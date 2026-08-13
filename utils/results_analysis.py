#!/usr/bin/env python3
"""Aggregate LAVA exclusion results by technology and scenario.

The JSON metadata written by ``Exclusion.py`` is the source of truth for the
technology, scenario, and area metrics. Region names come from the enclosing
``data/<region>/available_land`` directory, so underscores in any of these
values do not require ambiguous filename parsing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.merge import merge
from rasterio.vrt import WarpedVRT
from shapely.geometry import shape
from shapely.ops import unary_union


TARGET_CRS = CRS.from_epsg(4326)


class ResultsAnalysisError(RuntimeError):
    """A user-actionable problem with the available-land result set."""


def _required_text(data: dict, key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ResultsAnalysisError(
            f"{path} must define a non-empty string value for '{key}'."
        )
    return value.strip()


def _required_number(data: dict, key: str, path: Path) -> float:
    try:
        value = float(data[key])
    except KeyError as exc:
        raise ResultsAnalysisError(f"{path} is missing required field '{key}'.") from exc
    except (TypeError, ValueError) as exc:
        raise ResultsAnalysisError(f"{path} has a non-numeric '{key}' value.") from exc
    return value


def parse_info_json(path: Path) -> dict:
    """Read and validate exclusion metadata, including documented legacy data."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ResultsAnalysisError(f"Exclusion metadata file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ResultsAnalysisError(
            f"Exclusion metadata is not valid JSON: {path} ({exc})"
        ) from exc
    except OSError as exc:
        raise ResultsAnalysisError(f"Could not read exclusion metadata {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ResultsAnalysisError(f"Exclusion metadata must be a JSON object: {path}")

    technology = _required_text(data, "technology", path)
    scenario = _required_text(data, "scenario", path)
    eligibility_share = _required_number(data, "eligibility_share", path)
    power_potential = _required_number(data, "power_potential_MW", path)
    if not 0.0 <= eligibility_share <= 1.0:
        raise ResultsAnalysisError(
            f"{path} has eligibility_share={eligibility_share}; expected a fraction from 0 to 1."
        )

    if "available_area_m2" in data:
        available_area = _required_number(data, "available_area_m2", path)
    elif "available_area_km2" in data:
        # Exclusion outputs created before available_area_m2 was added.
        available_area = _required_number(data, "available_area_km2", path) * 1e6
    else:
        raise ResultsAnalysisError(
            f"{path} must define 'available_area_m2' (or legacy 'available_area_km2')."
        )

    if "study_area_m2" in data:
        study_area = _required_number(data, "study_area_m2", path)
    elif eligibility_share > 0:
        # The old schema stored enough information to recover the study area.
        study_area = available_area / eligibility_share
    else:
        raise ResultsAnalysisError(
            f"{path} has no 'study_area_m2' and its zero eligibility share cannot be used "
            "to reconstruct it. Re-run Exclusion.py for this result."
        )

    if available_area < 0 or study_area <= 0 or power_potential < 0:
        raise ResultsAnalysisError(
            f"{path} contains invalid negative area/power values or a non-positive study area."
        )
    return {
        "technology": technology,
        "scenario": scenario,
        "eligibility_share": eligibility_share,
        "available_area": available_area,
        "study_area": study_area,
        "power_potential": power_potential,
    }


def _resolve_available_land_raster(
    folder: Path, region: str, technology: str, scenario: str
) -> Path:
    """Resolve the current stable raster or one legacy CRS-tagged raster."""
    base = f"{region}_{technology}_{scenario}_available_land"
    current = folder / f"{base}.tif"
    if current.is_file():
        return current
    legacy = sorted(folder.glob(f"{base}_*.tif"))
    # ResourceValues is a derived raster, never the binary available-land input.
    legacy = [path for path in legacy if not path.stem.endswith("_ResourceValues")]
    if len(legacy) == 1:
        return legacy[0]
    if len(legacy) > 1:
        names = ", ".join(path.name for path in legacy)
        raise ResultsAnalysisError(
            f"Multiple legacy available-land rasters match {base}: {names}. "
            "Keep only the raster belonging to this result."
        )
    raise ResultsAnalysisError(
        f"Missing available-land raster for region '{region}', technology "
        f"'{technology}', scenario '{scenario}'. Expected {current}."
    )


def _build_groups(root: Path) -> dict[tuple[str, str], list[tuple[str, Path, dict]]]:
    """Collect result rasters by (technology, scenario), using JSON metadata."""
    data_dir = root / "data"
    if not data_dir.is_dir():
        raise ResultsAnalysisError(f"Data directory not found: {data_dir}")
    info_files = sorted(data_dir.glob("*/available_land/*_exclusion_info.json"))
    if not info_files:
        raise ResultsAnalysisError(
            f"No exclusion metadata files were found below {data_dir}. "
            "Run the exclusion stage before aggregating results."
        )

    groups: dict[tuple[str, str], list[tuple[str, Path, dict]]] = {}
    seen: set[tuple[str, str, str]] = set()
    for info_file in info_files:
        region = info_file.parent.parent.name
        info = parse_info_json(info_file)
        technology = info["technology"]
        scenario = info["scenario"]
        identity = (region, technology, scenario)
        if identity in seen:
            raise ResultsAnalysisError(
                "Duplicate exclusion metadata for region/technology/scenario "
                f"{identity}: {info_file.parent}"
            )
        seen.add(identity)
        raster = _resolve_available_land_raster(
            info_file.parent, region, technology, scenario
        )
        groups.setdefault((technology, scenario), []).append((region, raster, info))
    return groups


def _merge_rasters(paths: list[Path]):
    srcs = [rasterio.open(path) for path in paths]
    vrts = [WarpedVRT(src, crs=TARGET_CRS) for src in srcs]
    try:
        mosaic, transform = merge(vrts)
        nodata = vrts[0].nodata
    finally:
        for vrt in vrts:
            vrt.close()
        for src in srcs:
            src.close()
    return mosaic[0], transform, nodata, TARGET_CRS


def _array_to_gdf(data, transform, nodata, crs) -> gpd.GeoDataFrame:
    mask = data != nodata if nodata is not None else data.astype(bool)
    geoms = [
        shape(geom)
        for geom, value in shapes(data, mask=mask, transform=transform)
        if nodata is None or value != nodata
    ]
    if not geoms:
        raise ResultsAnalysisError("An available-land raster contains no eligible pixels.")
    return gpd.GeoDataFrame({"geometry": geoms}, crs=crs)


def _derive_suffixed(path: Path, suffix_token: str) -> Path:
    return path.with_name(f"{path.stem}_{suffix_token}{path.suffix}")


def _temporary_output(path: Path) -> Path:
    return path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp{path.suffix}")


def _layer_name(technology: str, scenario: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", f"{technology}_{scenario}").strip("_")
    return (clean or "results")[:63]


def _run_for_subset(
    subset: dict[tuple[str, str], list[tuple[str, Path, dict]]],
    out_gpkg: Path,
    out_json: Path,
    out_csv: Path,
) -> None:
    for path in (out_gpkg, out_json, out_csv):
        path.parent.mkdir(parents=True, exist_ok=True)
    temp_gpkg, temp_json, temp_csv = map(
        _temporary_output, (out_gpkg, out_json, out_csv)
    )
    temporary = (temp_gpkg, temp_json, temp_csv)
    results: list[dict] = []
    used_layers: set[str] = set()
    try:
        for index, ((technology, scenario), items) in enumerate(sorted(subset.items())):
            paths = [path for _, path, _ in items]
            data, transform, nodata, crs = _merge_rasters(paths)
            polygons = _array_to_gdf(data, transform, nodata, crs)
            merged_geometry = unary_union(polygons.geometry)

            available_area = sum(info["available_area"] for _, _, info in items)
            study_area = sum(info["study_area"] for _, _, info in items)
            power_potential = sum(info["power_potential"] for _, _, info in items)
            eligibility_share = available_area / study_area

            result_gdf = gpd.GeoDataFrame(
                {
                    "technology": [technology],
                    "scenario": [scenario],
                    "available_area": [available_area],
                    "power_potential": [power_potential],
                    "eligibility_share": [eligibility_share],
                    "geometry": [merged_geometry],
                },
                crs=crs,
            )
            layer = _layer_name(technology, scenario)
            if layer in used_layers:
                raise ResultsAnalysisError(
                    f"GeoPackage layer-name collision for '{technology}' / '{scenario}'."
                )
            used_layers.add(layer)
            result_gdf.to_file(
                temp_gpkg,
                layer=layer,
                driver="GPKG",
                mode="w" if index == 0 else "a",
            )
            print(f"Written temporary layer {layer} from {len(paths)} region raster(s).")

            regions = {}
            for region, _, info in items:
                regions[region] = {
                    "eligibility_share_%": round(info["eligibility_share"] * 100, 2),
                    "available_area_km2": f"{info['available_area'] / 1e6:.2e}",
                    "power_potential_TW": round(info["power_potential"] / 1e6, 2),
                }
            results.append(
                {
                    "scenario": scenario,
                    "technology": technology,
                    "aggregated": {
                        "eligibility_share_%": round(eligibility_share * 100, 2),
                        "available_area_km2": f"{available_area / 1e6:.2e}",
                        "power_potential_TW": round(power_potential / 1e6, 2),
                    },
                    "regions": regions,
                }
            )

        temp_json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        rows = []
        for entry in results:
            common = {"Scenario": entry["scenario"], "Technology": entry["technology"]}
            rows.append({**common, "Region": "ALL", **entry["aggregated"]})
            rows.extend(
                {**common, "Region": region, **metrics}
                for region, metrics in entry["regions"].items()
            )
        pd.DataFrame(rows).to_csv(temp_csv, index=False)

        for temporary_path, final_path in zip(temporary, (out_gpkg, out_json, out_csv)):
            temporary_path.replace(final_path)
        print(f"Written GeoPackage: {out_gpkg}")
        print(f"Written metrics JSON: {out_json}")
        print(f"Written metrics CSV: {out_csv}")
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def aggregate_available_land(
    root: Path,
    output: Path,
    json_output: Path,
    per_scenario_files: bool = False,
    csv_output: Path | None = None,
) -> None:
    root = root.resolve()
    groups = _build_groups(root)
    csv_output = csv_output or json_output.with_suffix(".csv")
    if per_scenario_files:
        for scenario in sorted({scenario for _, scenario in groups}):
            subset = {key: value for key, value in groups.items() if key[1] == scenario}
            _run_for_subset(
                subset,
                _derive_suffixed(output, scenario),
                _derive_suffixed(json_output, scenario),
                _derive_suffixed(csv_output, scenario),
            )
    else:
        _run_for_subset(groups, output, json_output, csv_output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate available-land results")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root containing the data directory",
    )
    parser.add_argument("--output", type=Path, default=Path("aggregated_available_land.gpkg"))
    parser.add_argument(
        "--json-output", type=Path, default=Path("aggregated_available_land.json")
    )
    parser.add_argument("--csv-output", type=Path, default=None)
    parser.add_argument("--per-scenario-files", action="store_true")
    args = parser.parse_args()
    try:
        aggregate_available_land(
            args.root,
            args.output,
            args.json_output,
            args.per_scenario_files,
            args.csv_output,
        )
    except ResultsAnalysisError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Results aggregation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
