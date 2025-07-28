#!/usr/bin/env python3
"""Simplified aggregation of LAVA available land results.

This script searches for all raster files matching ``*_available_land_*.tif``
inside ``data/**/available_land/``. The technology and scenario are parsed
from the file name and all rasters belonging to the same technology and
scenario are merged into a single geometry. The geometries are written as
layers to a GeoPackage (``aggregated_available_land.gpkg`` by default).

Usage::

    python simple_results_analysis.py [--root PATH] [--output FILE]

The optional ``--root`` argument should point to the repository root
containing the ``data`` directory. ``--output`` sets the resulting
GeoPackage path.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import geopandas as gpd
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape
from shapely.ops import unary_union


_PATTERN = re.compile(r"(.+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)_available_land_.*\.tif$")


def _parse_info(path: Path):
    match = _PATTERN.match(path.name)
    if not match:
        return None
    region, tech, scenario = match.groups()
    return region, tech, scenario


def _raster_to_gdf(path: Path) -> gpd.GeoDataFrame:
    with rasterio.open(path) as src:
        data = src.read(1)
        mask = data != src.nodata
        geoms = [shape(geom) for geom, val in shapes(data, mask=mask, transform=src.transform) if val != src.nodata]
    return gpd.GeoDataFrame({"geometry": geoms}, crs=src.crs)


def aggregate_available_land(root: Path, output: Path) -> None:
    files = list(root.glob("data/**/available_land/*_available_land_*.tif"))
    groups: dict[tuple[str, str], list[Path]] = {}
    for f in files:
        info = _parse_info(f)
        if not info:
            continue
        _, tech, scen = info
        groups.setdefault((tech, scen), []).append(f)

    if not groups:
        print("No available land rasters found.")
        return

    with gpd.io.file.fiona.drivers():
        for (tech, scen), paths in groups.items():
            geoms = [_raster_to_gdf(p) for p in paths]
            merged_geom = unary_union([g.unary_union for g in geoms])
            gdf = gpd.GeoDataFrame(
                {"technology": [tech], "scenario": [scen], "geometry": [merged_geom]},
                crs=geoms[0].crs,
            )
            layer = f"{tech}_{scen}"
            gdf.to_file(output, layer=layer, driver="GPKG")
            print(f"Written layer {layer} with {len(paths)} files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate available land rasters")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root containing data directory")
    parser.add_argument("--output", type=Path, default=Path("aggregated_available_land.gpkg"), help="Output GeoPackage path")
    args = parser.parse_args()
    aggregate_available_land(args.root, args.output)
