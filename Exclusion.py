import atlite
import matplotlib.pyplot as plt
from scipy.ndimage import label
import numpy as np
import json 
import pickle
import os  
import argparse
import geopandas as gpd
from atlite.gis import shape_availability
from atlite.gis import shape_availability_reprojected
import rasterio
import yaml
from utils.data_preprocessing import clean_region_name, log_scenario_run
from rasterstats import zonal_stats
from utils.raster_analysis import area_filter

dirname = os.getcwd() 
#main_dir = os.path.join(dirname, '..')
config_file = os.path.join("configs", "config.yaml")
#load the configuration file
with open(config_file, "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

region_name = config['study_region_name'] #if country is studied, then use country name
region_name_clean = clean_region_name(region_name)
technology = config.get('technology') #technology, e.g., 'wind' or 'solar'
scenario = config.get('scenario', 'ref') # scenario, e.g., 'ref' or 'high'


#Initialize parser for command line arguments and define arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default=region_name_clean, help="region name")
parser.add_argument("--method",default="manual", help="method to run the script, e.g., snakemake or manual")
parser.add_argument("--scenario", default=scenario, help="scenario name")
parser.add_argument('--technology', default=f"{technology}")
args = parser.parse_args()

# If running via Snakemake, use the region name and folder name from command line arguments
if args.method == "snakemake":
    region_name_clean = clean_region_name(args.region)
    technology = args.technology
    scenario = args.scenario
    print(f'\nExclusion for {region_name_clean}')
    print(f"Running via snakemake - measures: region={region_name_clean}, technology={technology}, scenario={scenario}")
else:
    print(f'\nExclusion for {region_name_clean}')
    print(f"Running manually - measures: region={region_name_clean}, technology={technology}, scenario={scenario}")


#load the technology specific configuration file
tech_config_file = os.path.join("configs", f"{technology}.yaml")
with open(tech_config_file, "r", encoding="utf-8") as f:
    tech_config = yaml.load(f, Loader=yaml.FullLoader)

resampled = '' #'_resampled' 

# construct folder paths
dirname = os.getcwd()
data_path = os.path.join(dirname, 'data', region_name_clean)
log_scenario_run(region_name_clean, technology, scenario, log_dir=data_path)
data_path_OSM = os.path.join(dirname, 'data', region_name_clean, 'OSM_Infrastructure')
data_from_DEM = os.path.join(data_path, 'derived_from_DEM')
OSM_source = config['OSM_source']

# Load the CRS
# geo CRS
with open(os.path.join(data_path, region_name_clean+'_global_CRS.pkl'), 'rb') as file:
        global_crs_obj = pickle.load(file)
# projected CRS
with open(os.path.join(data_path, region_name_clean+'_local_CRS.pkl'), 'rb') as file:
        local_crs_obj = pickle.load(file)

print(f'geo CRS: {global_crs_obj}; projected CRS: {local_crs_obj}')

# Extract tag for filename, e.g., 'EPSG3035' or 'ESRI102003'
auth = global_crs_obj.to_authority()
global_crs_tag = ''.join(auth) if auth else global_crs_obj.to_string().replace(":", "_")
auth = local_crs_obj.to_authority()
local_crs_tag = ''.join(auth) if auth else local_crs_obj.to_string().replace(":", "_")


# Paths and existence checks
landcoverPath = os.path.join(data_path, f"landcover_{config['landcover_source']}_{region_name_clean}_{local_crs_tag}.tif")
landcover = 1 if os.path.isfile(landcoverPath) else 0
demRasterPath = os.path.join(data_path, f'DEM_{region_name_clean}_{global_crs_tag}{resampled}.tif')
dem = 1 if os.path.isfile(demRasterPath) else 0
slopeRasterPath = os.path.join(data_from_DEM, f'slope_{region_name_clean}_{global_crs_tag}{resampled}.tif')
slope = 1 if os.path.isfile(slopeRasterPath) else 0
terrain_ruggedness_path = os.path.join(data_path, f'TerrainRuggednessIndex_{region_name_clean}_{global_crs_tag}.tif')
terrain_ruggedness = 1 if os.path.isfile(terrain_ruggedness_path) else 0
windRasterPath = os.path.join(data_path, f'wind_{region_name_clean}_{global_crs_tag}{resampled}.tif')
wind = 1 if os.path.isfile(windRasterPath) else 0
solarRasterPath = os.path.join(data_path, f'solar_{region_name_clean}_{global_crs_tag}{resampled}.tif')
solar = 1 if os.path.isfile(solarRasterPath) else 0

regionPath = os.path.join(data_path, f'{region_name_clean}_{local_crs_tag}.geojson')
region = gpd.read_file(regionPath)

northfacingRasterPath = os.path.join(data_from_DEM, f'north_facing_{region_name_clean}_{global_crs_tag}{resampled}.tif')
nfacing = 1 if os.path.isfile(northfacingRasterPath) else 0
coastlinesPath = os.path.join(data_path, f'goas_{region_name_clean}_{global_crs_tag}.gpkg')
coastlines = 1 if os.path.isfile(coastlinesPath) else 0
protectedAreasPath = os.path.join(data_path, f"protected_areas_{config['protected_areas_source']}_{region_name_clean}_{global_crs_tag}.gpkg")
protectedAreas = 1 if os.path.isfile(protectedAreasPath) else 0

# OSM
roadsPath = os.path.join(data_path_OSM, f'{OSM_source}_roads.gpkg')
roads = 1 if os.path.isfile(roadsPath) else 0
railwaysPath = os.path.join(data_path_OSM, f'{OSM_source}_railways.gpkg')
railways = 1 if os.path.isfile(railwaysPath) else 0
airportsPath = os.path.join(data_path_OSM, f'{OSM_source}_airports.gpkg')
airports = 1 if os.path.isfile(airportsPath) else 0
waterbodiesPath = os.path.join(data_path_OSM, f'{OSM_source}_waterbodies.gpkg')
waterbodies = 1 if os.path.isfile(waterbodiesPath) else 0
militaryPath = os.path.join(data_path_OSM, f'{OSM_source}_military.gpkg')
military = 1 if os.path.isfile(militaryPath) else 0
substationsPath = os.path.join(data_path_OSM, f'{OSM_source}_substations.gpkg')
substations = 1 if os.path.isfile(substationsPath) else 0
transmissionPath = os.path.join(data_path_OSM, f'{OSM_source}_transmission_lines.gpkg')
transmission = 1 if os.path.isfile(transmissionPath) else 0
generatorsPath = os.path.join(data_path_OSM, f'{OSM_source}_generators.gpkg')
generators = 1 if os.path.isfile(generatorsPath) else 0
plantsPath = os.path.join(data_path_OSM, f'{OSM_source}_plants.gpkg')
plants = 1 if os.path.isfile(plantsPath) else 0

# Additional exclusion polygons
additional_exclusion_polygons_Path = os.path.join(data_path, 'additional_exclusion_polygons')
additional_exclusion_polygons = 1 if os.path.exists(additional_exclusion_polygons_Path) else 0


# load unique land use codes
with open(os.path.join(data_path, f'landuses_{region_name_clean}.json'), 'r') as fp:
    landuses = json.load(fp)

# load pixel size
if tech_config['resolution_manual'] is not None:
    res = tech_config['resolution_manual']
else:
    with open(os.path.join(data_path, f'pixel_size_{region_name_clean}_{local_crs_tag}.json'), 'r') as fp:
        res = json.load(fp)
    

#perform exclusions

#raster can be in different CRS than exclusioncontainer, it is co-registered by atlite!
#vector data needs to be in CRS of exclusioncontainer???


info_list_exclusion = []
info_list_not_selected = []
info_list_not_available = []

# initiate Exclusion container
excluder = atlite.ExclusionContainer(crs=local_crs_obj, res=res)

# add landcover exclusions 
if tech_config['landcover_codes']:   
    input_codes = tech_config['landcover_codes']
    for key, value in input_codes.items():
        excluder.add_raster(landcoverPath, codes=key, buffer=value , crs=local_crs_obj)
    info_list_exclusion.append(f"landcover codes which are excluded (code, buffer in meters): {input_codes}")
else: print('landcover not selected in config.')

# add elevation exclusions
param = tech_config['max_elevation']
if dem==1 and param is not None: 
    excluder.add_raster(demRasterPath, codes=range(param,10000), crs=global_crs_obj)
    info_list_exclusion.append(f"max elevation: {param}")
elif dem==1 and param is None: info_list_not_selected.append(f"DEM")
elif dem==0: info_list_not_available.append(f"DEM")

# add slope exclusions
param = tech_config['max_slope']
if slope==1 and param is not None:
    excluder.add_raster(slopeRasterPath, codes=range(param,90), crs=global_crs_obj)
    info_list_exclusion.append(f"max slope: {param}")
elif slope==1 and param is None: info_list_not_selected.append(f"slope")
elif slope==0: info_list_not_available.append(f"slope")

# add terrain ruggedness exclusions
param = tech_config['max_terrain_ruggedness']
if terrain_ruggedness==1 and param is not None:
    excluder.add_raster(terrain_ruggedness_path, codes=range(0,param), invert=True, crs=global_crs_obj)
    info_list_exclusion.append(f"max terrain ruggedness: {param}")
elif terrain_ruggedness==1 and param is None: info_list_not_selected.append(f"terrain_ruggedness")
elif terrain_ruggedness==0: info_list_not_available.append(f"terrain_ruggedness")

# add north facing exclusion
param = config['north_facing_pixels']
if nfacing==1  and param is not None:
    excluder.add_raster(northfacingRasterPath, codes=1, crs=global_crs_obj)
    info_list_exclusion.append(f'north facing pixels')
elif nfacing==1 and param is None: info_list_not_selected.append(f"nfacing")
elif nfacing==0: info_list_not_available.append(f"nfacing")


# add wind exclusions
def wind_filter(mask):
    """Filter out values outside the desired wind speed range."""
    min_val = tech_config['min_wind_speed']
    max_val = tech_config['max_wind_speed']
    if min_val is not None and max_val is not None:
        return (mask < min_val) | (mask > max_val)
    elif min_val is not None:
        return mask < min_val
    elif max_val is not None:
        return mask > max_val

if technology in  ["onshorewind", "offshorewind"] and (tech_config['min_wind_speed'] is not None or tech_config['max_wind_speed'] is not None): 
    min_wind_speed = tech_config['min_wind_speed']
    max_wind_speed = tech_config['max_wind_speed']
    excluder.add_raster(windRasterPath, codes=wind_filter, crs=global_crs_obj)
    if min_wind_speed is not None and max_wind_speed is not None: info=f"min wind speed: {min_wind_speed}, max wind speed: {max_wind_speed}"
    elif min_wind_speed is not None: info=f"min wind speed: {min_wind_speed}"
    elif max_wind_speed is not None: info=f"max wind speed: {max_wind_speed}"
    info_list_exclusion.append(f'{info}')
elif wind==0: info_list_not_available.append(f"wind")

# add solar exclusions
def solar_filter(mask): #desired yearly, specific solar production (kWh/m²/year) 
    """Filter out values outside the desired solar production range (kWh/m²/year)."""
    min_val = tech_config.get('min_solar_production')
    max_val = tech_config.get('max_solar_production')
    if min_val is not None and max_val is not None:
        return (mask < min_val) | (mask > max_val)
    elif min_val is not None:
        return mask < min_val
    elif max_val is not None:
        return mask > max_val
    
if technology == "solar" and (tech_config.get('min_solar_production') is not None or tech_config.get('max_solar_production') is not None):
    
    min_solar_production = tech_config.get('min_solar_production')
    max_solar_production = tech_config.get('max_solar_production')

    excluder.add_raster(solarRasterPath, codes=solar_filter, crs=global_crs_obj)
    if min_solar_production is not None and max_solar_production is not None:
        info=f"min_solar_production: {min_solar_production}, max_solar_production: {max_solar_production}"
    elif min_solar_production is not None:
        info=f"min_solar_production: {min_solar_production}"
    elif max_solar_production is not None:
        info=f"max_solar_production: {max_solar_production}"
    info_list_exclusion.append(info)
elif solar==0: info_list_not_available.append(f"solar")



# add exclusions from vector data
# Railways
param = tech_config['railways_buffer']
if railways==1 and param is not None: 
    excluder.add_geometry(railwaysPath, buffer=param)
    info_list_exclusion.append(f"railways buffer: {param}")
elif railways==1 and param is None: info_list_not_selected.append(f"railways")
elif railways==0: info_list_not_available.append(f"railways")

# Roads
param = tech_config['roads_buffer']
if roads == 1 and param is not None:
    excluder.add_geometry(roadsPath, buffer=param)
    info_list_exclusion.append(f"roads buffer: {param}")
elif roads == 1 and param is None: info_list_not_selected.append("roads")
elif roads == 0: info_list_not_available.append("roads")

# Airports
param = tech_config['airports_buffer']
if airports == 1 and param is not None:
    excluder.add_geometry(airportsPath, buffer=param)
    info_list_exclusion.append(f"airports buffer: {param}")
elif airports == 1 and param is None: info_list_not_selected.append("airports")
elif airports == 0: info_list_not_available.append("airports")

# Waterbodies
param = tech_config['waterbodies_buffer']
if waterbodies == 1 and param is not None:
    excluder.add_geometry(waterbodiesPath, buffer=param)
    info_list_exclusion.append(f"waterbodies buffer: {param}")
elif waterbodies == 1 and param is None: info_list_not_selected.append("waterbodies")
elif waterbodies == 0: info_list_not_available.append("waterbodies")

# Military
param = tech_config['military_buffer']
if military == 1 and param is not None:
    excluder.add_geometry(militaryPath, buffer=param)
    info_list_exclusion.append(f"military buffer: {param}")
elif military == 1 and param is None: info_list_not_selected.append("military")
elif military == 0: info_list_not_available.append("military")

# Coastlines
param = tech_config['coastlines_buffer']
if coastlines == 1 and param is not None:
    excluder.add_geometry(coastlinesPath, buffer=param)
    info_list_exclusion.append(f"coastlines buffer: {param}")
elif coastlines == 1 and param is None: info_list_not_selected.append("coastlines")
elif coastlines == 0: info_list_not_available.append("coastlines")

# Protected Areas
param = tech_config['protectedAreas_buffer']
if protectedAreas == 1 and param is not None:
    excluder.add_geometry(protectedAreasPath, buffer=param)
    info_list_exclusion.append(f"protected areas buffer: {param}")
elif protectedAreas == 1 and param is None: info_list_not_selected.append("protectedAreas")
elif protectedAreas == 0: info_list_not_available.append("protectedAreas")

# Transmission Lines
param = tech_config['transmission_lines_buffer']
if transmission == 1 and param is not None:
    excluder.add_geometry(transmissionPath, buffer=param)
    info_list_exclusion.append(f"transmission buffer: {param}")
elif transmission == 1 and param is None: info_list_not_selected.append("transmission")
elif transmission == 0: info_list_not_available.append("transmission")

# existing generators (points)
param = tech_config['generators_buffer']
if generators == 1 and param is not None:
    excluder.add_geometry(generatorsPath, buffer=param)
    info_list_exclusion.append(f"existing generators buffer: {param}")
elif generators == 1 and param is None: info_list_not_selected.append("existing generators")
elif generators == 0: info_list_not_available.append("existing generators")

# existing plants (polygons)
param = tech_config['plants_buffer']
if plants == 1 and param is not None:
    excluder.add_geometry(plantsPath, buffer=param)
    info_list_exclusion.append(f"existing plants buffer: {param}")
elif plants == 1 and param is None: info_list_not_selected.append("existing plants")
elif plants == 0: info_list_not_available.append("existing plants")


# add additional exclusion polygons
if additional_exclusion_polygons==1 and tech_config['additional_exclusion_polygons_buffer']:   
    for i, (buffer_value, filename) in enumerate(zip(tech_config['additional_exclusion_polygons_buffer'], os.listdir(additional_exclusion_polygons_Path))):
        filepath = os.path.join(additional_exclusion_polygons_Path, filename)    # Construct the full file path
        excluder.add_geometry(filepath, buffer=buffer_value)
        info_list_exclusion.append(f'additional exclusion polygon file {i+1}: {buffer_value}')
elif additional_exclusion_polygons == 1 and tech_config['additional_exclusion_polygons_buffer'] is None: info_list_not_selected.append("additional_exclusion_polygons_buffer")
elif additional_exclusion_polygons == 0: info_list_not_available.append("additional_exclusion_polygons_buffer")


# INCLUSION
# Substations (Inclusion Buffer)
param = tech_config['substations_inclusion_buffer']
if substations == 1 and param is not None:
    excluder.add_geometry(substationsPath, buffer=param, invert=True)
    info_list_exclusion.append(f"substations inclusion buffer: {param}")
elif substations == 1 and param is None: info_list_not_selected.append("substations")
elif substations == 0: info_list_not_available.append("substations")

# Transmission (Inclusion Buffer)
param = tech_config['transmission_inclusion_buffer']
if transmission == 1 and param is not None:
    excluder.add_geometry(transmissionPath, buffer=param, invert=True)
    info_list_exclusion.append(f"transmission inclusion buffer: {param}")
elif transmission == 1 and param is None: info_list_not_selected.append("transmission")
elif transmission == 0: info_list_not_available.append("transmission")

# Roads (Inclusion Buffer)
param = tech_config['roads_inclusion_buffer']
if roads == 1 and param is not None:
    excluder.add_geometry(roadsPath, buffer=param, invert=True)
    info_list_exclusion.append(f"roads inclusion buffer: {param}")
elif roads == 1 and param is None: info_list_not_selected.append("roads")
elif roads == 0: info_list_not_available.append("roads")


# data info
print('\nfollowing data was not found in data folder:')
for item in info_list_not_available:
    print('- ', item)
print('\nfollowing data was not selected in config:')
for item in info_list_not_selected:
    print('- ', item)

# test
with rasterio.open(landcoverPath, 'r+') as src:
    transform_lc = src.transform  # Only works in 'r+' or 'w' modes
    height = src.height
    width = src.width
    shape = (height, width)

# calculate available areas
print('\nperforming exclusions...')
#masked, transform = shape_availability(region.geometry, excluder)
masked, transform = shape_availability_reprojected(region.geometry, excluder, dst_transform=transform_lc, dst_crs=local_crs_obj, dst_shape=shape)

available_area = masked.sum() * excluder.res**2
eligible_share = available_area / region.geometry.item().area

# print results
print(f"\nEligibility share: {eligible_share:.2%}")
print(f'Available area: {available_area:.2} km²')
if tech_config['deployment_density']:
    power_potential = available_area*1e-6 * tech_config['deployment_density']
    print(f'Power potential: {power_potential:.2} MW')

print('\nfollowing data was considered during exclusion:')
for item in info_list_exclusion:
    print('- ', item)

min_pixels_connected = tech_config['min_pixels_connected']
#min_pixels_x=tech_config['min_pixels_x']
#min_pixels_y=tech_config['min_pixels_y']

masked_area_filtered = area_filter(masked,min_size=min_pixels_connected)
#masked_area_filtered = area_filter2(masked,min_x=5, min_y=5)

#array to be used 
array = masked_area_filtered

# Convert boolean array to integers (1 for True, 0 for False)
int_array = array.astype(np.uint8)

# Set 0 (False) to be the nodata value
nodata_value = 0

#save eligible land array as .tif file
# Define the metadata for the new file
# You'll need to adjust these parameters based on your specific data
metadata = {
    'driver': 'GTiff',
    'dtype': rasterio.uint8,
    'nodata': nodata_value,
    'width': array.shape[1],
    'height': array.shape[0],
    'count': 1,
    'crs': local_crs_obj,  
    'transform': transform,
    'compress': 'LZW' 
}

# Define output directory
output_dir = os.path.join(data_path, 'available_land')
os.makedirs(output_dir, exist_ok=True)
output_file_available_land = os.path.join(output_dir, f"{region_name_clean}_{technology}_{scenario}_available_land_{local_crs_tag}.tif")
# Write the array to a new .tif file
with rasterio.open(output_file_available_land, 'w', **metadata) as dst:
    dst.write(array, 1)
 


# model area stats
if config['model_areas_filename']:
    available_area_raster_filePath = os.path.join(output_file_available_land)

    modelAreasPath =os.path.join(dirname, 'Raw_Spatial_Data', 'model_areas', f"{config['model_areas_filename']}")
    model_areas = gpd.read_file(modelAreasPath)
    model_areas.to_crs(local_crs_obj, inplace=True)
    
    stats = zonal_stats(model_areas,
                    available_area_raster_filePath,
                    stats=['sum'])
    
    model_areas['pixel_count'] = [list(d.values())[0] for d in stats]
    model_areas['available_area_m2'] = model_areas['pixel_count'] * excluder.res**2
    model_areas['available_area_km2'] = model_areas['pixel_count'] *1e-6
    if config['deployment_density']:
        model_areas['power_potential_MW'] = (model_areas['available_area_m2']*1e-6) * config['deployment_density']

    # create summary table
    first_column = model_areas.columns[0]
    columns = [first_column, "pixel_count", "available_area_m2", "available_area_km2", "power_potential_MW"]
    subset = model_areas[columns]
    print('\npotentials in model areas:')
    print(subset.to_string(index=False))


# save info in textfile
with open(os.path.join(output_dir, f"{region_name_clean}_{scenario}_{technology}_exclusion_info.txt"), "w") as file:
    file.write(f"{technology}")
    file.write(f"\nscenario: {scenario}")
    file.write(f"\nmin pixels connected: {min_pixels_connected}\n\n")
    for item in info_list_exclusion:
        file.write(f"{item}\n")
    file.write(f"\neligibility share: {eligible_share:.2%}")
    file.write(f"\navailable area: {available_area:.2} m2")
    file.write(f"\npower potential: {power_potential:.2} MW")

    if config['model_areas_filename']:
        # Write table from GeoDataFrame subset
        file.write("\n\nResults for model areas:\n")
        file.write(subset.to_string(index=False))

# save info in JSON file for easier retrieval
info_data = {
    "technology": technology,
    "scenario": scenario,
    "min_pixels_connected": min_pixels_connected,
    "info_list": info_list_exclusion,
    "eligibility_share": eligible_share,
    "available_area_m2": available_area,
    "power_potential_MW": power_potential,
}

if config['model_areas_filename']:
    # Include summary table from GeoDataFrame subset
    info_data["model_areas"] = subset.to_dict(orient="records")

with open(
    os.path.join(
        output_dir,
        f"{region_name_clean}_{scenario}_{technology}_exclusion_info.json",
    ),
    "w",
) as file:
    json.dump(info_data, file, indent=2)