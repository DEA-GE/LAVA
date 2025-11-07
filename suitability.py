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
import json
from rasterio.warp import reproject, Resampling
from rasterio.io import MemoryFile
from utils.data_preprocessing import clean_region_name, rel_path
from utils.raster_analysis import align_to_reference, export_raster, filter, area_filter, union, diff, overlap, rasterize


#------------------------------------------- Initialization -------------------------------------------
dirname = os.getcwd() 
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 

# Load suitability configuration
suitability_config_file = os.path.join("configs", f"suitability.yaml")
with open(suitability_config_file, "r", encoding="utf-8") as f:
    config_suitability = yaml.load(f, Loader=yaml.FullLoader)

# Load the configs for relevant technologies
suitability_techs = config_suitability["suitability_techs"]
tech_configs = {}
for tech in suitability_techs:
    tech_config_file = os.path.join("configs", f"{tech}.yaml")
    with open(tech_config_file, "r", encoding="utf-8") as f:
        tech_configs[tech] = yaml.load(f, Loader=yaml.FullLoader)
if len(suitability_techs) > 1:
    multi_tech = True
else:
    multi_tech = False

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

# --- Resolution ---
# Check all techs for a manual resolution
manual_resolutions = [
    tech_configs[tech]['resolution_manual']
    for tech in suitability_techs
    if tech_configs[tech].get('resolution_manual') is not None
]
if manual_resolutions:
    # If more than one tech has manual resolution, choose one (they should match)
    res = manual_resolutions[0]
else:
    pixel_path = os.path.join(data_path, f'pixel_size_{region_name}_{local_crs_tag}.json')
    with open(pixel_path, 'r') as fp:
        res = json.load(fp)

# Get selected suitability categories
suitability_params = {k for k,v in config_suitability["suitability_params"].items() if v}


#--------------------------------------- Data ----------------------------------------

potential = {}
input_area = config_suitability['input_area']
if input_area == 'available_land':
    for tech in suitability_techs:
        path = os.path.join(data_path_available_land, f"{region_name}_{tech}_{scenario}_available_land_{local_crs_tag}.tif")
        potential[tech] = rasterio.open(path).read(1)
        # Reference grid
        ref = rasterio.open(path) # Should be standardized to a region raster or intersection of all rasters
        pixel_area_km2 = abs(ref.transform.a * ref.transform.e) / 1e6
elif input_area == 'study_region':
    for tech in suitability_techs:
        path = os.path.join(data_path, f"{region_name}_{local_crs_tag}.geojson")
        # Reference grid
        ref, memfile = rasterize(vector_path=path, crs=local_crs_obj, resolution=res)
        pixel_area_km2 = abs(ref.transform.a * ref.transform.e) / 1e6
        potential[tech] = ref.read(1)


GWAPath = os.path.join(data_path, f'wind_{region_name}_{local_crs_tag}.tif')
GWA = rasterio.open(GWAPath)
GWA_reproj = align_to_reference(GWA, ref, resampling=Resampling.bilinear)

GSAPath = os.path.join(data_path, f'solar_{region_name}_{local_crs_tag}.tif')
GSA = rasterio.open(GSAPath)
GSA_reproj = align_to_reference(GSA, ref, resampling=Resampling.bilinear)

if 'terrain' in suitability_params:
    terrain_ruggedness_path = os.path.join(data_path, 'derived_from_DEM', f'TerrainRuggednessIndex_{region_name}_{local_crs_tag}.tif')
    terrain_ruggedness = rasterio.open(terrain_ruggedness_path)
    terrain_ruggedness_reproj = align_to_reference(terrain_ruggedness, ref, resampling=Resampling.bilinear)

    landcover_path = os.path.join(data_path, f"landcover_{config['landcover_source']}_{region_name}_{local_crs_tag}.tif")
    landcover = rasterio.open(landcover_path)
    land_cover_reproj = align_to_reference(landcover, ref, resampling=Resampling.nearest)

if 'topography' in suitability_params:
    dem_path = os.path.join(data_path, f'DEM_{region_name}_{local_crs_tag}.tif')
    dem = rasterio.open(dem_path)
    dem_reproj = align_to_reference(dem, ref, resampling=Resampling.bilinear)

if 'substation_distance' in suitability_params:
    substation_distance_path = os.path.join(data_from_proximity, f'substation_distance.tif')
    substation_distance = rasterio.open(substation_distance_path)
    substation_distance_reproj = align_to_reference(substation_distance, ref, resampling=Resampling.bilinear)


#---------------- Dynamic costmap based on selected suitability categories ----------------

if suitability_params:
    print(f'Calculating costmaps based on suitability parameters: {list(suitability_params)}')
    # Initialize costmaps (multiplicative identity)
    costmap = {}
    for tech in suitability_techs:
        costmap[tech] = np.ones_like(ref.read(1), dtype=float)

    for tech in suitability_techs:

        # --- TERRAIN (optional) ---
        if "terrain" in suitability_params:
            terrain_factor = np.zeros_like(ref.read(1), dtype=float)

            for terrain_type in config_suitability["terrain_modifier"]:
                lower, upper = terrain_type['range']
                terrain_mask = (terrain_ruggedness_reproj >= lower) & (terrain_ruggedness_reproj < upper)
                terrain_factor[terrain_mask] = terrain_type['cost'][tech] - 1

            # Landcover modifiers
            for landcover_type, vals in config_suitability["landcover_modifier"].items():
                mask = (land_cover_reproj == landcover_type)
                terrain_factor[mask] = vals[tech] - 1

            # Apply terrain weight
            costmap[tech] *= (1 + terrain_factor * config_suitability["modifier_weights"]["terrain"][tech])

            export_raster(terrain_factor, os.path.join(output_path, f'terrain_factor_{tech}_{scenario}_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)

        # --- TOPOGRAPHY (optional) ---
        if "topography" in suitability_params:
            topography_factor = np.zeros_like(ref.read(1), dtype=float)

            for topography_level in config_suitability["topography_modifier"]:
                lower, upper = topography_level['range']
                elevation_mask = (dem_reproj >= lower) & (dem_reproj < upper)
                topography_factor[elevation_mask] = topography_level['cost'][tech] - 1
            
            # Apply elevation weight
            costmap[tech] *= (1 + topography_factor * config_suitability["modifier_weights"]["topography"][tech])

            export_raster(topography_factor, os.path.join(output_path, f'topography_factor_{tech}_{scenario}_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)

        # --- SUBSTATION DISTANCE (optional) ---
        if "substation_distance" in suitability_params:
            avg_sub = config_suitability["average_sub_dist"][config_suitability["region_set"][region_name]]
            substation_factor = substation_distance_reproj / avg_sub[tech] - 1

            # Apply substation distance weight
            costmap[tech] *= (1 + substation_factor * config_suitability["modifier_weights"]["substation_distance"][tech])

            export_raster(substation_factor, os.path.join(output_path, f'substation_factor_{tech}_{scenario}_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)

        # --- REGION (optional) ---
        if "region" in suitability_params:
            region_key = config_suitability["region_set"][region_name]
            region_factor = config_suitability["region_modifier"][region_key][tech] - 1

            # Apply region weight
            costmap[tech] *= (1 + region_factor * config_suitability["modifier_weights"]["region"][tech])

        # --- Export cost maps ---
        export_raster(costmap[tech] * potential[tech],  os.path.join(output_path, f'costmap_{tech}_{scenario}_available_{region_name}_{local_crs_tag}.tif'), ref, local_crs_obj)

else:
    print('No suitability parameters selected. Calculating only resource grades')


# Resource grades
RG = {}
for tech in suitability_techs:
    RG[tech] = list(tech_configs[tech]['rg_thr'].keys())
if multi_tech:
    RG_comb = list(itertools.product(*RG.values())) # All combinations of resource grades across technologies

# Area lists
areas = []
areas += [f"{region_name}_{rg}" for tech in suitability_techs for rg in RG[tech]]
if multi_tech:
    areas += [f"{region_name}_" + "_".join(combo) for combo in RG_comb]
areas += [f"{region_name}_distributed"]


# Create a DataFrame to store the area potentials (km2)
df_potentials = pd.DataFrame(index=areas, columns=["Potential"])

# DataFrame to store tiered potentials (as share of full potential)
df_tier_potentials = {}
if suitability_params:
    for tech in suitability_techs:
        df_tier_potentials[tech] = pd.DataFrame(index=areas, columns=config_suitability["tiers"].keys())
else:
    for tech in suitability_techs:
        df_tier_potentials[tech] = pd.DataFrame(index=areas, columns=["Potential share"])

# Total available land area
total_avail = np.sum(union([potential[tech] for tech in suitability_techs])) * pixel_area_km2
print(f'Total available land area: {total_avail:.0f} km²')

min_size_distributed = config_suitability["min_area_distributed"] / pixel_area_km2
min_size_rg = config_suitability["min_area_rg"] / pixel_area_km2

potential_filtered = {}
distributed_area = {}
tech_grades = {}
for tech in suitability_techs:
    # Utility scale area (with areas greater than the minimum size)
    potential_filtered[tech] = area_filter(potential[tech], min_size_distributed)
    # Small distributed areas
    distributed_area[tech] = diff(potential[tech], potential_filtered[tech])

    # Filter areas based on resource grades
    if tech in ['onshorewind', 'offshorewind']:
        tech_grades[tech] = {rg: filter(potential_filtered[tech], GWA_reproj, tech_configs[tech]["rg_thr"][rg][0], tech_configs[tech]["rg_thr"][rg][1]) for rg in RG[tech]}
    elif tech == 'solar':
        tech_grades[tech] = {rg: filter(potential_filtered[tech], GSA_reproj, tech_configs[tech]["rg_thr"][rg][0], tech_configs[tech]["rg_thr"][rg][1]) for rg in RG[tech]}
    tech_grades[tech]['distributed'] = distributed_area[tech]

# Find all tech potentials that do not overlap with other tech potentials
for tech in suitability_techs:
    for rg in RG[tech]:
        print(f'Processing {tech} potential: {rg}')
        
        if multi_tech:
            # List all other tech grades
            other_tech_grades = [
                arr
                for t, rg_dict in tech_grades.items()
                if t != tech
                for arr in rg_dict.values()
            ]
            
            # Find inclusion area by removing all wind grades and distributed wind areas
            inclusion_area = diff(tech_grades[tech][rg], union(other_tech_grades))
        else:
            inclusion_area = tech_grades[tech][rg]

        if inclusion_area.sum() < min_size_rg:
            print(f'Potential found for {rg} in {region_name} is below minimum. Adding to distributed area.')
            tech_grades[tech]['distributed'] = union([tech_grades[tech]['distributed'], inclusion_area])
            continue

        # Save potential area and export raster
        df_potentials.loc[f"{region_name}_{rg}", "Potential"] = np.sum(inclusion_area) * pixel_area_km2
        export_raster(inclusion_area, os.path.join(output_path, f'{region_name}_{rg}_{scenario}_{local_crs_tag}.tif'), ref, local_crs_obj)

        # If there are suitability categories selected, calculate tiered potentials as share of the full potential
        if suitability_params:
            for t in config_suitability["tiers"]:
                tier_area = filter(inclusion_area, costmap[tech], config_suitability["tiers"][t][0], config_suitability["tiers"][t][1])
                df_tier_potentials[tech].loc[f"{region_name}_{rg}", t] = np.sum(tier_area) / np.sum(inclusion_area)
        else:
            df_tier_potentials[tech].loc[f"{region_name}_{rg}", "Potential share"] = 1

# Find all areas with combinations of solar and wind potentials
if multi_tech:
    for tech_combo in RG_comb:
        label = ", ".join(f"{tech}: {rg}" for tech, rg in zip(suitability_techs, tech_combo))
        print(f"Processing combination: {label}")
        
        # Find inclusion area by overlapping tech grades
        arrays = [tech_grades[tech][rg] for tech, rg in zip(suitability_techs, tech_combo)]
        inclusion_area = overlap(arrays)

        if inclusion_area.sum() < min_size_rg:
            print(f'Potential found for combination {tech_combo} and in {region_name} is below minimum. Adding to distributed area.')
            for tech in suitability_techs:
                tech_grades[tech]['distributed'] = union([tech_grades[tech]['distributed'], inclusion_area])
            continue

        # Save potential area and export raster
        df_potentials.loc[f"{region_name}_" + "_".join(tech_combo), "Potential"] = np.sum(inclusion_area) * pixel_area_km2
        export_raster(inclusion_area, os.path.join(output_path, f"{region_name}_" + "_".join(tech_combo) + f"_{scenario}_{local_crs_tag}.tif"), ref, local_crs_obj)

        if suitability_params:
            for t in config_suitability["tiers"]:
                for tech in suitability_techs:
                    tier_area = filter(inclusion_area, costmap[tech], config_suitability["tiers"][t][0], config_suitability["tiers"][t][1])
                    df_tier_potentials[tech].loc[f"{region_name}_" + "_".join(tech_combo), t] = np.sum(tier_area) / np.sum(inclusion_area)
        else:
            for tech in suitability_techs:
                df_tier_potentials[tech].loc[f"{region_name}_" + "_".join(tech_combo), "Potential share"] = 1


# Process the distributed areas found above
distributed_area = union([tech_grades[tech]['distributed'] for tech in suitability_techs])
df_potentials.loc[f"{region_name}_distributed", "Potential"] = np.sum(distributed_area) * pixel_area_km2
export_raster(distributed_area, os.path.join(output_path, f'{region_name}_distributed_{scenario}_{local_crs_tag}.tif'), ref, local_crs_obj)

if suitability_params:
    for t in config_suitability["tiers"]:
        for tech in suitability_techs:
            tier_area = filter(distributed_area, costmap[tech], config_suitability["tiers"][t][0],config_suitability["tiers"][t][1])
            df_tier_potentials[tech].loc[f"{region_name}_distributed", t] = np.sum(tier_area) / np.sum(distributed_area)
else:
    for tech in suitability_techs:
        df_tier_potentials[tech].loc[f"{region_name}_distributed", "Potential share"] = 1


# Export potentials to CSV
print(f'Exporting potentials to {rel_path(output_path)}')
potentials_file = os.path.join(output_path, f'{region_name}_{scenario}_resource_grade_potentials.csv')
df_potentials.to_csv(potentials_file)
for tech in suitability_techs:
    df_tier_potentials_file = os.path.join(output_path, f'{region_name}_{tech}_{scenario}_tier_potentials.csv')
    df_tier_potentials[tech].to_csv(df_tier_potentials_file)

# Export lists with the relevant resource grades
relevant_resource_grades = df_potentials.dropna(how='all').index.tolist()
relevant_resource_grades_file = os.path.join(output_path, f'{region_name}_{scenario}_relevant_resource_grades.json')
with open(relevant_resource_grades_file, 'w') as f:
    json.dump(relevant_resource_grades, f)
for tech in suitability_techs:
    relevant_resource_grades_tech = df_tier_potentials[tech].dropna(how='all').index.tolist()
    relevant_resource_grades_tech_file = os.path.join(output_path, f'{region_name}_{tech}_{scenario}_relevant_resource_grades.json')
    with open(relevant_resource_grades_tech_file, 'w') as f:
        json.dump(relevant_resource_grades_tech, f)