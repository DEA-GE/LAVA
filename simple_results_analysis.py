#!/usr/bin/env python3
"""Simplified aggregation of LAVA available land results.

This script reads exclusion info files inside ``data/**/available_land/`` to
determine region, technology and scenario. It then searches for matching
``{region}_{technology}_{scenario}_available_land_*.tif`` rasters, reprojects
them to ``EPSG:4326`` and merges them into a single raster. This
combined raster is then converted to vector polygons. The polygons are
written as layers to a GeoPackage (``aggregated_available_land.gpkg`` by
default).

Usage::

    python simple_results_analysis.py [--root PATH] [--output FILE] [--json-output FILE]

By default ``--root`` is the directory containing this script, i.e. the
repository root. ``--output`` sets the resulting GeoPackage path and
``--json-output`` specifies where to write a JSON file with the individual
measures and their aggregated values. The exported measures are expressed in
scientific notation, with area converted to square kilometres and power to
terawatts.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import geopandas as gpd
import rasterio
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.merge import merge
from rasterio.vrt import WarpedVRT
from shapely.geometry import shape
from shapely.ops import unary_union




logger = logging.getLogger(__name__)



TARGET_CRS = CRS.from_epsg(4326)


def _merge_rasters(paths: list[Path]):
    """Reproject rasters to EPSG:4326, merge and return data, transform, nodata and crs."""
    srcs = [rasterio.open(p) for p in paths]
    vrts = [WarpedVRT(src, crs=TARGET_CRS) for src in srcs]
    try:
        mosaic, out_trans = merge(vrts)
        nodata = vrts[0].nodata
    finally:
        for vrt in vrts:
            vrt.close()
        for src in srcs:
            src.close()
    return mosaic[0], out_trans, nodata, TARGET_CRS


def _array_to_gdf(data, transform, nodata, crs) -> gpd.GeoDataFrame:
    mask = data != nodata
    geoms = [shape(geom) for geom, val in shapes(data, mask=mask, transform=transform) if val != nodata]
    return gpd.GeoDataFrame({"geometry": geoms}, crs=crs)


def parse_info_json(path: Path) -> dict | None:
    """Parse exclusion info JSON file and return metrics.

    Expected keys are ``technology``, ``scenario``, ``eligibility_share``
    (fractional), ``available_area_m2`` and ``power_potential_MW`` written in
    ``Exclusion.py``. Returns ``None`` if the file is missing, cannot be
    decoded or lacks required keys.
    """

    try:
        with path.open() as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.warning("Missing info file %s", path)
        return None
    except json.JSONDecodeError:
        logger.warning("Malformed info file %s", path)
        return None

    try:
        return {
            "technology": str(data["technology"]),
            "scenario": str(data["scenario"]),
            "eligibility_share": float(data["eligibility_share"]),
            "available_area": float(data["available_area_m2"]),
            "power_potential": float(data["power_potential_MW"]),
        }
    except KeyError as e:
        logger.warning("Missing key %s in info file %s", e, path)
        return None
    except (TypeError, ValueError):
        logger.warning("Malformed values in info file %s", path)
        return None


def aggregate_available_land(root: Path, output: Path, json_output: Path) -> None:
    info_files = list(root.glob("data/**/available_land/*_exclusion_info.json"))
    groups: dict[tuple[str, str], list[tuple[str, Path, dict]]] = {}
    for info_file in info_files:
        parts = info_file.stem.split("_")
        if len(parts) < 5 or parts[-2:] != ["exclusion", "info"]:
            continue
        region = "_".join(parts[:-4])
        scen = parts[-4]
        tech = parts[-3]
        info_dict = parse_info_json(info_file)
        if not info_dict:
            continue
        pattern = f"{region}_{tech}_{scen}_available_land_*.tif"
        for raster in info_file.parent.glob(pattern):
            groups.setdefault((tech, scen), []).append((region, raster, info_dict))
    if not groups:
        print("No available land rasters found.")
        return


    results: list[dict] = []


    for (tech, scen), items in groups.items():
        paths = [p for _, p, _ in items]
        data, transform, nodata, crs = _merge_rasters(paths)
        gdf = _array_to_gdf(data, transform, nodata, crs)
        merged_geom = unary_union(gdf.geometry)

        area_sum = sum(info["available_area"] for _, _, info in items)
        power_sum = sum(info["power_potential"] for _, _, info in items)
        shares = [info["eligibility_share"] for _, _, info in items]
        share_agg = sum(shares) / len(shares) if shares else None

        def to_sci(value: float) -> str:
            return f"{value:.2e}"

        gdf = gpd.GeoDataFrame(
            {
                "technology": [tech],
                "scenario": [scen],
                "available_area": [area_sum],
                "power_potential": [power_sum],
                "eligibility_share": [share_agg],
                "geometry": [merged_geom],
            },
            crs=crs,
        )
        layer = f"{tech}_{scen}"
        gdf.to_file(output, layer=layer, driver="GPKG")
        print(f"Written layer {layer} with {len(paths)} files")

        region_measures: dict[str, dict] = {}
        for region, _, info in items:
            share_val =  round(info["eligibility_share"] * 100 ,2) # Convert to percentage
            area_val = round( info["available_area"] / 1e6 ,2)  # Convert m2 to km2
            power_val = round(info["power_potential"] / 1e6, 2)  # Convert MW to TW
            #print(
            #    f"{region}: share={to_sci(share_val)}, area={to_sci(area_val)} km2, "
            #    f"power={to_sci(power_val)} TW"
            #)
            region_measures[region] = {
                "eligibility_share_%": share_val,
                "available_area_km2": to_sci(area_val),
                "power_potential_TW": power_val,
            }


        results.append(
            {
                "scenario": scen,
                "technology": tech,
                "aggregated": {
                    "eligibility_share_%": round(share_agg * 100,2)  if share_agg is not None else None,
                    "available_area_km2": to_sci(area_sum / 1e6),
                    "power_potential_TW": round(power_sum / 1e6,2)
                },
                "regions": region_measures,
            }
        )

    with json_output.open("w") as f:
        json.dump(results, f, indent=2)
    print(f"Written metrics JSON to {json_output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate available land rasters")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Project root containing data directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("aggregated_available_land.gpkg"),
        help="Output GeoPackage path",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("aggregated_available_land.json"),
        help="Path to write aggregated metrics JSON",
    )
    args = parser.parse_args()
    aggregate_available_land(args.root, args.output, args.json_output)
