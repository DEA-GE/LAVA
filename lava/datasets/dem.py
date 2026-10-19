import logging
import os

import numpy as np
import rasterio
import richdem
import xdem

from lava.utils.study_area import StudyArea
from lava.utils.common import rel_path
from lava.utils.raster import (
    clip_reproject_raster,
    reproject_raster,
    save_richdem_file,
)


def prepare_dem(
    study_area: StudyArea,
    dem_raster_path,
    compute_terrain_ruggedness,
    north_facing_slope_threshold,
    north_facing_aspect_min,
    north_facing_aspect_max,
):
    """Clip the DEM and derive slope, aspect, ruggedness and north-facing pixels."""
    print("\nprocessing DEM")
    output_dir = study_area.output_dir
    region_name_clean = study_area.name
    local_crs_tag = study_area.local_crs_tag
    global_crs_tag = study_area.global_crs_tag
    try:
        clip_reproject_raster(
            dem_raster_path,
            region_name_clean,
            study_area.boundary_4326,
            "DEM",
            study_area.local_crs,
            "bilinear",
            "float32",
            output_dir,
        )
        # DEM larger than study area to account for Ruggedness Index calculation
        clip_reproject_raster(
            dem_raster_path,
            region_name_clean,
            study_area.boundary_buffered_4000_4326,
            "DEM_buffered",
            study_area.local_crs,
            "bilinear",
            "float32",
            output_dir,
        )
        dem_local_buffered_Path = os.path.join(
            output_dir, f"DEM_buffered_{region_name_clean}_{local_crs_tag}.tif"
        )  # for ruggedness index calculation
        dem_localCRS_Path = os.path.join(
            output_dir, f"DEM_{region_name_clean}_{local_crs_tag}.tif"
        )

        richdem_helper_dir = os.path.join(output_dir, "derived_from_DEM")
        os.makedirs(richdem_helper_dir, exist_ok=True)

        # create slope map (https://www.earthdatascience.org/tutorials/get-slope-aspect-from-digital-elevation-model/)
        # save in local CRS
        dem_file = richdem.LoadGDAL(dem_localCRS_Path)
        slope = richdem.TerrainAttribute(dem_file, attrib="slope_degrees")
        slopeFilePathLocalCRS = os.path.join(
            richdem_helper_dir, f"slope_{region_name_clean}_{local_crs_tag}.tif"
        )
        save_richdem_file(slope, dem_localCRS_Path, slopeFilePathLocalCRS)
        # save in 4326: slope cannot be calculated from EPSG4326 because units get confused (https://github.com/r-barnes/richdem/issues/34)
        slopeFilePath4326 = os.path.join(
            richdem_helper_dir, f"slope_{region_name_clean}_EPSG4326.tif"
        )
        reproject_raster(
            slopeFilePathLocalCRS,
            region_name_clean,
            4326,
            "bilinear",
            "float32",
            slopeFilePath4326,
        )

        # create aspect map
        dem_file = richdem.LoadGDAL(dem_localCRS_Path)
        aspect = richdem.TerrainAttribute(dem_file, attrib="aspect")
        aspectFilePathLocalCRS = os.path.join(
            richdem_helper_dir, f"aspect_{region_name_clean}_{local_crs_tag}.tif"
        )
        save_richdem_file(aspect, dem_localCRS_Path, aspectFilePathLocalCRS)
        # save in 4326: not sure if aspect is calculated correctly in EPSG4326 because units might get confused (https://github.com/r-barnes/richdem/issues/34)
        aspectFilePath4326 = os.path.join(
            richdem_helper_dir, f"aspect_{region_name_clean}_EPSG4326.tif"
        )
        reproject_raster(
            aspectFilePathLocalCRS,
            region_name_clean,
            4326,
            "bilinear",
            "float32",
            aspectFilePath4326,
        )

        # ------------- Terrain Ruggedness Index -----------------
        if compute_terrain_ruggedness:
            print("\nprocessing Terrain Ruggedness Index")
            tri_local_path = os.path.join(
                richdem_helper_dir,
                f"TerrainRuggednessIndex_{region_name_clean}_{local_crs_tag}.tif",
            )
            tri_global_path = os.path.join(
                richdem_helper_dir,
                f"TerrainRuggednessIndex_{region_name_clean}_{global_crs_tag}.tif",
            )
            if os.path.exists(tri_local_path) and os.path.exists(tri_global_path):
                print(
                    f"Terrain Ruggedness Index already exists at {rel_path(tri_local_path)}. Skipping calculation."
                )
            else:
                dem = xdem.DEM(dem_local_buffered_Path)
                tri = dem.terrain_ruggedness_index(window_size=9)
                tri.data = np.rint(tri.data).astype(np.float32)
                tri.save(tri_local_path)
                reproject_raster(
                    tri_local_path,
                    region_name_clean,
                    4326,
                    "bilinear",
                    "float32",
                    tri_global_path,
                )

        # create map showing pixels with slope bigger X and aspect between Y and Z (north facing with slope where you would not build PV)
        create_north_facing_pixels(
            slopeFilePath4326,
            aspectFilePath4326,
            region_name_clean,
            richdem_helper_dir,
            north_facing_slope_threshold,
            north_facing_aspect_min,
            north_facing_aspect_max,
        )

    except Exception as e:
        logging.error(f"DEM failed: {e}")


def create_north_facing_pixels(
    slopeFilePath, aspectFilePath, region_name_clean, richdem_helper_dir, X, Y, Z
):
    if "resampled" in slopeFilePath:
        resampled = "_resampled"
    else:
        resampled = ""

    # Open the slope and aspect rasters
    with rasterio.open(slopeFilePath) as src_slope:
        slope = src_slope.read(1)  # Read the slope data
        profile = src_slope.profile  # Get the profile for writing the output file
        crs_slope = src_slope.crs  # Access the CRS from metadata
        EPSG_slope = crs_slope.to_epsg()  # get EPSG code

    with rasterio.open(aspectFilePath) as src_aspect:
        aspect = src_aspect.read(1)  # Read the aspect data
        crs_aspect = src_aspect.crs  # Access the CRS from metadata
        EPSG_aspect = crs_aspect.to_epsg()  # get EPSG code

    if EPSG_slope == EPSG_aspect:
        # create map showing pixels with slope bigger X and aspect between Y and Z (north facing with slope where you would not build PV)
        condition = (slope > X) & ((aspect >= Y) | (aspect <= Z))
        result = np.where(
            condition, 1, 0
        )  # Create a new raster with the filtered results

        profile.update(
            dtype=rasterio.int16, count=1, nodata=0, compress="DEFLATE"
        )  # Update the profile for the output raster

        if result.sum() > 0:
            # Write the result to a new raster file
            with rasterio.open(
                os.path.join(
                    richdem_helper_dir,
                    f"north_facing_{region_name_clean}_EPSG{EPSG_slope}{resampled}.tif",
                ),
                "w",
                **profile,
            ) as dst:
                dst.write(result.astype(rasterio.int16), 1)
        if result.sum() == 0:
            logging.info("no north-facing pixel exceeding threshold slope")

    else:
        print("EPSG codes of used rasters is not the same")
