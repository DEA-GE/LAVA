import logging
import os

import geopandas as gpd

import requests

from lava.utils.study_area import StudyArea


def prepare_coastlines(study_area: StudyArea):
    """Clip the global oceans and seas file to the study region."""
    print("\nprocessing coastlines")
    output_dir = study_area.output_dir
    goas_region_filePath = os.path.join(
        output_dir, f"goas_{study_area.name}_{study_area.global_crs_tag}.gpkg"
    )
    if not os.path.exists(
        goas_region_filePath
    ):  # process data if file not exists in output folder
        goas_raw_filePath = os.path.join(
            study_area.raw_spatial_data_folder, "GOAS", "goas.gpkg"
        )
        if not os.path.exists(goas_raw_filePath):
            print("downloading global oceans and seas (coastlines)")
            goas_download(
                output_dir=os.path.join(study_area.raw_spatial_data_folder, "GOAS")
            )
        try:
            print("clipping coastlines to study region")
            coastlines = gpd.read_file(goas_raw_filePath)
            coastlines_region = coastlines.clip(study_area.bounding_box_4326)
            if not coastlines_region.empty:
                coastlines_region.to_file(
                    goas_region_filePath,
                    driver="GPKG",
                    encoding="utf-8",
                )
            else:
                logging.info("no coastline in study region")
        except Exception as e:
            logging.error(f"global oceans and seas (coastlines) failed: {e}")
    else:
        print("GOAS data already exists for region")


def goas_download(output_dir):
    base_url = "https://geo.vliz.be/geoserver/MarineRegions/wfs"

    # Parameters for WFS request - using GeoJSON output
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "goas",
        #'cql_filter': 'mrgid=3293',  # Filter by Marine Regions ID
        "outputFormat": "application/json",
    }

    response = requests.get(base_url, params=params, timeout=300)

    if response.status_code == 200:
        gdf = gpd.read_file(response.text)
        gpkg_path = os.path.join(output_dir, "goas.gpkg")
        gdf.to_file(gpkg_path, driver="GPKG")
    else:
        logging.error(f"GOAS download failed: {response.status_code}")
