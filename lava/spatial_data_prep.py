# -*- coding: utf-8 -*-
"""
@author: Jonas Meier

TBA
"""

import time
import os
import yaml
import logging
import argparse
from pathlib import Path
from pyproj import CRS
from lava.project import PROJECT_ROOT
from lava.utils.study_area import StudyArea
from lava.utils.common import clean_region_name
from lava.utils.crs import save_crs
from lava.datasets.study_area_polygon import get_study_area_polygon
from lava.datasets.additional_layers import (
    prepare_additional_exclusion_polygons,
    prepare_additional_exclusion_rasters,
    prepare_additional_inclusion_polygons,
    prepare_additional_inclusion_rasters,
)
from lava.datasets.buildings import prepare_buildings
from lava.datasets.coastlines import prepare_coastlines
from lava.datasets.dem import prepare_dem
from lava.datasets.forest_density import prepare_forest_density
from lava.datasets.landcover import prepare_landcover_file, prepare_landcover_openeo
from lava.datasets.osm import prepare_osm_geofabrik, prepare_osm_overpass
from lava.datasets.population import (
    prepare_population_file,
    prepare_population_worldpop,
)
from lava.datasets.protected_areas import prepare_protected_areas
from lava.datasets.proximity import (
    prepare_road_proximity,
    prepare_substation_proximity,
)
from lava.datasets.wind_solar_atlas import prepare_solar_atlas, prepare_wind_atlas

# Record the starting time
start_time = time.time()

# Suppress specific noisy INFO logs from openeo
# logging.getLogger("openeo.config").setLevel(logging.WARNING)
# logging.getLogger("openeo.rest.connection").setLevel(logging.WARNING)


with open(PROJECT_ROOT / "configs" / "config.yaml", "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

# Load advanced data prep settings
advanced_config_path = os.path.join(
    PROJECT_ROOT, "configs", "advanced_settings", "advanced_data_prep_settings.yaml"
)
if not os.path.exists(advanced_config_path):
    advanced_config_path = os.path.join(
        PROJECT_ROOT,
        "configs",
        "advanced_settings",
        "advanced_data_prep_settings_template.yaml",
    )
with open(advanced_config_path, "r", encoding="utf-8") as f:
    config_advanced = yaml.load(f, Loader=yaml.FullLoader)

# -------data config-------
consider_coastlines = config["coastlines"]
consider_railways = config["railways"]
consider_roads = config["roads"]
consider_airports = config["airports"]
consider_waterbodies = config["waterbodies"]
consider_military = config["military"]
population_data = config.get("population_source", 0)
consider_wind_atlas = config["wind_atlas"]
consider_solar_atlas = config["solar_atlas"]
compute_substation_proximity = config.get("compute_substation_proximity", 0)
compute_road_proximity = config.get("compute_road_proximity", 0)
compute_terrain_ruggedness = config.get("compute_terrain_ruggedness", 0)
consider_additional_exclusion_polygons = config[
    "additional_exclusion_polygons_folder_name"
]
consider_additional_exclusion_rasters = config[
    "additional_exclusion_rasters_folder_name"
]
consider_additional_inclusion_polygons = config.get(
    "additional_inclusion_polygons_folder_name"
)
consider_additional_inclusion_rasters = config.get(
    "additional_inclusion_rasters_folder_name"
)
CRS_manual = config["CRS_manual"]  # if None use empty string
consider_protected_areas = config["protected_areas_source"]
OSM_source = config["OSM_source"]  # either 'geofabrik' or 'overpass'
consider_forest_density = config.get("forest_density", 0)
buildings_filename = config.get(
    "buildings_filename", None
)  # optional, only needed if local file is used as source

# ----------------------------
study_region_name = (
    config.get("study_region_name") or "unknown_region_name"
)  # when no name is set in config, use default
OSM_folder_name = config[
    "OSM_folder_name"
]  # usually same as country_code, only needed if OSM is to be considered
DEM_filename = config["DEM_filename"]

# use ADM boundary
adm_source = config.get("GADM_source", "gadm")  # gadm or wb (WorldBank via space2stats)
adm_region_name = config.get(
    "GADM_region_name"
)  # if country is studied, then use country name
country_code = config["country_code"]
adm_level = config.get("GADM_level")
# or use custom region
custom_study_area_filename = config.get("custom_study_area_filename", None)

# Initialize parser for command line arguments and define arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default=study_region_name, help="study region name")
parser.add_argument(
    "--method",
    default="manual",
    help="method to run the script, e.g., snakemake or manual",
)
args = parser.parse_args()

# Clean region name (uses --region if passed via snakemake, otherwise config default)
region_name_clean = clean_region_name(args.region)
print(f"Running ({args.method}) - region={region_name_clean}")

##################################################
# north facing pixels
X = config_advanced["X"]
Y = config_advanced["Y"]
Z = config_advanced["Z"]


# Record the starting time
start_time = time.time()

# Get paths to data files or folders
dirname = str(PROJECT_ROOT)
raw_spatial_data_folder = os.path.join(dirname, "Raw_Spatial_Data")
demRasterPath = os.path.join(raw_spatial_data_folder, "DEM", DEM_filename)
if OSM_source == "geofabrik":
    OSM_data_path = os.path.join(raw_spatial_data_folder, "OSM", OSM_folder_name)

# Define output directories
output_dir = os.path.join(dirname, "data", f"{region_name_clean}")
os.makedirs(output_dir, exist_ok=True)

# Set up logging
log_file_path = os.path.join(output_dir, "data-prep.log")
file_handler = logging.FileHandler(log_file_path, mode="w")
file_handler.setLevel(logging.DEBUG)  # file can record everything

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)  # terminal only shows WARNING and above

logging.basicConfig(
    handlers=[file_handler, stream_handler],
    level=logging.INFO,  # minimum level for logger; handlers override this
    format="%(levelname)s:%(name)s:%(message)s",
)  # source: https://stackoverflow.com/questions/13733552/logger-configuration-to-log-to-file-and-print-to-stdout

logging.info(f"\nPrepping {region_name_clean}...")

# Resolve {region_name} placeholder in GADM_region_name if present
if adm_region_name and "{region_name}" in adm_region_name:
    adm_region_name = adm_region_name.format(region_name=args.region)

# get region boundary
custom_study_area_filepath = None
if custom_study_area_filename:
    # check if dynamic filename is used
    if "{region_name}" in custom_study_area_filename:
        custom_study_area_filename = custom_study_area_filename.format(
            region_name=region_name_clean
        )
    print(f"\nUsing custom study area filename: {custom_study_area_filename}")
    custom_study_area_filepath = os.path.join(
        raw_spatial_data_folder, "custom_study_area", custom_study_area_filename
    )
    region = get_study_area_polygon(
        custom_polygon_path=custom_study_area_filepath,
    )
    logging.info("using custom polygon for study area")
else:
    region = get_study_area_polygon(
        source=adm_source,
        country_code=country_code,
        level=adm_level,
        admin_name=adm_region_name,
    )
    if adm_source == "gadm" and adm_level == 0:
        logging.info("using whole country as study area (source: GADM)")
    elif adm_source == "gadm":
        logging.info("using admin area within country as study area (source: GADM)")
    else:
        logging.info(
            "using admin area within country as study area (source: World Bank)"
        )

# simplify polygon of study area (openeo can only handle polygons up to a certain size)
try:
    region["geometry"] = region["geometry"].simplify(
        config_advanced["study_area"]["tolerance"], preserve_topology=True
    )
except Exception as e:
    logging.warning(f"Polygon of study could not be simplified: {e}")
region.to_file(
    os.path.join(output_dir, f"{region_name_clean}_EPSG4326.geojson"),
    driver="GeoJSON",
    encoding="utf-8",
)


# calculate UTM zone based on representative point of country
representative_point = region.representative_point().iloc[0]
latitude, longitude = representative_point.y, representative_point.x
EPSG = int(
    32700 - round((45 + latitude) / 90, 0) * 100 + round((183 + longitude) / 6, 0)
)
# if EPSG was set manual in the beginning then use that one
if CRS_manual:
    local_crs_obj = CRS.from_user_input(
        CRS_manual
    )  # Accepts 'EPSG:3035', 'ESRI:102003', WKT, or PROJ strings
    logging.info(f"Using manually set CRS: {local_crs_obj.to_string()}")
else:
    local_crs_obj = CRS.from_user_input(EPSG)
    logging.info(f"Local CRS to be used: {local_crs_obj.to_string()}")
print(local_crs_obj)

# Extract tag for filename, e.g., 'EPSG3035' or 'ESRI102003'
auth = local_crs_obj.to_authority()
local_crs_tag = "".join(auth) if auth else local_crs_obj.to_string().replace(":", "_")
save_crs(
    local_crs_obj,
    os.path.join(output_dir, f"{region_name_clean}_local_CRS.wkt"),
)

# reproject country to defined projected CRS
region.to_crs(local_crs_obj, inplace=True)
region.to_file(
    os.path.join(output_dir, f"{region_name_clean}_{local_crs_tag}.geojson"),
    driver="GeoJSON",
    encoding="utf-8",
)
# also have region polygon in equal-area Mollweide projection
region_mollweide = region.to_crs(CRS.from_user_input("ESRI:54009"))

# set global CRS EPSG:4326
global_crs_obj = CRS.from_user_input("4326")
auth = global_crs_obj.to_authority()
global_crs_tag = "".join(auth) if auth else global_crs_obj.to_string().replace(":", "_")
save_crs(
    global_crs_obj,
    os.path.join(output_dir, f"{region_name_clean}_global_CRS.wkt"),
)

# calculate bounding box with 1000m buffer (region needs to be in projected CRS so meters are the unit)
region_copy = region
region_copy["buffered"] = region_copy.buffer(1000)
region_buffered_4000 = region_copy.buffer(
    4000
)  # have DEM larger than study area to account for Ruggedness Index calculation (convert to 4326 below)
# Convert buffered region back to EPSC 4326 to get bounding box latitude and longitude
region_buffered_4326 = region_copy.set_geometry("buffered").to_crs(global_crs_obj)
region_buffered_4000 = region_buffered_4000.to_crs(global_crs_obj)
bounding_box = region_buffered_4326["buffered"].total_bounds
logging.info(
    f"Bounding box in EPSG 4326: \nminx: {bounding_box[0]}, miny: {bounding_box[1]}, maxx: {bounding_box[2]}, maxy: {bounding_box[3]}"
)


# Convert region back to EPSC 4326 to trim raster files and clip polygons
region.to_crs(global_crs_obj, inplace=True)

study_area = StudyArea(
    name=region_name_clean,
    boundary_4326=region,
    local_crs=local_crs_obj,
    raw_spatial_data_folder=Path(raw_spatial_data_folder),
    output_dir=Path(output_dir),
    boundary_mollweide=region_mollweide,
    boundary_buffered_4000_4326=region_buffered_4000,
    bounding_box_4326=bounding_box,
)

# clip global oceans and seas file to study region for coastlines
if consider_coastlines == 1:
    prepare_coastlines(study_area)

# OSM data
if OSM_source == "geofabrik":
    prepare_osm_geofabrik(study_area, config_advanced, OSM_data_path)
elif OSM_source == "overpass":
    # Load all possible OSM features directly from config, filter based on config flags
    osm_features_config = config_advanced.get("osm_features_config", {})
    selected_osm_features_dict = {
        key: val for key, val in osm_features_config.items() if config.get(f"{key}", 0)
    }
    prepare_osm_overpass(
        study_area, selected_osm_features_dict, config_advanced["force_osm_download"]
    )

# create proximity rasters if data exists and calculation is enabled
if compute_substation_proximity:
    prepare_substation_proximity(study_area)
if compute_road_proximity:
    prepare_road_proximity(study_area)

# additional exclusion / inclusion layers
if consider_additional_exclusion_polygons:
    prepare_additional_exclusion_polygons(
        study_area, consider_additional_exclusion_polygons
    )
if consider_additional_exclusion_rasters:
    prepare_additional_exclusion_rasters(
        study_area, consider_additional_exclusion_rasters
    )
if consider_additional_inclusion_polygons:
    prepare_additional_inclusion_polygons(
        study_area, consider_additional_inclusion_polygons
    )
if consider_additional_inclusion_rasters:
    prepare_additional_inclusion_rasters(
        study_area, consider_additional_inclusion_rasters
    )

# population data
if population_data == "worldpop":
    prepare_population_worldpop(study_area, country_code, config["population_year"])
if population_data == "file":
    prepare_population_file(study_area, country_code, config["population_year"])

# landcover
if config["landcover_source"] == "openeo":
    # use region file in EPSG 4326 because openeo default file is in 4326
    if custom_study_area_filename:
        landcover_aoi_path = custom_study_area_filepath
    else:
        landcover_aoi_path = os.path.join(
            output_dir, f"{region_name_clean}_EPSG4326.geojson"
        )
    processed_landcover_filePath = prepare_landcover_openeo(
        study_area, landcover_aoi_path, config["resolution_landcover"]
    )
if config["landcover_source"] == "file":
    processed_landcover_filePath = prepare_landcover_file(
        study_area, config["landcover_filename"]
    )

# DEM and derivatives
prepare_dem(study_area, demRasterPath, compute_terrain_ruggedness, X, Y, Z)

# protected areas
if consider_protected_areas == "WDPA" or consider_protected_areas == "file":
    prepare_protected_areas(
        study_area,
        consider_protected_areas,
        country_code,
        config.get("protected_areas_filename"),
    )

# forest density (optional; raster clipped/reprojected if filename is provided)
if consider_forest_density == 1:
    prepare_forest_density(study_area, config.get("forest_density_filename", 0))

# global wind and solar atlas
if consider_wind_atlas == 1:
    prepare_wind_atlas(study_area, country_code)
if consider_solar_atlas == 1:
    prepare_solar_atlas(study_area)

# buildings raster
if buildings_filename:
    prepare_buildings(study_area, buildings_filename)


print("\nDone!")

elapsed = time.time() - start_time
logging.info(f"elapsed seconds: {round(elapsed, 2)}")
print(f"elapsed time: {elapsed}")

# Print all error messages from the log file
with open(log_file_path, "r") as log_file:
    content = log_file.read()
    if "ERROR" in content:
        print("\nErrors for following data:")
        log_file.seek(0)
        for line in log_file:
            if "ERROR" in line:
                print(line.strip())
