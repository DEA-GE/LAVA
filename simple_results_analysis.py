#!/usr/bin/env python3
"""Simplified aggregation of LAVA available land results.

This script searches for all raster files matching ``*_available_land_*.tif``
inside ``data/**/available_land/``. The technology and scenario are parsed
from the file name and rasters belonging to the same technology and scenario
are reprojected to ``EPSG:4326`` and merged into a single raster. This
combined raster is then converted to vector polygons. The polygons are
written as layers to a GeoPackage (``aggregated_available_land.gpkg`` by
default).

Usage::

    python simple_results_analysis.py [--root PATH] [--output FILE]

By default ``--root`` is the directory containing this script, i.e. the
repository root. ``--output`` sets the resulting GeoPackage path.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

import geopandas as gpd
import rasterio
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.merge import merge
from rasterio.vrt import WarpedVRT
from shapely.geometry import shape
from shapely.ops import unary_union


_PATTERN = re.compile(r"(.+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)_available_land_.*\.tif$")


def _parse_info(path: Path):
    match = _PATTERN.match(path.name)
    if not match:
        return None
    region, tech, scenario = match.groups()
    return region, tech, scenario


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

    Expected keys are ``eligibility_share`` (fractional), ``available_area_m2``
    and ``power_potential_MW`` written in ``Exclusion.py``. Returns ``None``
    if the file is missing, cannot be decoded or lacks required keys.
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


def aggregate_available_land(root: Path, output: Path) -> None:
    files = list(root.glob("data/**/available_land/*_available_land_*.tif"))
    groups: dict[tuple[str, str], list[tuple[str, Path, dict]]] = {}
    for f in files:
        info = _parse_info(f)
        if not info:
            continue
        region, tech, scen = info
        info_path = f.parent / f"{region}_{scen}_{tech}_exclusion_info.json"
        info_dict = parse_info_json(info_path)
        if not info_dict:
            continue
        groups.setdefault((tech, scen), []).append((region, f, info_dict))

    if not groups:
        print("No available land rasters found.")
        return

    for (tech, scen), items in groups.items():
        paths = [p for _, p, _ in items]
        data, transform, nodata, crs = _merge_rasters(paths)
        gdf = _array_to_gdf(data, transform, nodata, crs)
        merged_geom = unary_union(gdf.geometry)

        area_sum = sum(info["available_area"] for _, _, info in items)
        power_sum = sum(info["power_potential"] for _, _, info in items)
        shares = [info["eligibility_share"] for _, _, info in items]
        share_agg = sum(shares) / len(shares) if shares else None

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

        for region, _, info in items:
            print(
                f"{region}: share={info['eligibility_share']:.2%}, area={info['available_area']:.2f} m2, "
                f"power={info['power_potential']:.2f} MW"
            )
        print(
            f"Total {tech} {scen}: share={share_agg:.2% if share_agg is not None else 'NA'}, "
            f"area={area_sum:.2f} m2, power={power_sum:.2f} MW"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate available land rasters")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Project root containing data directory",
    )
    parser.add_argument("--output", type=Path, default=Path("aggregated_available_land.gpkg"), help="Output GeoPackage path")
    args = parser.parse_args()
    aggregate_available_land(args.root, args.output)
