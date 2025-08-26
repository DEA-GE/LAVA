#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: Matteo D'Andrea
@date: 18-06-2025

@description:
Script to generate proximity (distance) rasters from OpenStreetMap (OSM) features using the 
DistanceRaster tool from the distancerasters library.

The script rasterizes vector features (e.g., substations), calculates the
approximate geodesic distance from those features, and outputs the result as a GeoTIFF 
distance raster.

The region of interest is specified by a vector file (e.g., a GeoJSON polygon). The 
distance raster is clipped after calculation to match the region shape.
"""


import os
import time
from shapely.geometry import shape
import geopandas as gpd
import distancerasters as dr
import rasterio
from rasterio.mask import mask
import numpy as np

def raster_conditional(rarray):
    """
    Default condition function for DistanceRaster.
    Assumes the raster is binary and returns True where value == 1.
    """
    return (rarray == 1)

def generate_distance_raster(shapefile_path, region_gdf, output_path, pixel_size=0.01, no_data_value=-9999):
    """
    Generate a proximity raster from vector data and clip it to a specified region.

    Parameters:
        shapefile_path (str): Path to the input shapefile (.shp or .gpkg).
        region_gdf (geopandas.GeoDataFrame): Region boundary provided in-memory.
        output_path (str): Path to save the clipped output raster (.tif).
        pixel_size (float): Resolution of the output raster.
        no_data_value (int): NoData value to use in the raster.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    t0 = time.time()

    #print("Loading input data...")

    shp_gdf = gpd.read_file(shapefile_path)

    if shp_gdf.crs != region_gdf.crs:
        raise ValueError(
            f"CRS mismatch: region CRS is {region_gdf.crs}, but shp CRS is {shp_gdf.crs}"
        )

    region_bounds = region_gdf.total_bounds
    region_geometries = [shape(geom) for geom in region_gdf.geometry]

    temp_raster_path = os.path.join(os.path.dirname(output_path), "temp_rasterized.tif")

    #print("Rasterizing shapefile...")
    t1 = time.time()
    rv_array, affine = dr.rasterize(
        shp_gdf,
        pixel_size=pixel_size,
        bounds=region_bounds,
        fill=0,
        nodata=no_data_value,
        output=temp_raster_path,
    )
    #print(f"✔ Rasterization completed in {time.time() - t1:.2f} seconds")

 
    #print("Calculating distance raster...")
    t2 = time.time()
    dr_obj = dr.DistanceRaster(
        rv_array,
        affine=affine,
        output_path=output_path,
        conditional=raster_conditional
    )
    #print(f"✔ Distance calculation completed in {time.time() - t2:.2f} seconds")

    #print("Clipping raster to region...")
    t3 = time.time()
    with rasterio.open(output_path) as src:
        out_image, out_transform = mask(src, region_geometries, crop=True)
        out_meta = src.meta.copy()

    out_meta.update({
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
        "nodata": src.nodata
    })

    #print("Saving clipped raster...")
    with rasterio.open(output_path, 'w', **out_meta) as dest:
        dest.write(out_image)
    #print(f"✔ Clipping and saving completed in {time.time() - t3:.2f} seconds")

    #print(f"✅ Distance raster generation complete in {time.time() - t0:.2f} seconds.")

# Example usage
if __name__ == "__main__":
    region_demo = gpd.read_file(
        "Raw_Spatial_Data/custom_study_area/gadm41_CHN_1_NeiMongol.geojson"
    )
    generate_distance_raster(
        shapefile_path="data/NeiMongol/OSM_Infrastructure/substations.gpkg",
        region_gdf=region_demo,
        output_path="data/NeiMongol/proximity/substation_distance_raster.tif",
    )
