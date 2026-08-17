import atlite
from pyproj import CRS
import time
import numpy as np
import json
import pickle
import os
import argparse
import geopandas as gpd
from atlite.gis import shape_availability
import rasterio
import yaml
from utils.data_preprocessing import log_scenario_run
from utils.region_names import canonical_region_name
from rasterstats import zonal_stats
from utils.raster_analysis import area_filter, overlay_value_raster
from utils.inclusion_layers import (
    apply_inclusion_layer_overrides,
    compute_combined_inclusion_mask,
    discover_processed_inclusion_layers,
    parse_inclusion_layer_settings,
)
from utils.tech_config import load_tech_config

# Record the starting time
start_time = time.time()

dirname = os.getcwd()
# main_dir = os.path.join(dirname, '..')
config_file = os.path.join("configs", "config.yaml")
# load the configuration file
with open(config_file, "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

# Set up argument parser; exclusion requires all runtime inputs from the CLI.
parser = argparse.ArgumentParser()
parser.add_argument("--region", required=True, help="region name")
parser.add_argument(
    "--method",
    default="manual",
    help="method to run the script, e.g., snakemake or manual",
)
parser.add_argument("--scenario", required=True, help="scenario name")
parser.add_argument("--technology", required=True, help="technology")
args = parser.parse_args()

region_name_clean = canonical_region_name(args.region)
technology = args.technology
scenario = args.scenario

# If running via Snakemake, use the region name and folder name from command line arguments.
if args.method == "snakemake":
    print(f"\nExclusion for {region_name_clean}")
    print(
        f"Running via snakemake - measures: region={region_name_clean}, technology={technology}, scenario={scenario}"
    )
else:
    # If run from VS Code Run button or terminal (manual), use CLI args.
    print(f"\nExclusion for {region_name_clean}")
    print(
        f"Running manually - measures: region={region_name_clean}, technology={technology}, scenario={scenario}"
    )


# load the technology specific configuration file
tech_config = load_tech_config(technology, scenario)

resampled = ""  #'_resampled'

# construct folder paths
dirname = os.getcwd()
data_path = os.path.join(dirname, "data", region_name_clean)
log_scenario_run(region_name_clean, technology, scenario, log_dir=data_path)
data_path_OSM = os.path.join(dirname, "data", region_name_clean, "OSM_Infrastructure")
data_from_DEM = os.path.join(data_path, "derived_from_DEM")
OSM_source = config["OSM_source"]
raw_data_path = os.path.join(dirname, "Raw_Spatial_Data")


# Load the CRS
# geo CRS
with open(os.path.join(data_path, region_name_clean + "_global_CRS.pkl"), "rb") as file:
    global_crs_obj = pickle.load(file)
# projected CRS
with open(os.path.join(data_path, region_name_clean + "_local_CRS.pkl"), "rb") as file:
    local_crs_obj = pickle.load(file)
# overwrite local CRS if specified in tech_config
if tech_config["projection_manual"] is not None:
    local_crs_obj = CRS.from_user_input(tech_config["projection_manual"])


print(f"geo CRS: {global_crs_obj}; projected CRS: {local_crs_obj}")

# Extract tag for filename, e.g., 'EPSG3035' or 'ESRI102003'
auth = global_crs_obj.to_authority()
global_crs_tag = "".join(auth) if auth else global_crs_obj.to_string().replace(":", "_")
auth = local_crs_obj.to_authority()
local_crs_tag = "".join(auth) if auth else local_crs_obj.to_string().replace(":", "_")


# load pixel size
if tech_config["resolution_manual"] is not None:
    res = tech_config["resolution_manual"]
else:
    with open(
        os.path.join(data_path, f"pixel_size_{region_name_clean}_{local_crs_tag}.json"),
        "r",
    ) as fp:
        res = json.load(fp)


regionPath = os.path.join(data_path, f"{region_name_clean}_{global_crs_tag}.geojson")
region = gpd.read_file(regionPath)
region = region.to_crs(local_crs_obj)

# perform exclusions

# raster can be in different CRS than exclusioncontainer, it is co-registered by atlite!
# same applies for vector data

info_list_exclusion = []
info_list_not_selected = []
info_list_not_available = []

# initiate Exclusion container
excluder = atlite.ExclusionContainer(crs=local_crs_obj, res=res)


# --- Landcover ---
landcoverPath = os.path.join(
    data_path,
    f"landcover_{config['landcover_source']}_{region_name_clean}_{global_crs_tag}.tif",
)
if tech_config["landcover_codes"] and os.path.isfile(landcoverPath):
    input_codes = tech_config["landcover_codes"]
    for key, value in input_codes.items():
        excluder.add_raster(landcoverPath, codes=key, buffer=value, crs=global_crs_obj)
    info_list_exclusion.append(
        f"landcover codes which are excluded (code, buffer in meters): {input_codes}"
    )
elif tech_config["landcover_codes"] and not os.path.isfile(landcoverPath):
    info_list_not_available.append("landcover")
else:
    info_list_not_selected.append("landcover")


# --- Elevation ---
demRasterPath = os.path.join(
    data_path, f"DEM_{region_name_clean}_{global_crs_tag}{resampled}.tif"
)
param = tech_config["max_elevation"]
if os.path.isfile(demRasterPath) and param is not None:
    excluder.add_raster(demRasterPath, codes=range(param, 10000), crs=global_crs_obj)
    info_list_exclusion.append(f"max elevation: {param}")
elif os.path.isfile(demRasterPath) and param is None:
    info_list_not_selected.append("DEM")
else:
    info_list_not_available.append("DEM")


# --- Slope ---
slopeRasterPath = os.path.join(
    data_from_DEM, f"slope_{region_name_clean}_{global_crs_tag}{resampled}.tif"
)
param = tech_config["max_slope"]
if os.path.isfile(slopeRasterPath) and param is not None:
    excluder.add_raster(slopeRasterPath, codes=range(param, 90), crs=global_crs_obj)
    info_list_exclusion.append(f"max slope: {param}")
elif os.path.isfile(slopeRasterPath) and param is None:
    info_list_not_selected.append("slope")
else:
    info_list_not_available.append("slope")


# --- Buildings ---
buildingsRasterPath = os.path.join(
    data_path, f"buildings_{region_name_clean}_ESRI54009.tif"
)
param = tech_config["max_buildings_footprint"]
if os.path.isfile(buildingsRasterPath) and param is not None:
    excluder.add_raster(
        buildingsRasterPath,
        codes=range(param, 101),
        buffer=tech_config["buildings_buffer"],
        crs=rasterio.crs.CRS.from_user_input("ESRI:54009"),
    )
    info_list_exclusion.append(f"max buildings footprint: {param}")
elif os.path.isfile(buildingsRasterPath) and param is None:
    info_list_not_selected.append("buildings raster")
else:
    info_list_not_available.append("buildings raster")


# --- Terrain Ruggedness ---
terrain_ruggedness_path = os.path.join(
    data_from_DEM, f"TerrainRuggednessIndex_{region_name_clean}_{global_crs_tag}.tif"
)
param = tech_config["max_terrain_ruggedness"]
if os.path.isfile(terrain_ruggedness_path) and param is not None:
    excluder.add_raster(
        terrain_ruggedness_path, codes=range(0, param), invert=True, crs=global_crs_obj
    )
    info_list_exclusion.append(f"max terrain ruggedness: {param}")
elif os.path.isfile(terrain_ruggedness_path) and param is None:
    info_list_not_selected.append("terrain_ruggedness")
else:
    info_list_not_available.append("terrain_ruggedness")


# --- Population ---
def lower_end_filter(mask):
    """Filter out values below a lower end."""
    lower_end = tech_config["max_population"]
    return mask > lower_end


populationPath = os.path.join(
    data_path, f"population_{region_name_clean}_{global_crs_tag}.tif"
)
param = tech_config.get("max_population")
if os.path.isfile(populationPath) and param is not None:
    excluder.add_raster(
        populationPath, codes=lower_end_filter, crs=global_crs_obj, nodata=None
    )  # nodata=None, otherwise no data values get excluded (assumption: in no data pixels there is no population)
    info_list_exclusion.append(f"max population per pixel: {param}")
elif os.path.isfile(populationPath) and param is None:
    info_list_not_selected.append("population")
else:
    info_list_not_available.append("population")


# --- North Facing ---
northfacingRasterPath = os.path.join(
    data_from_DEM, f"north_facing_{region_name_clean}_{global_crs_tag}{resampled}.tif"
)
param = tech_config.get("north_facing_pixels", None)
if os.path.isfile(northfacingRasterPath) and param is not None:
    excluder.add_raster(northfacingRasterPath, codes=1, crs=global_crs_obj)
    info_list_exclusion.append("north facing pixels")
elif os.path.isfile(northfacingRasterPath) and param is None:
    info_list_not_selected.append("nfacing")
else:
    info_list_not_available.append("nfacing")


# --- Wind Speed ---
def wind_filter(mask):
    """Filter out values outside the desired wind speed range."""
    min_val = tech_config["min_wind_speed"]
    max_val = tech_config["max_wind_speed"]
    if min_val is not None and max_val is not None:
        return (mask < min_val) | (mask > max_val)
    elif min_val is not None:
        return mask < min_val
    elif max_val is not None:
        return mask > max_val


windRasterPath = os.path.join(
    data_path, f"wind_{region_name_clean}_{global_crs_tag}{resampled}.tif"
)
if technology in ["onshorewind", "offshorewind"] and (
    tech_config["min_wind_speed"] is not None
    or tech_config["max_wind_speed"] is not None
):
    min_wind_speed = tech_config["min_wind_speed"]
    max_wind_speed = tech_config["max_wind_speed"]
    if os.path.isfile(windRasterPath):
        excluder.add_raster(windRasterPath, codes=wind_filter, crs=global_crs_obj)
        if min_wind_speed is not None and max_wind_speed is not None:
            info = f"min wind speed: {min_wind_speed}, max wind speed: {max_wind_speed}"
        elif min_wind_speed is not None:
            info = f"min wind speed: {min_wind_speed}"
        elif max_wind_speed is not None:
            info = f"max wind speed: {max_wind_speed}"
        info_list_exclusion.append(info)
    else:
        info_list_not_available.append("wind")


# --- Solar Production ---
def solar_filter(mask):  # desired yearly, specific solar production (kWh/m²/year)
    """Filter out values outside the desired solar production range (kWh/m²/year)."""
    min_val = tech_config.get("min_solar_production")
    max_val = tech_config.get("max_solar_production")
    if min_val is not None and max_val is not None:
        return (mask < min_val) | (mask > max_val)
    elif min_val is not None:
        return mask < min_val
    elif max_val is not None:
        return mask > max_val


solarRasterPath = os.path.join(
    data_path, f"solar_{region_name_clean}_{global_crs_tag}{resampled}.tif"
)
if technology == "solar" and (
    tech_config.get("min_solar_production") is not None
    or tech_config.get("max_solar_production") is not None
):
    min_solar_production = tech_config.get("min_solar_production")
    max_solar_production = tech_config.get("max_solar_production")
    if os.path.isfile(solarRasterPath):
        excluder.add_raster(solarRasterPath, codes=solar_filter, crs=global_crs_obj)
        if min_solar_production is not None and max_solar_production is not None:
            info = f"min_solar_production: {min_solar_production}, max_solar_production: {max_solar_production}"
        elif min_solar_production is not None:
            info = f"min_solar_production: {min_solar_production}"
        elif max_solar_production is not None:
            info = f"max_solar_production: {max_solar_production}"
        info_list_exclusion.append(info)
    else:
        info_list_not_available.append("solar")


# --- Railways ---
railwaysPath = os.path.join(data_path_OSM, "railways.gpkg")
param = tech_config["railways_buffer"]
if os.path.isfile(railwaysPath) and param is not None:
    excluder.add_geometry(railwaysPath, buffer=param)
    info_list_exclusion.append(f"railways buffer: {param}")
elif os.path.isfile(railwaysPath) and param is None:
    info_list_not_selected.append("railways")
else:
    info_list_not_available.append("railways")


# --- Roads ---
roadsPath = os.path.join(data_path_OSM, "roads.gpkg")
param = tech_config["roads_buffer"]
if os.path.isfile(roadsPath) and param is not None:
    excluder.add_geometry(roadsPath, buffer=param)
    info_list_exclusion.append(f"roads buffer: {param}")
elif os.path.isfile(roadsPath) and param is None:
    info_list_not_selected.append("roads")
else:
    info_list_not_available.append("roads")


# --- Airports ---
airportsPath = os.path.join(data_path_OSM, "airports.gpkg")
param = tech_config["airports_buffer"]
if os.path.isfile(airportsPath) and param is not None:
    excluder.add_geometry(airportsPath, buffer=param)
    info_list_exclusion.append(f"airports buffer: {param}")
elif os.path.isfile(airportsPath) and param is None:
    info_list_not_selected.append("airports")
else:
    info_list_not_available.append("airports")


# --- Waterbodies ---
waterbodiesPath = os.path.join(data_path_OSM, "waterbodies.gpkg")
param = tech_config["waterbodies_buffer"]
if os.path.isfile(waterbodiesPath) and param is not None:
    excluder.add_geometry(waterbodiesPath, buffer=param)
    info_list_exclusion.append(f"waterbodies buffer: {param}")
elif os.path.isfile(waterbodiesPath) and param is None:
    info_list_not_selected.append("waterbodies")
else:
    info_list_not_available.append("waterbodies")


# --- Military ---
militaryPath = os.path.join(data_path_OSM, "military.gpkg")
param = tech_config["military_buffer"]
if os.path.isfile(militaryPath) and param is not None:
    excluder.add_geometry(militaryPath, buffer=param)
    info_list_exclusion.append(f"military buffer: {param}")
elif os.path.isfile(militaryPath) and param is None:
    info_list_not_selected.append("military")
else:
    info_list_not_available.append("military")


# --- Coastlines ---
coastlinesPath = os.path.join(
    data_path, f"goas_{region_name_clean}_{global_crs_tag}.gpkg"
)
param = tech_config["coastlines_buffer"]
if os.path.isfile(coastlinesPath) and param is not None:
    excluder.add_geometry(coastlinesPath, buffer=param)
    info_list_exclusion.append(f"coastlines buffer: {param}")
elif os.path.isfile(coastlinesPath) and param is None:
    info_list_not_selected.append("coastlines")
else:
    info_list_not_available.append("coastlines")


# --- Protected Areas ---
protectedAreasPath = os.path.join(
    data_path,
    f"protected_areas_{config['protected_areas_source']}_{region_name_clean}_{global_crs_tag}.gpkg",
)
param = tech_config["protectedAreas_buffer"]
if os.path.isfile(protectedAreasPath) and param is not None:
    excluder.add_geometry(protectedAreasPath, buffer=param)
    info_list_exclusion.append(f"protected areas buffer: {param}")
elif os.path.isfile(protectedAreasPath) and param is None:
    info_list_not_selected.append("protectedAreas")
else:
    info_list_not_available.append("protectedAreas")


# --- Forest Density ---
forestDensityPath = os.path.join(
    data_path, f"forest_density_{region_name_clean}_{global_crs_tag}.tif"
)
param = tech_config.get("max_forest_density")
if os.path.isfile(forestDensityPath) and param is not None:
    excluder.add_raster(
        forestDensityPath, codes=range(0, param), invert=True, crs=global_crs_obj
    )
    info_list_exclusion.append(f"max forest density included: {param}")
elif os.path.isfile(forestDensityPath) and param is None:
    info_list_not_selected.append("forestDensity")
else:
    info_list_not_available.append("forestDensity")


# --- Transmission Lines ---
transmissionPath = os.path.join(data_path_OSM, "transmission_lines.gpkg")
param = tech_config["transmission_lines_buffer"]
if os.path.isfile(transmissionPath) and param is not None:
    excluder.add_geometry(transmissionPath, buffer=param)
    info_list_exclusion.append(f"transmission buffer: {param}")
elif os.path.isfile(transmissionPath) and param is None:
    info_list_not_selected.append("transmission")
else:
    info_list_not_available.append("transmission")


# --- Existing Generators ---
generatorsPath = os.path.join(data_path_OSM, "generators.gpkg")
param = tech_config["generators_buffer"]
if os.path.isfile(generatorsPath) and param is not None:
    excluder.add_geometry(generatorsPath, buffer=param)
    info_list_exclusion.append(f"existing generators buffer: {param}")
elif os.path.isfile(generatorsPath) and param is None:
    info_list_not_selected.append("existing generators")
else:
    info_list_not_available.append("existing generators")


# --- Existing Plants ---
plantsPath = os.path.join(data_path_OSM, "plants.gpkg")
param = tech_config["plants_buffer"]
if os.path.isfile(plantsPath) and param is not None:
    excluder.add_geometry(plantsPath, buffer=param)
    info_list_exclusion.append(f"existing plants buffer: {param}")
elif os.path.isfile(plantsPath) and param is None:
    info_list_not_selected.append("existing plants")
else:
    info_list_not_available.append("existing plants")


# --- Additional Exclusion Polygons ---
additional_exclusion_polygons_folderPath = os.path.join(
    data_path, "additional_exclusion_polygons"
)
buffer_config = tech_config.get("additional_exclusion_polygons_buffer")
if os.path.exists(additional_exclusion_polygons_folderPath) and buffer_config:
    for filename in os.listdir(additional_exclusion_polygons_folderPath):
        if filename in buffer_config:  # check if buffer is defined
            buffer_value = buffer_config[filename]
            filepath = os.path.join(additional_exclusion_polygons_folderPath, filename)
            excluder.add_geometry(filepath, buffer=buffer_value)
            info_list_exclusion.append(
                f"additional exclusion polygons file: {filename}: {buffer_value}"
            )
elif os.path.exists(additional_exclusion_polygons_folderPath) and not buffer_config:
    info_list_not_selected.append("additional_exclusion_polygons_buffer")
else:
    info_list_not_available.append("additional_exclusion_polygons_buffer")


# --- Additional Exclusion Rasters ---
additional_exclusion_rasters_folderPath = os.path.join(
    data_path, "additional_exclusion_rasters"
)
buffer_config = tech_config.get("additional_exclusion_rasters_buffer")
if os.path.exists(additional_exclusion_rasters_folderPath) and buffer_config:
    for filename in os.listdir(additional_exclusion_rasters_folderPath):
        if filename in buffer_config:  # check if buffer is defined
            buffer_value = buffer_config[filename]
            filepath = os.path.join(additional_exclusion_rasters_folderPath, filename)
            excluder.add_raster(
                filepath,
                codes=range(0, 1_000_000),
                buffer=buffer_value,
                crs=global_crs_obj,
            )
            info_list_exclusion.append(
                f"additional exclusion raster file: {filename}: {buffer_value}"
            )
elif os.path.exists(additional_exclusion_rasters_folderPath) and not buffer_config:
    info_list_not_selected.append("additional_exclusion_rasters_buffer")
else:
    info_list_not_available.append("additional_exclusion_rasters_buffer")


# INCLUSION

inclusion_layer_groups = []


def register_inclusion_polygon(layer_excluder, layer):
    settings = layer["settings"]
    layer_excluder.add_geometry(
        layer["path"], buffer=settings["buffer"], invert=True
    )


def register_inclusion_raster(layer_excluder, layer):
    settings = layer["settings"]
    layer_excluder.add_raster(
        layer["path"],
        codes=settings["codes"],
        buffer=settings["buffer"],
        crs=global_crs_obj,
        invert=True,
        nodata=settings["nodata"],
    )


def configure_inclusion_layer_group(
    config_key, folder_config_key, layer_type, register_layer
):
    settings = parse_inclusion_layer_settings(tech_config, config_key, layer_type)
    if settings is None or not settings["enabled"]:
        info_list_not_selected.append(config_key)
        return

    source_folder_name = config.get(folder_config_key)
    if not source_folder_name:
        info_list_not_available.append(
            f"{config_key} (no source folder selected in config.yaml)"
        )
        return

    processed_folder = os.path.join(data_path, config_key, source_folder_name)
    layers = discover_processed_inclusion_layers(processed_folder, layer_type)
    if not layers:
        info_list_not_available.append(config_key)
        return

    configured_layers = apply_inclusion_layer_overrides(layers, settings, config_key)
    inclusion_layer_groups.append(
        {
            "config_key": config_key,
            "combine": settings["combine"],
            "layers": configured_layers,
            "register_layer": register_layer,
        }
    )
    for layer in configured_layers:
        info_list_exclusion.append(
            f"{config_key}: {layer['source']} -> {layer['processed']}: "
            f"buffer={layer['settings']['buffer']} "
            f"(combine={settings['combine']})"
        )


configure_inclusion_layer_group(
    "additional_inclusion_polygons",
    "additional_inclusion_polygons_folder_name",
    "polygon",
    register_inclusion_polygon,
)
configure_inclusion_layer_group(
    "additional_inclusion_rasters",
    "additional_inclusion_rasters_folder_name",
    "raster",
    register_inclusion_raster,
)


# --- Substations (Inclusion Buffer) ---
substationsPath = os.path.join(data_path_OSM, "substations.gpkg")
param = tech_config["substations_inclusion_buffer"]
if os.path.isfile(substationsPath) and param is not None:
    excluder.add_geometry(substationsPath, buffer=param, invert=True)
    info_list_exclusion.append(f"substations inclusion buffer: {param}")
elif os.path.isfile(substationsPath) and param is None:
    info_list_not_selected.append("substations")
else:
    info_list_not_available.append("substations")


# --- Transmission Lines (Inclusion Buffer) ---
param = tech_config["transmission_inclusion_buffer"]
if os.path.isfile(transmissionPath) and param is not None:
    excluder.add_geometry(transmissionPath, buffer=param, invert=True)
    info_list_exclusion.append(f"transmission inclusion buffer: {param}")
elif os.path.isfile(transmissionPath) and param is None:
    info_list_not_selected.append("transmission inclusion")
else:
    info_list_not_available.append("transmission inclusion")


# --- Roads (Inclusion Buffer) ---
param = tech_config["roads_inclusion_buffer"]
if os.path.isfile(roadsPath) and param is not None:
    excluder.add_geometry(roadsPath, buffer=param, invert=True)
    info_list_exclusion.append(f"roads inclusion buffer: {param}")
elif os.path.isfile(roadsPath) and param is None:
    info_list_not_selected.append("roads inclusion")
else:
    info_list_not_available.append("roads inclusion")


# data info
print("\nfollowing data was not found in data folder:")
for item in info_list_not_available:
    print("- ", item)
print("\nfollowing data was not selected in config:")
for item in info_list_not_selected:
    print("- ", item)


# calculate available areas
print("\nperforming exclusions...")
masked, transform = shape_availability(region.geometry, excluder)

# Apply the same mask-combination workflow to polygon and raster groups. Each
# layer still uses Atlite's native geometry or raster buffering implementation.
for inclusion_group in inclusion_layer_groups:
    inclusion_mask, inclusion_transform = compute_combined_inclusion_mask(
        inclusion_group["layers"],
        inclusion_group["combine"],
        inclusion_group["register_layer"],
        region.geometry,
        local_crs_obj,
        res,
    )
    if inclusion_transform != transform or inclusion_mask.shape != masked.shape:
        raise RuntimeError(
            f"{inclusion_group['config_key']} could not be aligned with the "
            "exclusion grid"
        )
    masked &= inclusion_mask
# masked, transform = shape_availability_reprojected(region.geometry, excluder, dst_transform=transform_lc, dst_crs=local_crs_obj, dst_shape=shape)

print("\nfollowing data was considered during exclusion:")
for item in info_list_exclusion:
    print("- ", item)

min_pixels_connected = tech_config["min_pixels_connected"]
# min_pixels_x=tech_config['min_pixels_x']
# min_pixels_y=tech_config['min_pixels_y']

masked_area_filtered = area_filter(masked, min_size=min_pixels_connected)
# masked_area_filtered = area_filter2(masked,min_x=5, min_y=5)

# array to be used
array = masked_area_filtered

available_area = masked_area_filtered.sum() * excluder.res**2
eligible_share = available_area / region.geometry.item().area
available_area_km2 = available_area * 1e-6

# print results
print(f"\nThe eligibility share is: {eligible_share:.2%}")
print(f"The available area is: {available_area_km2:.2f} km²")
if tech_config["deployment_density"]:
    power_potential = available_area_km2 * tech_config["deployment_density"]
    print(f"Power potential: {power_potential:.2} MW")

# Define output directory
output_dir = os.path.join(data_path, "available_land")
os.makedirs(output_dir, exist_ok=True)

# --- Save binary (0/1) available-land raster ---
binary_array = array.astype(np.uint8)
binary_metadata = {
    "driver": "GTiff",
    "dtype": "uint8",
    "nodata": 0,
    "width": array.shape[1],
    "height": array.shape[0],
    "count": 1,
    "crs": local_crs_obj,
    "transform": transform,
    "compress": "LZW",
}
output_file_available_land = os.path.join(
    output_dir,
    f"{region_name_clean}_{technology}_{scenario}_available_land.tif",
)
with rasterio.open(output_file_available_land, "w", **binary_metadata) as dst:
    dst.write(binary_array, 1)

# --- Save colored value raster (wind speed / PV output) for wind and solar technologies ---
_value_raster_map = {
    "onshorewind": windRasterPath,
    "offshorewind": windRasterPath,
    "solar": solarRasterPath,
}
value_raster_path = _value_raster_map.get(technology)

if value_raster_path is not None and os.path.isfile(value_raster_path):
    with rasterio.open(value_raster_path) as src:
        src_array = src.read(1)
        src_transform = src.transform
        src_crs = src.crs
        src_nodata = src.nodata
    values_array = overlay_value_raster(
        array, transform, local_crs_obj, src_array, src_transform, src_crs, src_nodata
    )
    output_file_values = os.path.join(
        output_dir,
        f"{region_name_clean}_{technology}_{scenario}_available_land_ResourceValues.tif",
    )
    with rasterio.open(
        output_file_values,
        "w",
        driver="GTiff",
        dtype="float32",
        nodata=float("nan"),
        width=array.shape[1],
        height=array.shape[0],
        count=1,
        crs=local_crs_obj,
        transform=transform,
        compress="deflate",
        predictor=3,
    ) as dst:
        dst.write(values_array, 1)


# model area stats
if config["model_areas_filename"]:
    available_area_raster_filePath = os.path.join(output_file_available_land)

    modelAreasPath = os.path.join(
        dirname, "Raw_Spatial_Data", "model_areas", f"{config['model_areas_filename']}"
    )
    model_areas = gpd.read_file(modelAreasPath)
    model_areas.to_crs(local_crs_obj, inplace=True)

    stats = zonal_stats(model_areas, available_area_raster_filePath, stats=["sum"])

    model_areas["pixel_count"] = [list(d.values())[0] for d in stats]
    model_areas["available_area_m2"] = model_areas["pixel_count"] * excluder.res**2
    model_areas["available_area_km2"] = model_areas["pixel_count"] * 1e-6
    if config["deployment_density"]:
        model_areas["power_potential_MW"] = (
            model_areas["available_area_m2"] * 1e-6
        ) * config["deployment_density"]

    # create summary table
    first_column = model_areas.columns[0]
    columns = [
        first_column,
        "pixel_count",
        "available_area_m2",
        "available_area_km2",
        "power_potential_MW",
    ]
    subset = model_areas[columns]
    print("\npotentials in model areas:")
    print(subset.to_string(index=False))

elapsed = time.time() - start_time
print(f"elapsed time: {elapsed}")

# save info in textfile
with open(
    os.path.join(
        output_dir, f"{region_name_clean}_{technology}_{scenario}_exclusion_info.txt"
    ),
    "w",
) as file:
    file.write(f"{technology}")
    file.write(f"\nscenario: {scenario}")
    file.write(f"\nresolution in m: {res}")
    file.write(f"\ncalculation time in s: {elapsed}")
    file.write(f"\nmin pixels connected: {min_pixels_connected}\n\n")
    for item in info_list_exclusion:
        file.write(f"{item}\n")
    file.write(f"\neligibility share: {eligible_share:.2%}")
    file.write(f"\navailable area: {available_area_km2:.2f} km2")
    file.write(f"\npower potential: {power_potential:.2} MW")

    if config["model_areas_filename"]:
        # Write table from GeoDataFrame subset
        file.write("\n\nResults for model areas:\n")

        file.write(subset.to_string(index=False))


# save info in JSON file for easier retrieval
info_data = {
    "technology": technology,
    "scenario": scenario,
    "calculation_time_seconds": float(elapsed),
    "min_pixels_connected": int(min_pixels_connected),
    "info_list": info_list_exclusion,
    "eligibility_share": float(eligible_share),
    "study_area_m2": float(region.geometry.item().area),
    "available_area_m2": float(available_area),
    "available_area_km2": float(available_area_km2),
    "power_potential_MW": float(power_potential),
}

if config["model_areas_filename"]:
    # Include summary table from GeoDataFrame subset
    info_data["model_areas"] = subset.to_dict(orient="records")

with open(
    os.path.join(
        output_dir,
        f"{region_name_clean}_{technology}_{scenario}_exclusion_info.json",
    ),
    "w",
) as file:
    json.dump(info_data, file, indent=2)
