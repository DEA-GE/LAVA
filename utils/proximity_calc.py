#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import fiona
from shapely.geometry import shape
import distancerasters as dr
import rasterio
from rasterio.mask import mask

def raster_conditional(rarray):
    """
    Default condition function for DistanceRaster.
    Assumes the raster is binary and returns True where value == 1.
    """
    return (rarray == 1)

def generate_distance_raster(shapefile_path, region_path, output_path, pixel_size=0.01, no_data_value=-9999):
    """
    Generate a proximity raster from vector data and clip it to a specified region.

    Parameters:
        shapefile_path (str): Path to the input shapefile (.shp).
        region_path (str): Path to the region file (GeoJSON or similar).
        output_path (str): Path to save the clipped output raster (.tif).
        pixel_size (float): Resolution of the output raster.
        no_data_value (int): NoData value to use in the raster.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print("Loading input data...")
    with fiona.open(shapefile_path, "r") as shp, fiona.open(region_path, "r") as region:
        if shp.crs != region.crs:
            raise ValueError(f"CRS mismatch: region CRS is {region.crs}, but shp CRS is {shp.crs}")
        
        region_bounds = region.bounds
        region_geometries = [shape(feature['geometry']) for feature in region]

        temp_raster_path = os.path.join(os.path.dirname(output_path), "temp_rasterized.tif")

        print("Rasterizing shapefile...")
        rv_array, affine = dr.rasterize(
            shp,
            pixel_size=pixel_size,
            bounds=region_bounds,
            fill=0,
            nodata=no_data_value,
            output=temp_raster_path
        )

    print("Calculating distance raster...")
    dr_obj = dr.DistanceRaster(
        rv_array,
        affine=affine,
        output_path=output_path,
        conditional=raster_conditional
    )

    print("Clipping raster to region...")
    with rasterio.open(output_path) as src:
        out_image, out_transform = mask(src, region_geometries, crop=True)
        out_meta = src.meta.copy()

    out_meta.update({
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
        "nodata": src.nodata
    })

    print("Saving clipped raster...")
    with rasterio.open(output_path, 'w', **out_meta) as dest:
        dest.write(out_image)

    print("Distance raster generation complete.")


# Example usage

if __name__ == "__main__":
    generate_distance_raster(
        shapefile_path="Raw_Spatial_Data/Power_Infrastructure_v2/inner_mongolia_substation_polygons.shp",
        region_path="Raw_Spatial_Data/custom_polygon/gadm41_CHN_1_NeiMongol.json",
        output_path="Raw_Spatial_Data/proximity/substation_distance_raster_3.tif"
    )
