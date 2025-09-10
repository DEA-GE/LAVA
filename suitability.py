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
from utils.raster_analysis import align_to_reference, export_raster, check_alignment, filter, area_filter, union, diff, overlap


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


region_name = config['study_region_name'] #if country is studied, then use country name
region_name = clean_region_name(region_name)
scenario = config['scenario']

#Initialize parser for command line arguments and define arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default=region_name, help="region name")
parser.add_argument("--method",default="manual", help="method to run the script, e.g., snakemake or manual")
parser.add_argument("--scenario", default=scenario, help="scenario name")
args = parser.parse_args()

# If running via Snakemake, use the region name and folder name from command line arguments
if args.method == "snakemake":
    region_name = clean_region_name(args.region)
    scenario = args.scenario
    print(f"Running via snakemake - measures: region={region_name}, scenario={scenario}")
else:
    print(f"Running manually - measures: region={region_name} scenario={scenario}")

data_path = os.path.join(dirname, 'data', region_name)
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
GWA_reproj = align_to_reference(GWA, ref, resampling=Resampling.bilinear)
GSA_reproj = align_to_reference(GSA, ref, resampling=Resampling.bilinear)
substation_distance_reproj = align_to_reference(substation_distance, ref, resampling=Resampling.bilinear)
land_cover_reproj = align_to_reference(landcover, ref, resampling=Resampling.nearest)
terrain_ruggedness_reproj = align_to_reference(terrain_ruggedness, ref, resampling=Resampling.bilinear)
wind_avail_reproj = align_to_reference(wind_avail, ref, resampling=Resampling.nearest)
solar_avail_reproj = align_to_reference(solar_avail, ref, resampling=Resampling.nearest)

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
export_raster(terrain_factor_onshorewind, os.path.join(output_path, f'terrain_factor_onshorewind_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)
export_raster(terrain_factor_solar, os.path.join(output_path, f'terrain_factor_solar_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)

substation_factor_onshorewind = substation_distance_reproj / config["average_sub_dist"]['onshorewind'] - 1
substation_factor_solar = substation_distance_reproj / config["average_sub_dist"]['solar'] - 1

export_raster(substation_factor_onshorewind, os.path.join(output_path, f'substation_factor_onshorewind_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)
export_raster(substation_factor_solar, os.path.join(output_path, f'substation_factor_solar_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)

region_factor_onshorewind = config["region_modifier"][region_name]['onshorewind'] - 1
region_factor_solar = config["region_modifier"][region_name]['solar'] - 1

costmap_onshorewind = (1 + terrain_factor_onshorewind * config["modifier_weights"]["terrain"]["onshorewind"]) * (1 + substation_factor_onshorewind * config["modifier_weights"]["substation_distance"]["onshorewind"]) * (1 + region_factor_onshorewind * config["modifier_weights"]["region"]["onshorewind"])
costmap_solar = (1 + terrain_factor_solar * config["modifier_weights"]["terrain"]["solar"]) * (1 + substation_factor_solar * config["modifier_weights"]["substation_distance"]["solar"]) * (1 + region_factor_solar * config["modifier_weights"]["region"]["solar"])

costmap_onshorewind[land_cover_reproj == 0] = np.nan
costmap_solar[land_cover_reproj == 0] = np.nan

export_raster(costmap_onshorewind, os.path.join(output_path, f'costmap_onshorewind_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)
export_raster(costmap_solar, os.path.join(output_path, f'costmap_solar_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)


# Resource grades
SG = solar_config["sg_thr"].keys()
WG = onshorewind_config["wg_thr"].keys()
SG_WG_comb = list(itertools.product(SG, WG))  # All combinations of SG and WG

# Area lists
a_indiv = [f"{region_name}_{sg}" for sg in SG] + [f"{region_name}_{wg}" for wg in WG]
a_comb = [f"{region_name}_{sg}_{wg}" for sg, wg in SG_WG_comb]
a_dist = [f"{region_name}_distributed"]
areas = a_indiv + a_comb + a_dist

# Create a DataFrame to store the area potentials (km2) for each cost tier
df_tier_potentials_onshorewind = pd.DataFrame(index=areas, columns=config["tiers"].keys())
df_tier_potentials_solar = pd.DataFrame(index=areas, columns=config["tiers"].keys())

# Total available land area
total_avail = np.sum(union([wind_avail_reproj, solar_avail_reproj])) * pixel_area_km2
print(f'Total available land area: {total_avail:.0f} km²')

min_size_distributed = config["min_area_distributed"] / pixel_area_km2
min_size_rg = config["min_area_rg"] / pixel_area_km2

# Find minimum connected
wind_avail_filtered = area_filter(wind_avail_reproj, min_size_distributed)
solar_avail_filtered = area_filter(solar_avail_reproj, min_size_distributed)

# Distributed area
wind_distributed_area = diff(wind_avail_reproj,wind_avail_filtered)
solar_distributed_area = diff(solar_avail_reproj,solar_avail_filtered)

# Define wind and solar grades
wind_grades = {wg: filter(wind_avail_filtered, GWA_reproj, onshorewind_config["wg_thr"][wg][0], onshorewind_config["wg_thr"][wg][1]) for wg in WG}
solar_grades = {sg: filter(solar_avail_filtered, GSA_reproj, solar_config["sg_thr"][sg][0], solar_config["sg_thr"][sg][1]) for sg in SG}


# Find all solar potentials that do not overlap with wind potentials
for sg in SG:
    print(f'Processing solar potential: {sg}')
    
    inclusion_area = diff(solar_grades[sg], union(list(wind_grades.values()) + [wind_distributed_area]))

    if inclusion_area.sum() < min_size_rg:
        print(f'Potential found for {sg} in {region_name} is below minimum. Adding to distributed area.')
        solar_distributed_area = union([solar_distributed_area, inclusion_area])
        continue

    export_raster(inclusion_area, os.path.join(output_path, f'{region_name}_{sg}_{local_crs_tag}.tif'), ref, local_crs_obj)

    for t in config["tiers"]:
        tier_area = filter(inclusion_area, costmap_solar, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials_solar.loc[f"{region_name}_{sg}", t] = np.sum(tier_area) * pixel_area_km2

# Find all wind potentials that do not overlap with solar potentials
for wg in WG:
    print(f'Processing wind potential: {wg}')
    
    inclusion_area = diff(wind_grades[wg], union(list(solar_grades.values()) + [solar_distributed_area]))

    if inclusion_area.sum() < min_size_rg:
        print(f'Potential found for {wg} in {region_name} is below minimum. Adding to distributed area.')
        wind_distributed_area = union([wind_distributed_area, inclusion_area])
        continue

    export_raster(inclusion_area, os.path.join(output_path, f'{region_name}_{wg}_{local_crs_tag}.tif'), ref, local_crs_obj)

    for t in config["tiers"]:
        tier_area = filter(inclusion_area, costmap_onshorewind, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials_onshorewind.loc[f"{region_name}_{wg}", t] = np.sum(tier_area) * pixel_area_km2

# Find all ares with combinations of solar and wind potentials
for sg, wg in SG_WG_comb:
    print(f'Processing combination: {sg} and {wg}')
    
    inclusion_area = overlap(solar_grades[sg], wind_grades[wg])

    if inclusion_area.sum() < min_size_rg:
        print(f'Potential found for combination {sg} and {wg} in {region_name} is below minimum. Adding to distributed area.')
        wind_distributed_area = union([wind_distributed_area, inclusion_area])
        solar_distributed_area = union([solar_distributed_area, inclusion_area])
        continue

    export_raster(inclusion_area, os.path.join(output_path, f'{region_name}_{sg}_{wg}_{local_crs_tag}.tif'), ref, local_crs_obj)

    for t in config["tiers"]:
        tier_area_onshorewind = filter(inclusion_area, costmap_onshorewind, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials_onshorewind.loc[f"{region_name}_{sg}_{wg}", t] = np.sum(tier_area_onshorewind) * pixel_area_km2
        tier_area_solar = filter(inclusion_area, costmap_solar, config["tiers"][t][0], config["tiers"][t][1])
        df_tier_potentials_solar.loc[f"{region_name}_{sg}_{wg}", t] = np.sum(tier_area_solar) * pixel_area_km2

# Process the distributed areas found above
distributed_area = union([solar_distributed_area, wind_distributed_area])
export_raster(distributed_area, os.path.join(output_path, f'{region_name}_distributed_{local_crs_tag}.tif'), ref, local_crs_obj)

for t in config["tiers"]:
    tier_area_onshorewind = filter(distributed_area, costmap_onshorewind, config["tiers"][t][0], config["tiers"][t][1])
    df_tier_potentials_onshorewind.loc[f"{region_name}_distributed", t] = np.sum(tier_area_onshorewind) * pixel_area_km2
    tier_area_solar = filter(distributed_area, costmap_solar, config["tiers"][t][0], config["tiers"][t][1])
    df_tier_potentials_solar.loc[f"{region_name}_distributed", t] = np.sum(tier_area_solar) * pixel_area_km2

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
