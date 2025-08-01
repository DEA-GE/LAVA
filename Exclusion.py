import atlite
import matplotlib.pyplot as plt
from scipy.ndimage import label
import numpy as np
import json 
import pickle
import os  
import argparse
import geopandas as gpd
from rasterio.plot import show  
from atlite.gis import shape_availability
import rasterio
import yaml
from utils.data_preprocessing import clean_region_name
from rasterstats import zonal_stats

dirname = os.getcwd() 
#main_dir = os.path.join(dirname, '..')
config_file = os.path.join("configs", "config.yaml")
#load the configuration file
with open(config_file, "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

region_name = config['region_name'] #if country is studied, then use country name
region_name = clean_region_name(region_name)
region_folder_name = config['region_folder_name'] #folder name for the region, e.g., 'China' or 'Germany'
technology = config.get('technology') #technology, e.g., 'wind' or 'solar'
scenario=   config.get('scenario', 'ref') # scenario, e.g., 'ref' or 'high'
print(f"Config parameters: region={region_name}, technology={technology}, scenario={scenario}")

#Initialize parser for command line arguments and define arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default=region_name, help="region name")
parser.add_argument("--region_folder_name", default=region_folder_name, help="region folder name")
parser.add_argument("--technology", default=technology, help="technology type")
parser.add_argument("--method",default="manual", help="method to run the script, e.g., snakemake or manual")
args = parser.parse_args()

# If running via Snakemake, use the region name and folder name from command line arguments
if args.method == "snakemake":
    region_name = args.region
    region_folder_name = args.region_folder_name
    print(f"Running via snakemake - measures: region={region_name}, region_folder_name={region_folder_name}")
else:
    print(f"Running manually - measures: region={region_name}, region_folder_name={region_folder_name}")

#load the technology specific configuration file
tech_config_file = os.path.join("configs", f"{technology}.yaml")
with open(tech_config_file, "r", encoding="utf-8") as f:
    tech_config = yaml.load(f, Loader=yaml.FullLoader)

resampled = '' #'_resampled' 

# construct folder paths
dirname = os.getcwd() 
data_path = os.path.join(dirname, 'data', region_folder_name)
data_path_OSM = os.path.join(dirname, 'data', region_folder_name, 'OSM_Infrastructure')
data_from_DEM = os.path.join(data_path, 'derived_from_DEM')
OSM_source = config['OSM_source']

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


# path to file and check if it exists and save 1 or 0 for later
landcoverPath=os.path.join(data_path, f"landcover_{config['landcover_source']}_{region_name}_{local_crs_tag}.tif")
landcover=0 if not os.path.isfile(landcoverPath) and print('no landcover file') is None else 1
demRasterPath = os.path.join(data_path, f'DEM_{region_name}_{global_crs_tag}{resampled}.tif')
dem=0 if not os.path.isfile(demRasterPath) and print('no DEM file') is None else 1
slopeRasterPath = os.path.join(data_from_DEM, f'slope_{region_name}_{global_crs_tag}{resampled}.tif')
slope=0 if not os.path.isfile(slopeRasterPath) and print('no slope file') is None else 1
windRasterPath = os.path.join(data_path, f'wind_{region_name}_{global_crs_tag}{resampled}.tif')
wind=0 if not os.path.isfile(windRasterPath) and print('no wind file') is None else 1
solarRasterPath = os.path.join(data_path, f'solar_{region_name}_{global_crs_tag}{resampled}.tif')
solar=0 if not os.path.isfile(solarRasterPath) and print('no solar file') is None else 1

regionPath =os.path.join(data_path, f'{region_name}_{local_crs_tag}.geojson')
region = gpd.read_file(regionPath)

northfacingRasterPath = os.path.join(data_from_DEM, f'north_facing_{region_name}_{global_crs_tag}{resampled}.tif')
nfacing=0 if not os.path.isfile(northfacingRasterPath) and print('no north facing pixels file') is None else 1
coastlinesPath = os.path.join(data_path, f'goas_{region_name}_{global_crs_tag}.gpkg')
coastlines=0 if not os.path.isfile(coastlinesPath) and print('no coastlines file') is None else 1
protectedAreasPath = os.path.join(data_path, f"protected_areas_{config['protected_areas_source']}_{region_name}_{global_crs_tag}.gpkg")
protectedAreas=0 if not os.path.isfile(protectedAreasPath) and print('no protected areas file') is None else 1
# OSM
roadsPath = os.path.join(data_path_OSM, f'{OSM_source}_roads.gpkg') #_{region_name}_{global_crs_tag}
roads=0 if not os.path.isfile(roadsPath) and print('no roads file') is None else 1
railwaysPath = os.path.join(data_path_OSM, f'{OSM_source}_railways.gpkg')
railways=0 if not os.path.isfile(railwaysPath) and print('no railways file') is None else 1
airportsPath = os.path.join(data_path_OSM, f'{OSM_source}_airports.gpkg')
airports=0 if not os.path.isfile(airportsPath) and print('no airports file') is None else 1
waterbodiesPath = os.path.join(data_path_OSM, f'{OSM_source}_waterbodies.gpkg')
waterbodies=0 if not os.path.isfile(waterbodiesPath) and print('no waterbodies file') is None else 1
militaryPath = os.path.join(data_path_OSM, f'{OSM_source}_military.gpkg')
military=0 if not os.path.isfile(militaryPath) and print('no military file') is None else 1

# OSM overpass
substationsPath = os.path.join(data_path_OSM, f'{OSM_source}_substations.gpkg')
substations=0 if not os.path.isfile(substationsPath) and print('no substations file') is None else 1
transmissionPath = os.path.join(data_path_OSM, f'{OSM_source}_transmission_lines.gpkg')
transmission=0 if not os.path.isfile(transmissionPath) and print('no transmission file') is None else 1




# additional exclusion polygons
additional_exclusion_polygons_Path = os.path.join(data_path, 'additional_exclusion_polygons')
additional_exclusion_polygons=0 if not os.path.exists(additional_exclusion_polygons_Path) and print('no additional exclusion polygon files') is None else 1

# load unique land use codes
with open(os.path.join(data_path, f'landuses_{region_name}.json'), 'r') as fp:
    landuses = json.load(fp)

# load pixel size
if config['resolution_manual'] is not None:
    res = config['resolution_manual']
else:
    with open(os.path.join(data_path, f'pixel_size_{region_name}_{local_crs_tag}.json'), 'r') as fp:
        res = json.load(fp)
    

#perform exclusions

#raster can be in different CRS than exclusioncontainer, it is co-registered by atlite!
#vector data needs to be in CRS of exclusioncontainer???


info_list_exclusion = []

# initiate Exclusion container
excluder = atlite.ExclusionContainer(crs=local_crs_obj, res=res)

# add landcover exclusions
if tech_config['landcover_without_buffer']:
    input_codes = tech_config['landcover_without_buffer']
    excluder.add_raster(landcoverPath, codes=input_codes,crs=local_crs_obj)
    info_list_exclusion.append(f"landcover codes without buffer which are excluded: {input_codes}")
else: print('landcover without buffer not selected in config.')
    
if tech_config['landcover_with_buffer']:   
    input_codes = tech_config['landcover_with_buffer']
    for key, value in input_codes.items():
        excluder.add_raster(landcoverPath, codes=key, buffer=value ,crs=local_crs_obj)
    info_list_exclusion.append(f"landcover codes with buffer which are excluded: {input_codes}")
else: print('landcover with buffer not selected in config.')

# add elevation exclusions
if dem==1 and tech_config['max_elevation'] is not None: 
    param= tech_config['max_elevation']
    excluder.add_raster(demRasterPath, codes=range(param,10000), crs=global_crs_obj)
    info_list_exclusion.append(f"max elevation: {param}")
else: print('DEM file not found or not selected in config.')

# add slope exclusions
if slope==1 and tech_config['max_slope'] is not None: 
    param= tech_config['max_slope']
    excluder.add_raster(slopeRasterPath, codes=range(param,90), crs=global_crs_obj)
    info_list_exclusion.append(f"max slope: {param}")
else: print('Slope file not found or not selected in config.')

# add north facing exclusion
if nfacing==1  and config['north_facing_pixels'] is not None: 
    excluder.add_raster(northfacingRasterPath, codes=1, crs=global_crs_obj)
    info_list_exclusion.append(f'north facing pixels')
else: print('North-facing file not found or not selected in config.')


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
else: print('Wind technology not selected in config.')

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
else:
    print("Solar file not found or not selected in config.")



# add exclusions from vector data
if railways==1 and tech_config['railways_buffer'] is not None: 
    excluder.add_geometry(railwaysPath, buffer=tech_config['railways_buffer'])
    info_list_exclusion.append(f"railways buffer: {tech_config['railways_buffer']}")
else: print('Railways file not found or not selected in config.')

if roads==1 and tech_config['roads_buffer'] is not None: 
    excluder.add_geometry(roadsPath, buffer=tech_config['roads_buffer'])
    info_list_exclusion.append(f"roads buffer: {tech_config['roads_buffer']}")
else: print('Roads file not found or not selected in config.')

if airports==1 and tech_config['airports_buffer'] is not None: 
    excluder.add_geometry(airportsPath, buffer=tech_config['airports_buffer'])
    info_list_exclusion.append(f"airports buffer: {tech_config['airports_buffer']}")
else: print('Airports file not found or not selected in config.')

if waterbodies==1 and tech_config['waterbodies_buffer'] is not None: 
    excluder.add_geometry(waterbodiesPath, buffer=tech_config['waterbodies_buffer'])
    info_list_exclusion.append(f"waterbodies buffer: {tech_config['waterbodies_buffer']}")
else: print('Waterbodies file not found or not selected in config.')

if military==1 and tech_config['military_buffer'] is not None: 
    excluder.add_geometry(militaryPath, buffer=tech_config['military_buffer'])
    info_list_exclusion.append(f"military buffer: {tech_config['military_buffer']}")
else: print('Military file not found or not selected in config.')

if coastlines==1 and tech_config['coastlines_buffer'] is not None: 
    excluder.add_geometry(coastlinesPath, buffer=tech_config['coastlines_buffer'])
    info_list_exclusion.append(f"coastlines buffer: {tech_config['coastlines_buffer']}")
else: print('Coastlines file not found or not selected in config.')

if protectedAreas==1 and tech_config['protectedAreas_buffer'] is not None: 
    excluder.add_geometry(protectedAreasPath, buffer=tech_config['protectedAreas_buffer'])
    info_list_exclusion.append(f"protected areas buffer: {tech_config['protectedAreas_buffer']}")
else: print('Protected Areas file not found or not selected in config.')

if transmission==1 and tech_config['transmission_lines_buffer'] is not None: 
    excluder.add_geometry(transmissionPath, buffer=tech_config['transmission_lines_buffer'])
    info_list_exclusion.append(f"transmission buffer: {tech_config['transmission_lines_buffer']}")
else: print('Transmission file not found or not selected in config.')

# INCLUSION
if substations==1 and tech_config['substations_inclusion_buffer'] is not None: 
    excluder.add_geometry(substationsPath, buffer=tech_config['substations_inclusion_buffer'], invert=True)
    info_list_exclusion.append(f"substations inclusion buffer: {tech_config['substations_inclusion_buffer']}")
else: print('Substations file not found or not selected in config.')

if transmission==1 and tech_config['transmission_inclusion_buffer'] is not None: 
    excluder.add_geometry(transmissionPath, buffer=tech_config['transmission_inclusion_buffer'], invert=True)
    info_list_exclusion.append(f"transmission inclusion buffer: {tech_config['transmission_inclusion_buffer']}")
else: print('Transmission file not found or not selected in config.')



# add additional exclusion polygons
if additional_exclusion_polygons==1 and tech_config['additional_exclusion_polygons_buffer']:   
    for i, (buffer_value, filename) in enumerate(zip(tech_config['additional_exclusion_polygons_buffer'], os.listdir(additional_exclusion_polygons_Path))):
        filepath = os.path.join(additional_exclusion_polygons_Path, filename)    # Construct the full file path
        excluder.add_geometry(filepath, buffer=buffer_value)
        info_list_exclusion.append(f'additional exclusion polygon file {i+1}: {buffer_value}')
else: print('additional exclusion polygon files not found or not selected in config.')




# calculate available areas
masked, transform = shape_availability(region.geometry, excluder)

available_area = masked.sum() * excluder.res**2
eligible_share = available_area / region.geometry.item().area

# print results
print(f"\nThe eligibility share is: {eligible_share:.2%}")
print(f'The available area is: {available_area:.2} km²')
if tech_config['deployment_density']:
    power_potential = available_area*1e-6 * tech_config['deployment_density']
    print(f'Power potential: {power_potential:.2} MW')

print('\nfollowing data was considered during exclusion:')
for item in info_list_exclusion:
    print('- ', item)



# area filter
def area_filter(boolean_array, min_size):
    # Label connected components in the array
    labeled_array, num_features = label(boolean_array)
    
    # Count the number of pixels in each component
    component_sizes = np.bincount(labeled_array.ravel())
    
    # Create a mask for components that meet the size requirement (ignoring the background)
    large_component_mask = np.zeros_like(component_sizes, dtype=bool)
    large_component_mask[1:] = component_sizes[1:] >= min_size  # Skip the background component (index 0)
    
    # Filter the original array, keeping only large components
    filtered_array = large_component_mask[labeled_array]
    
    return filtered_array



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
output_file_available_land = os.path.join(output_dir, f"{region_name}_{technology}_{scenario}_available_land_{local_crs_tag}.tif")
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
with open(os.path.join(output_dir, f"{region_name}_{scenario}_{technology}_exclusion_info.txt"), "w") as file:
    for item in info_list_exclusion:
        file.write(f"{item}\n")
    file.write(f"\neligibility share: {eligible_share:.2%}")
    file.write(f"\navailable area: {available_area:.2} m2")
    file.write(f"\npower potential: {power_potential:.2} MW")

    if config['model_areas_filename']:
        # Write table from GeoDataFrame subset
        file.write("\n\nResults for model areas:\n")
        file.write(subset.to_string(index=False))