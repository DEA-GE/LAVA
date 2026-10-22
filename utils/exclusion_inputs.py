from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml
from pyproj import CRS

from utils.tech_config import load_tech_config_from_path


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        document = yaml.load(file, Loader=yaml.FullLoader) or {}
    if not isinstance(document, dict):
        raise TypeError(f"Expected a YAML mapping in {path}.")
    return document


def _crs_tag(crs: CRS) -> str:
    authority = crs.to_authority()
    if authority:
        return "".join(authority)
    return crs.to_string().replace(":", "_")


def _selected(value: Any) -> bool:
    return value is not None


def _enabled(value: Any) -> bool:
    return value not in (None, False, 0, "", "0")


def _configured_custom_files(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        candidates = value.keys()
    elif isinstance(value, (list, tuple, set)):
        candidates = value
    else:
        return []
    return [name for name in candidates if isinstance(name, str) and name.strip()]


def resolve_exclusion_inputs(
    *,
    region: str,
    technology: str,
    scenario: str,
    local_crs_path: str | Path,
    project_root: str | Path = ".",
) -> list[str]:
    """Return the files that affect one exclusion job.

    The function is intended for a Snakemake input function evaluated after the
    spatial-data checkpoint. It mirrors the configuration conditions in
    ``Exclusion.py`` and retains the existing CRS-tagged filenames.
    """

    root = Path(project_root)
    config_path = root / "configs" / "config.yaml"
    technology_config_path = root / "configs" / f"{technology}.yaml"
    config = _load_yaml_mapping(config_path)
    technology_config = load_tech_config_from_path(
        str(technology_config_path), scenario
    )

    local_crs_path = Path(local_crs_path)
    with local_crs_path.open("rb") as file:
        prepared_local_crs = CRS.from_user_input(pickle.load(file))

    projection_manual = technology_config.get("projection_manual")
    active_local_crs = (
        CRS.from_user_input(projection_manual)
        if projection_manual is not None
        else prepared_local_crs
    )
    local_crs_tag = _crs_tag(active_local_crs)

    # spatial_data_prep.py currently fixes the global CRS to EPSG:4326.
    global_crs_tag = "EPSG4326"
    data_path = root / "data" / region
    osm_path = data_path / "OSM_Infrastructure"
    dem_helpers = data_path / "derived_from_DEM"

    inputs: list[Path] = [
        config_path,
        technology_config_path,
        local_crs_path,
        data_path / f"{region}_global_CRS.pkl",
        data_path / f"{region}_{global_crs_tag}.geojson",
    ]

    if technology_config.get("resolution_manual") is None:
        inputs.append(data_path / f"pixel_size_{region}_{local_crs_tag}.json")

    if technology_config.get("landcover_codes") and _enabled(
        config.get("landcover_source")
    ):
        inputs.append(
            data_path
            / f"landcover_{config.get('landcover_source')}_{region}_{global_crs_tag}.tif"
        )
    if _selected(technology_config.get("max_elevation")):
        inputs.append(data_path / f"DEM_{region}_{global_crs_tag}.tif")
    if _selected(technology_config.get("max_slope")):
        inputs.append(dem_helpers / f"slope_{region}_{global_crs_tag}.tif")
    if _selected(technology_config.get("max_buildings_footprint")) and _enabled(
        config.get("buildings_filename")
    ):
        inputs.append(data_path / f"buildings_{region}_ESRI54009.tif")
    if _selected(technology_config.get("max_terrain_ruggedness")) and _enabled(
        config.get("compute_terrain_ruggedness")
    ):
        inputs.append(
            dem_helpers / f"TerrainRuggednessIndex_{region}_{global_crs_tag}.tif"
        )
    if _selected(technology_config.get("max_population")) and config.get(
        "population_source"
    ) in {"worldpop", "file"}:
        inputs.append(data_path / f"population_{region}_{global_crs_tag}.tif")
    if _selected(technology_config.get("north_facing_pixels")):
        inputs.append(dem_helpers / f"north_facing_{region}_{global_crs_tag}.tif")

    if (
        technology in {"onshorewind", "offshorewind"}
        and (
            _selected(technology_config.get("min_wind_speed"))
            or _selected(technology_config.get("max_wind_speed"))
        )
        and _enabled(config.get("wind_atlas"))
    ):
        inputs.append(data_path / f"wind_{region}_{global_crs_tag}.tif")
    if (
        technology == "solar"
        and (
            _selected(technology_config.get("min_solar_production"))
            or _selected(technology_config.get("max_solar_production"))
        )
        and _enabled(config.get("solar_atlas"))
    ):
        inputs.append(data_path / f"solar_{region}_{global_crs_tag}.tif")

    osm_conditions = {
        "railways.gpkg": ("railways", ("railways_buffer",)),
        "roads.gpkg": ("roads", ("roads_buffer", "roads_inclusion_buffer")),
        "airports.gpkg": ("airports", ("airports_buffer",)),
        "waterbodies.gpkg": ("waterbodies", ("waterbodies_buffer",)),
        "military.gpkg": ("military", ("military_buffer",)),
        "transmission_lines.gpkg": (
            "transmission_lines",
            (
                "transmission_lines_buffer",
                "transmission_inclusion_buffer",
            ),
        ),
        "generators.gpkg": ("generators", ("generators_buffer",)),
        "plants.gpkg": ("plants", ("plants_buffer",)),
        "substations.gpkg": ("substations", ("substations_inclusion_buffer",)),
    }
    for filename, (source_key, technology_keys) in osm_conditions.items():
        if _enabled(config.get(source_key)) and any(
            _selected(technology_config.get(key)) for key in technology_keys
        ):
            inputs.append(osm_path / filename)

    if _selected(technology_config.get("coastlines_buffer")) and _enabled(
        config.get("coastlines")
    ):
        inputs.append(data_path / f"goas_{region}_{global_crs_tag}.gpkg")
    if _selected(technology_config.get("protectedAreas_buffer")) and config.get(
        "protected_areas_source"
    ) in {"WDPA", "file"}:
        inputs.append(
            data_path
            / (
                f"protected_areas_{config.get('protected_areas_source')}_"
                f"{region}_{global_crs_tag}.gpkg"
            )
        )
    if _selected(technology_config.get("max_forest_density")) and _enabled(
        config.get("forest_density")
    ):
        inputs.append(data_path / f"forest_density_{region}_{global_crs_tag}.tif")

    if _enabled(config.get("additional_exclusion_polygons_folder_name")):
        for filename in _configured_custom_files(
            technology_config.get("additional_exclusion_polygons_buffer")
        ):
            inputs.append(data_path / "additional_exclusion_polygons" / filename)
    if _enabled(config.get("additional_exclusion_rasters_folder_name")):
        for filename in _configured_custom_files(
            technology_config.get("additional_exclusion_rasters_buffer")
        ):
            inputs.append(data_path / "additional_exclusion_rasters" / filename)

    model_areas_filename = config.get("model_areas_filename")
    if model_areas_filename:
        inputs.append(
            root / "Raw_Spatial_Data" / "model_areas" / str(model_areas_filename)
        )

    # Preserve order while avoiding duplicate files selected by multiple options.
    return [str(path) for path in dict.fromkeys(inputs)]


def inspect_prepared_input_files(paths: Iterable[str | Path]) -> dict[str, str]:
    """Return unusable prepared inputs and a concise reason for each one.

    Checks are deliberately lightweight so existing cached files remain valid.
    Structured metadata and CRS pickle files are parsed, raster headers are
    opened when rasterio is available, and GeoPackages get a SQLite signature
    check. Other formats must exist as non-empty regular files.
    """

    issues: dict[str, str] = {}
    for raw_path in dict.fromkeys(str(path) for path in paths):
        path = Path(raw_path)
        if not path.exists():
            issues[raw_path] = "missing"
            continue
        if not path.is_file():
            issues[raw_path] = "not a regular file"
            continue
        try:
            if path.stat().st_size == 0:
                issues[raw_path] = "empty"
                continue
        except OSError as exc:
            issues[raw_path] = f"cannot be inspected: {exc}"
            continue

        suffix = path.suffix.lower()
        try:
            if suffix in {".json", ".geojson"}:
                with path.open("r", encoding="utf-8") as file:
                    json.load(file)
            elif suffix == ".pkl":
                with path.open("rb") as file:
                    pickle.load(file)
            elif suffix in {".tif", ".tiff"}:
                try:
                    import rasterio
                except ImportError:
                    # Existence and size still provide a useful fallback in
                    # lightweight environments that only inspect the DAG.
                    continue
                with rasterio.open(path) as dataset:
                    if dataset.width <= 0 or dataset.height <= 0:
                        raise ValueError("raster has no pixels")
            elif suffix == ".gpkg":
                with path.open("rb") as file:
                    if file.read(16) != b"SQLite format 3\x00":
                        raise ValueError("invalid GeoPackage header")
        except Exception as exc:
            issues[raw_path] = f"unreadable {suffix or 'file'}: {exc}"
    return issues


def validate_region_exclusion_inputs(
    *,
    region: str,
    technology_scenarios: Mapping[str, Iterable[str]],
    local_crs_path: str | Path,
    project_root: str | Path = ".",
) -> dict[tuple[str, str], dict[str, str]]:
    """Validate exact prepared inputs for every selected exclusion job.

    The result is grouped by ``(technology, scenario)``. An empty mapping means
    that every resolved input exists and passed its lightweight integrity check.
    """

    required_by_job: dict[tuple[str, str], list[str]] = {}
    all_required: list[str] = []
    for technology, selected_scenarios in technology_scenarios.items():
        for scenario in selected_scenarios:
            job = (str(technology), str(scenario))
            required = resolve_exclusion_inputs(
                region=region,
                technology=job[0],
                scenario=job[1],
                local_crs_path=local_crs_path,
                project_root=project_root,
            )
            required_by_job[job] = required
            all_required.extend(required)

    issues_by_path = inspect_prepared_input_files(all_required)
    return {
        job: {
            path: issues_by_path[path]
            for path in required
            if path in issues_by_path
        }
        for job, required in required_by_job.items()
        if any(path in issues_by_path for path in required)
    }
