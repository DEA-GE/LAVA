import rasterio
import numpy as np
import pandas as pd
import warnings
import pickle
import os
import yaml
import rasterio
import argparse
import itertools
import matplotlib.pyplot as plt
import json
from rasterio.warp import reproject, Resampling
from rasterio.io import MemoryFile
from utils.data_preprocessing import clean_region_name, rel_path

#------------------------------------------- Functions -------------------------------------------

# Transform raster based on a given raster
def align_to_reference(src, ref):
    """
    Reproject and resample `src` to match `ref` (CRS, transform, shape).
    Returns a rasterio in-memory dataset aligned to `ref`.

    Parameters:
        src: rasterio dataset to reproject
        ref: rasterio dataset to match

    Returns:
        rasterio.io.DatasetReader (in-memory)
    """
    dtype = src.dtypes[0]
    nodata = src.nodata if src.nodata is not None else 0

    dst_array = np.full((ref.height, ref.width), nodata, dtype=dtype)

    reproject(
        source=src.read(1),
        destination=dst_array,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=ref.transform,
        dst_crs=ref.crs,
        resampling=Resampling.nearest,
        dst_nodata=nodata,
    )

    # Change nan to zero
    dst_array[np.isnan(dst_array)] = 0
    return dst_array

def check_alignment(raster_paths):
    """
    Check if all rasters have the same CRS, transform, width, and height.
    
    Parameters:
        raster_paths (list of str): List of file paths to rasters.

    Returns:
        bool: True if all rasters are aligned, False otherwise.
        str: Message explaining the result.
    """

    with rasterio.open(raster_paths[0]) as ref:
        ref_crs = ref.crs
        ref_transform = ref.transform
        ref_shape = (ref.width, ref.height)

    for path in raster_paths[1:]:
        with rasterio.open(path) as src:
            if src.crs != ref_crs:
                return False, f"CRS mismatch: {path}"
            if src.transform != ref_transform:
                return False, f"Transform mismatch: {path}"
            if (src.width, src.height) != ref_shape:
                return False, f"Dimension mismatch: {path}"

    return "All rasters are aligned."

# Function to compute overlap between two masked arrays
def overlap(array1, array2):
    # Compute overlap mask (where both rasters have data)
    overlap_mask = (array1 > 0) & (array2 > 0)

    return overlap_mask.astype(int)

# Function to compute union mask of multiple masked array where at least one has data
def union(arrays):
    """
    Compute union of multiple masked arrays where at least one has data.
    
    Parameters:
        arrays (list of numpy.ndarray): List of masked arrays.

    Returns:
        numpy.ndarray: Union mask where at least one array has data.
    """

    union_mask = np.zeros_like(arrays[0], dtype=int)
    for array in arrays:
        union_mask |= (array > 0)

    return union_mask.astype(int)

# Function to compute difference between two masked arrays
def diff(array1, array2):
    # Compute difference mask (where data1 is present but data2 is not)
    diff_mask = (array1 > 0) & (array2 == 0)

    return diff_mask.astype(int)

# Function to filter a raster based on a value raster and a range
def filter(filter_array, value_array, vmin, vmax):
    vmin=float(vmin)
    vmax=float(vmax)
    filtered_mask = (filter_array > 0) & (value_array >= vmin) & (value_array <= vmax)

    return filtered_mask.astype(int)

def export_raster(array, path, ref):
    """
    Export a numpy array as a raster file.
    
    Parameters:
        array (numpy.ndarray): The data to export.
        path (str): The file path to save the raster.
        ref (rasterio.io.DatasetReader): Reference raster for CRS and transform.
    """
    with rasterio.open(
        path, 'w',
        driver='GTiff',
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=array.dtype,
        crs=local_crs_obj,
        transform=ref.transform,
        nodata=0
    ) as dst:
        dst.write(array, 1)



#------------------------------------------- Initialization -------------------------------------------
dirname = os.getcwd() 
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 

#load the technology specific configuration file
solar_config_file = os.path.join("configs", f"solar.yaml")
with open(solar_config_file, "r", encoding="utf-8") as f:
    solar_config = yaml.load(f, Loader=yaml.FullLoader)
onshorewind_config_file = os.path.join("configs", f"onshorewind.yaml")
with open(onshorewind_config_file, "r", encoding="utf-8") as f:
    onshorewind_config = yaml.load(f, Loader=yaml.FullLoader)

region_folder_name = config['region_folder_name']
region_name = config['region_name'] #if country is studied, then use country name
region_name = clean_region_name(region_name)
scenario = config['scenario']

#Initialize parser for command line arguments and define arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default=region_name, help="region name")
parser.add_argument("--region_folder_name", default=region_folder_name, help="region folder name")
parser.add_argument("--method",default="manual", help="method to run the script, e.g., snakemake or manual")
args = parser.parse_args()

# If running via Snakemake, use the region name and folder name from command line arguments
if args.method == "snakemake":
    region_name = args.region
    region_folder_name = args.region_folder_name
    print(f"Running via snakemake - measures: region={region_name}, region_folder_name={region_folder_name}")
else:
    print(f"Running manually - measures: region={region_name}, region_folder_name={region_folder_name}")

data_path = os.path.join(dirname, 'data', region_folder_name)
data_path_available_land = os.path.join(data_path, 'available_land')
data_from_proximity = os.path.join(data_path, 'proximity')

output_path = os.path.join(data_path,"suitability")
if not os.path.exists(output_path):
    os.makedirs(output_path)

# Load the CRS
# geo CRS
with open(os.path.join(data_path, region_name+'_global_CRS.pkl'), 'rb') as file:
        global_crs_obj = pickle.load(file)
# projected CRS
with open(os.path.join(data_path, region_name+'_local_CRS.pkl'), 'rb') as file:
        local_crs_obj = pickle.load(file)

print(f'geo CRS: {global_crs_obj}; projected CRS: {local_crs_obj}')

# Extract tag for filename, e.g., 'EPSG3035' or 'ESRI102003'
auth = global_crs_obj.to_authority()
global_crs_tag = ''.join(auth) if auth else global_crs_obj.to_string().replace(":", "_")
auth = local_crs_obj.to_authority()
local_crs_tag = ''.join(auth) if auth else local_crs_obj.to_string().replace(":", "_")

#--------------------------------------- Data ----------------------------------------
# Data paths
try:
    wind_avail_path = os.path.join(
        data_path_available_land,
        f"{region_name}_onshorewind_{scenario}_available_land_{local_crs_tag}.tif"
    )
except FileNotFoundError:
    print(f"Wind availability raster not found. Both technologies are needed to calculate the suitability.", 
          "Please selected onshorewind in the config and run extension.py again.")
    
try:
    solar_avail_path = os.path.join(
        data_path_available_land,
        f"{region_name}_solar_{scenario}_available_land_{local_crs_tag}.tif"
    )
except FileNotFoundError:
    print(f"Solar availability raster not found. Both technologies are needed to calculate the suitability.", 
          "Please selected solar in the config and run extension.py again.")
    
substation_distance_path = os.path.join(data_from_proximity, f'substation_distance.tif')
landcover_path = os.path.join(data_path, f"landcover_{config['landcover_source']}_{region_name}_{local_crs_tag}.tif")
terrain_ruggedness_path = os.path.join(data_path, f'TerrainRuggednessIndex_{region_name}_{local_crs_tag}.tif')
GWAPath = os.path.join(data_path, f'wind_{region_name}_{local_crs_tag}.tif')
GSAPath = os.path.join(data_path, f'solar_{region_name}_{local_crs_tag}.tif')

# Load rasters
wind_avail = rasterio.open(wind_avail_path)
solar_avail = rasterio.open(solar_avail_path)
substation_distance = rasterio.open(substation_distance_path)
landcover = rasterio.open(landcover_path)
terrain_ruggedness = rasterio.open(terrain_ruggedness_path)
GWA = rasterio.open(GWAPath)
GSA = rasterio.open(GSAPath)

# -------------- Check that rasters are formatted correcly and use same CRS --------------
#check_alignment([wind_avail_path, solar_avail_path, substation_distance_path, landcover, terrain_ruggedness_path, GWAPath, GSAPath])

#---------------- Reprojection and alignment (can be deleted if all rasters are aligned) ----------------
# Reference grid (intersection of all rasters)
ref = landcover # Should be standardized to a region raster or intersection of all rasters
pixel_area_km2 = abs(ref.transform.a * ref.transform.e) / 1e6

#Reproject rasters to a common array
GWA_reproj = align_to_reference(GWA, ref)
GSA_reproj = align_to_reference(GSA, ref)
substation_distance_reproj = align_to_reference(substation_distance, ref)
land_cover_reproj = align_to_reference(landcover, ref)
terrain_ruggedness_reproj = align_to_reference(terrain_ruggedness, ref)
wind_avail_reproj = align_to_reference(wind_avail, ref)
solar_avail_reproj = align_to_reference(solar_avail, ref)

# Cost map calculation
terrain_factor_onshorewind = np.zeros_like(terrain_ruggedness_reproj, dtype=float)
terrain_factor_solar = np.zeros_like(terrain_ruggedness_reproj, dtype=float)

for terrain_type in config["terrain_modifier"]:
    lower, upper = terrain_type['range']
    terrain_mask = (terrain_ruggedness_reproj >= lower) & (terrain_ruggedness_reproj < upper)
    terrain_factor_onshorewind[terrain_mask] = terrain_type['cost']['onshorewind'] - 1
    terrain_factor_solar[terrain_mask] = terrain_type['cost']['solar'] - 1

# Filter land cover and insert into terrain factor where there is data
for landcover_type in config["landcover_modifier"].keys():
    terrain_factor_onshorewind[land_cover_reproj == landcover_type] = config["landcover_modifier"][landcover_type]["onshorewind"] - 1
    terrain_factor_solar[land_cover_reproj == landcover_type] = config["landcover_modifier"][landcover_type]["solar"] - 1
export_raster(terrain_factor_onshorewind, os.path.join(output_path, f'terrain_factor_onshorewind_{region_name}_{local_crs_tag}.tif'), ref)
export_raster(terrain_factor_solar, os.path.join(output_path, f'terrain_factor_solar_{region_name}_{local_crs_tag}.tif'), ref)

substation_factor_onshorewind = substation_distance_reproj / config["average_sub_dist"]['onshorewind'] - 1
substation_factor_solar = substation_distance_reproj / config["average_sub_dist"]['solar'] - 1

export_raster(substation_factor_onshorewind, os.path.join(output_path, f'substation_factor_onshorewind_{region_name}_{local_crs_tag}.tif'), ref)
export_raster(substation_factor_solar, os.path.join(output_path, f'substation_factor_solar_{region_name}_{local_crs_tag}.tif'), ref)

region_factor_onshorewind = config["region_modifier"][region_name]['onshorewind'] - 1
region_factor_solar = config["region_modifier"][region_name]['solar'] - 1

costmap_onshorewind = (1 + terrain_factor_onshorewind * 1) * (1 + substation_factor_onshorewind * 0.1) * (1 + region_factor_onshorewind * 0.1)
costmap_solar = (1 + terrain_factor_solar * 1) * (1 + substation_factor_solar * 0.1) * (1 + region_factor_solar * 0.1)

export_raster(costmap_onshorewind, os.path.join(output_path, f'costmap_onshorewind_{region_name}_{local_crs_tag}.tif'), ref)
export_raster(costmap_solar, os.path.join(output_path, f'costmap_solar_{region_name}_{local_crs_tag}.tif'), ref)

# Resource grades
SG = solar_config["sg_thr"].keys()
WG = onshorewind_config["wg_thr"].keys()
SG_WG_comb = list(itertools.product(SG, WG))  # All combinations of SG and WG

wind_grades = {wg: filter(wind_avail_reproj, GWA_reproj, onshorewind_config["wg_thr"][wg][0], onshorewind_config["wg_thr"][wg][1]) for wg in WG}
solar_grades = {sg: filter(solar_avail_reproj, GSA_reproj, solar_config["sg_thr"][sg][0], solar_config["sg_thr"][sg][1]) for sg in SG}

# Area lists
a_indiv = [f"{region_name}_{sg}" for sg in SG] + [f"{region_name}_{wg}" for wg in WG]
a_comb = [f"{region_name}_{sg}_{wg}" for sg, wg in SG_WG_comb]
areas = a_indiv + a_comb

# Create a DataFrame to store the area potentials (km2) for each cost tier
df_tier_potentials_onshorewind = pd.DataFrame(index=areas, columns=config["tiers"].keys())
df_tier_potentials_solar = pd.DataFrame(index=areas, columns=config["tiers"].keys())

# Total available land area
total_avail = np.sum(union([wind_avail_reproj, solar_avail_reproj])) * pixel_area_km2
print(f'Total available land area: {total_avail:.0f} km²')


# Find all solar potentials that do not overlap with wind potentials
for sg in SG:
    print(f'Processing solar potential: {sg}')
    
    inclusion_area = diff(solar_grades[sg], union(list(wind_grades.values())))
    if (inclusion_area.sum() * pixel_area_km2) < (config["min_area_rg"] * total_avail * pixel_area_km2):
        print(f'Low/no solar potential found for {sg} in {region_name}. Skipping.')
        continue
    export_raster(inclusion_area, os.path.join(output_path, f'{region_name}_{sg}_{local_crs_tag}.tif'), ref)

    for t in config["tiers"]:
        tier_area = filter(inclusion_area, costmap_solar, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials_solar.loc[f"{region_name}_{sg}", t] = np.sum(tier_area) * pixel_area_km2

# Find all wind potentials that do not overlap with solar potentials
for wg in WG:
    print(f'Processing wind potential: {wg}')
    
    inclusion_area = diff(wind_grades[wg], union(list(solar_grades.values())))
    if (inclusion_area.sum() * pixel_area_km2) < (config["min_area_rg"] * total_avail * pixel_area_km2):
        print(f'Low/no wind potential found for {wg} in {region_name}. Skipping.')
        continue
    export_raster(inclusion_area, os.path.join(output_path, f'{region_name}_{wg}_{local_crs_tag}.tif'), ref)

    for t in config["tiers"]:
        tier_area = filter(inclusion_area, costmap_onshorewind, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials_onshorewind.loc[f"{region_name}_{wg}", t] = np.sum(tier_area) * pixel_area_km2

# Find all ares with combinations of solar and wind potentials
for sg, wg in SG_WG_comb:
    print(f'Processing combination: {sg} and {wg}')
    
    inclusion_area = overlap(solar_grades[sg], wind_grades[wg])
    if (inclusion_area.sum() * pixel_area_km2) < (config["min_area_rg"] * total_avail * pixel_area_km2):
        print(f'Low/no potential found for combination {sg} and {wg} in {region_name}. Skipping.')
        continue
    export_raster(inclusion_area, os.path.join(output_path, f'{region_name}_{sg}_{wg}_{local_crs_tag}.tif'), ref)

    for t in config["tiers"]:
        tier_area_onshorewind = filter(inclusion_area, costmap_onshorewind, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials_onshorewind.loc[f"{region_name}_{sg}_{wg}", t] = np.sum(tier_area_onshorewind) * pixel_area_km2
        tier_area_solar = filter(inclusion_area, costmap_solar, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials_solar.loc[f"{region_name}_{sg}_{wg}", t] = np.sum(tier_area_solar) * pixel_area_km2

# Drop rows with all zero values
df_tier_potentials_onshorewind = df_tier_potentials_onshorewind[df_tier_potentials_onshorewind.sum(axis=1) > 0]
df_tier_potentials_solar = df_tier_potentials_solar[df_tier_potentials_solar.sum(axis=1) > 0]

# Export potentials to CSV
print(f'Exporting cost tier potentials to {rel_path(output_path)}')
tier_potentials_file_onshorewind = os.path.join(output_path, f'{region_name}_tier_potentials_onshorewind.csv')
df_tier_potentials_onshorewind.to_csv(tier_potentials_file_onshorewind)
tier_potentials_file_solar = os.path.join(output_path, f'{region_name}_tier_potentials_solar.csv')
df_tier_potentials_solar.to_csv(tier_potentials_file_solar)

# Export a json with the relevant areas
relevant_resource_grades_onshorewind = df_tier_potentials_onshorewind.index.tolist()
relevant_resource_grades_onshorewind_file = os.path.join(output_path, f'{region_name}_onshorewind_relevant_resource_grades.json')
with open(relevant_resource_grades_onshorewind_file, 'w') as f:
    json.dump(relevant_resource_grades_onshorewind, f)
relevant_resource_grades_solar = df_tier_potentials_solar.index.tolist()
relevant_resource_grades_solar_file = os.path.join(output_path, f'{region_name}_solar_relevant_resource_grades.json')
with open(relevant_resource_grades_solar_file, 'w') as f:
    json.dump(relevant_resource_grades_solar, f)