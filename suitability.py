import rasterio
import numpy as np
import pandas as pd
import warnings
import pickle
import os
import yaml
import rasterio
import snakemake
import itertools
import matplotlib.pyplot as plt
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

    return overlap_mask

# Function to compute difference between two rasters
def diff(array1, array2):
    # Compute difference mask (where data1 is present but data2 is not)
    diff_mask = (array1 > 0) & (array2 == 0)

    return diff_mask

# Function to filter a raster based on a value raster and a range
def filter(filter_array, value_array, vmin, vmax):
    vmin=float(vmin)
    vmax=float(vmax)
    filtered_mask = (filter_array > 0) & (value_array >= vmin) & (value_array <= vmax)

    return filtered_mask


#------------------------------------------- Initialization -------------------------------------------
dirname = os.getcwd() 
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 

region_name = config['region_name'] #if country is studied, then use country name
region_name = clean_region_name(region_name)
scenario = config['scenario']


#use snakemake params to override region name and folder name
# if snakemake is used, then region name and folder name can be set via snakemake params
try:
    region_folder_name = snakemake.params.get('region')
    region_name = snakemake.params.get('region')
    scenario = snakemake.params.get('scenario')
except:
    print("Snakemake params not found, using config values.")



data_path = os.path.join(dirname, 'data', config['region_folder_name'])
data_path_available_land = os.path.join(data_path, 'available_land')
data_from_proximity = os.path.join(data_path, 'proximity')

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
min_pixels_connected = config['min_pixels_connected']

wind_avail_path = os.path.join(
    data_path_available_land,
    f"{region_name}_wind_{scenario}_available_land_{local_crs_tag}.tif"
)
solar_avail_path = os.path.join(
    data_path_available_land,
    f"{region_name}_solar_{scenario}_available_land_{local_crs_tag}.tif"
)
substation_distance_path = os.path.join(data_from_proximity, f'substation_distance.tif')
road_distance_path = os.path.join(data_from_proximity, f'road_distance.tif')
terrain_ruggedness_path = os.path.join(data_path, f'TerrainRuggednessIndex_{region_name}_{local_crs_tag}.tif')
GWAPath = os.path.join(data_path, f'wind_{region_name}_{local_crs_tag}.tif')
GSAPath = os.path.join(data_path, f'solar_{region_name}_{local_crs_tag}.tif')

# Load rasters
wind_avail = rasterio.open(wind_avail_path)
solar_avail = rasterio.open(solar_avail_path)
substation_distance = rasterio.open(substation_distance_path)
road_distance = rasterio.open(road_distance_path)
terrain_ruggedness = rasterio.open(terrain_ruggedness_path)
GWA = rasterio.open(GWAPath)
GSA = rasterio.open(GSAPath)

# -------------- Check that rasters are formatted correcly and use same CRS --------------
check_alignment([wind_avail_path, solar_avail_path, substation_distance_path, road_distance_path, terrain_ruggedness_path, GWAPath, GSAPath])

#---------------- Reprojection and alignment (can be deleted if all rasters are aligned) ----------------
# Reference grid (intersection of all rasters)
ref = wind_avail # Should be standardized to a region raster or intersection of all rasters
transform = ref.transform
pixel_area_m2 = abs(transform.a * transform.e)
pixel_area_km2 = pixel_area_m2 / 1e6

#Reproject rasters to a common array
GWA_reproj = align_to_reference(GWA, ref)
GSA_reproj = align_to_reference(GSA, ref)
substation_distance_reproj = align_to_reference(substation_distance, ref)
road_distance_reproj = align_to_reference(road_distance, ref)
terrain_ruggedness_reproj = align_to_reference(terrain_ruggedness, ref)
wind_avail_reproj = align_to_reference(wind_avail, ref)
solar_avail_reproj = align_to_reference(solar_avail, ref)


# Cost map calculation (TO DO: Adjust cost map)
costmap = substation_distance_reproj * config["sub_dist_cost_factor"] + road_distance_reproj * config["road_dist_cost_factor"] + terrain_ruggedness_reproj * config["ruggedness_cost_factor"]


SG = config["sg_thr"].keys()
WG = config["wg_thr"].keys()
SG_WG_comb = list(itertools.product(SG, WG))  # All combinations of SG and WG

wind_grades = {wg: filter(wind_avail_reproj, GWA_reproj, config["wg_thr"][wg][0], config["wg_thr"][wg][1]) for wg in WG}
solar_grades = {sg: filter(solar_avail_reproj, GSA_reproj, config["sg_thr"][sg][0], config["sg_thr"][sg][1]) for sg in SG}

# Area lists
a_indiv = [f"{region_name}_{sg}" for sg in SG] + [f"{region_name}_{wg}" for wg in WG]
a_comb = [f"{region_name}_{sg}_{wg}" for sg, wg in SG_WG_comb]
areas = a_indiv + a_comb

# Create a DataFrame to store the area potentials (km2) for each cost tier
df_tier_potentials = pd.DataFrame(index=areas, columns=config["tiers"].keys())

# Find all solar potentials that do not overlap with wind potentials
for sg in SG:
    print(f'Processing solar potential: {sg}')
    
    inclusion_area = diff(solar_grades[sg], wind_avail_reproj)

    for t in config["tiers"]:
        tier_area = filter(inclusion_area, costmap, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials.loc[f"{region_name}_{sg}", t] = np.sum(tier_area) * pixel_area_km2

# Find all wind potentials that do not overlap with solar potentials
for wg in WG:
    print(f'Processing wind potential: {wg}')
    
    inclusion_area = diff(wind_grades[wg], solar_avail_reproj)

    for t in config["tiers"]:
        tier_area = filter(inclusion_area, costmap, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials.loc[f"{region_name}_{wg}", t] = np.sum(tier_area) * pixel_area_km2

# Find all ares with combinations of solar and wind potentials
for sg, wg in SG_WG_comb:
    print(f'Processing combination: {sg} and {wg}')
    
    inclusion_area = overlap(solar_grades[sg], wind_grades[wg])

    for t in config["tiers"]:
        tier_area = filter(inclusion_area, costmap, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials.loc[f"{region_name}_{sg}_{wg}", t] = np.sum(tier_area) * pixel_area_km2


# Export potentials to CSV
output_path = os.path.join(data_path,"suitability")
if not os.path.exists(output_path):
    os.makedirs(output_path)
tier_potentials_file = os.path.join(output_path, f'{region_name}_tier_potentials.csv')
print(f'Exporting tier potentials to {rel_path(output_path)}')
df_tier_potentials.to_csv(tier_potentials_file)


# To do: Exporting the overlap/diff rasters as well as a json with the relevant areas
