import atlite
import matplotlib.pyplot as plt
from scipy.ndimage import label
import math 
import numpy as np
import json 
import pickle
import os  
import geopandas as gpd
from rasterio.plot import show  
from atlite.gis import shape_availability
import rasterio
from rasterio.transform import Affine
import yaml
from unidecode import unidecode
from utils.data_preprocessing import clean_region_name

dirname = os.getcwd() 
#main_dir = os.path.join(dirname, '..')
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 


region_name = config['region_name'] #if country is studied, then use country name
region_name = clean_region_name(region_name)
print(region_name)

resampled = '_resampled' 

# construct folder paths
dirname = os.getcwd() 
data_path = os.path.join(dirname, 'data', config['region_folder_name'])
data_from_DEM = os.path.join(data_path, 'derived_from_DEM')

# Load the json EPSG code for the country
with open(os.path.join(data_path, region_name+'_EPSG.pkl'), 'rb') as file:
        EPSG = pickle.load(file)
#use custom EPSG instead of local UTM zone if wanted
if config['EPSG_manual']:
    EPSG=int(config['EPSG_manual'])

print(f'EPSG {EPSG}')


#path to file and check if it exists and save 1 or 0 for later
landcoverPath=os.path.join(data_path, f'landcover_{config['landcover_source']}_{region_name}_EPSG{EPSG}.tif')
landcover=0 if not os.path.isfile(landcoverPath) and print('no landcover file') is None else 1
demRasterPath = os.path.join(data_path, f'DEM_{region_name}_EPSG{EPSG}{resampled}.tif')
dem=0 if not os.path.isfile(demRasterPath) and print('no DEM file') is None else 1
slopeRasterPath = os.path.join(data_from_DEM, f'slope_{region_name}_EPSG{EPSG}{resampled}.tif')
slope=0 if not os.path.isfile(slopeRasterPath) and print('no slope file') is None else 1
windRasterPath = os.path.join(data_path, f'wind_{region_name}_EPSG{EPSG}{resampled}.tif')
wind=0 if not os.path.isfile(windRasterPath) and print('no wind file') is None else 1
solarRasterPath = os.path.join(data_path, f'solar_{region_name}_EPSG{EPSG}{resampled}.tif')
solar=0 if not os.path.isfile(solarRasterPath) and print('no solar file') is None else 1

regionPath =os.path.join(data_path, f'{region_name}_{EPSG}.geojson')
region = gpd.read_file(regionPath)

northfacingRasterPath = os.path.join(data_from_DEM, f'north_facing_{region_name}_EPSG{EPSG}{resampled}.tif')
nfacing=0 if not os.path.isfile(northfacingRasterPath) and print('no north facing pixels file') is None else 1
coastlinesPath = os.path.join(data_path, f'goas_{region_name}_{EPSG}.gpkg')
coastlines=0 if not os.path.isfile(coastlinesPath) and print('no coastlines file') is None else 1
protectedAreasPath = os.path.join(data_path, f'protected_areas_{config['consider_protected_areas']}_{region_name}_{EPSG}.gpkg')
protectedAreas=0 if not os.path.isfile(protectedAreasPath) and print('no protected areas file') is None else 1
#OSM
roadsPath = os.path.join(data_path, f'OSM_roads_{region_name}_{EPSG}.gpkg')
roads=0 if not os.path.isfile(roadsPath) and print('no roads file') is None else 1
railwaysPath = os.path.join(data_path, f'OSM_railways_{region_name}_{EPSG}.gpkg')
railways=0 if not os.path.isfile(railwaysPath) and print('no railways file') is None else 1
airportsPath = os.path.join(data_path, f'OSM_airports_{region_name}_{EPSG}.gpkg')
airports=0 if not os.path.isfile(airportsPath) and print('no airports file') is None else 1
waterbodiesPath = os.path.join(data_path, f'OSM_waterbodies_{region_name}_{EPSG}.gpkg')
waterbodies=0 if not os.path.isfile(waterbodiesPath) and print('no waterbodies file') is None else 1
militaryPath = os.path.join(data_path, f'OSM_military_{region_name}_{EPSG}.gpkg')
military=0 if not os.path.isfile(militaryPath) and print('no military file') is None else 1

#additional exclusion polygons
additional_exclusion_polygons_Path = os.path.join(data_path, 'additional_exclusion_polygons')
additional_exclusion_polygons=0 if not os.listdir(additional_exclusion_polygons_Path) and print('no additional exclusion polygon files') is None else 1

#load unique land use codes
with open(os.path.join(data_path, f'landuses_{region_name}.json'), 'r') as fp:
    landuses = json.load(fp)

#load pixel size
if config['resolution_manual'] is not None:
    res = config['resolution_manual']
elif not EPSG==4326:
    with open(os.path.join(data_path, f'pixel_size_{region_name}_{EPSG}.json'), 'r') as fp:
        res = json.load(fp)
else:
    res = 0.0009920634920634887558 #???? res for 4326

print(landuses)
print(len(landuses))
print(res)


#perform exclusions

#raster can be in different CRS than exclusioncontainer, it is co-registered by atlite!
#vector data needs to be in CRS of exclusioncontainer???


info_list_exclusion = []

#initiate Exclusion container
excluder = atlite.ExclusionContainer(crs=EPSG, res=res)

#add landcover exclusions
if config['landcover_without_buffer']:
    excluder.add_raster(landcoverPath, codes=config['landcover_without_buffer'],crs=EPSG)
    info_list_exclusion.append(f'landcover codes without buffer which are excluded: {config['landcover_without_buffer']}')
else: print('landcover without buffer not selected in config.')
    
if config['landcover_with_buffer']:   
    for key, value in config['landcover_with_buffer'].items():
        excluder.add_raster(landcoverPath, codes=key, buffer=value ,crs=EPSG)
    info_list_exclusion.append(f'landcover codes with buffer which are excluded: {config['landcover_with_buffer']}')
else: print('landcover with buffer not selected in config.')

#add elevation exclusions
if dem==1 and config['max_elevation'] is not None: 
    excluder.add_raster(demRasterPath, codes=range(config['max_elevation'],10000), crs=EPSG)
    info_list_exclusion.append(f'max elevation: {config['max_elevation']}')
else: print('DEM file not found or not selected in config.')

#add slope exclusions
if slope==1 and config['max_slope'] is not None: 
    excluder.add_raster(slopeRasterPath, codes=range(config['max_slope'],90), crs=EPSG)
    info_list_exclusion.append(f'max slope: {config['max_slope']}')
else: print('Slope file not found or not selected in config.')

#add north facing exclusion
if nfacing==1  and config['north_facing_pixels'] is not None: 
    excluder.add_raster(northfacingRasterPath, codes=1, crs=EPSG)
    info_list_exclusion.append(f'north facing pixels')
else: print('North-facing file not found or not selected in config.')

#add wind exclusions
def wind_filter(mask):
    if config['min_wind_speed'] is not None and config['max_wind_speed'] is not None:
        return (mask < config['min_wind_speed']) | (mask > config['max_wind_speed'])
    elif config['min_wind_speed'] is not None:
        return mask < config['min_wind_speed']
    elif config['max_wind_speed'] is not None:
        return mask > config['max_wind_speed']
    
if wind==1 and (config['min_wind_speed'] is not None or config['max_wind_speed'] is not None): 
    excluder.add_raster(windRasterPath, codes=wind_filter, crs=EPSG)
    if config['min_wind_speed'] is not None and config['max_wind_speed'] is not None: info=f'min wind speed: {config['min_wind_speed']}, max wind speed: {config['max_wind_speed']}'
    elif config['min_wind_speed'] is not None: info=f'min wind speed: {config['min_wind_speed']}'
    elif config['max_wind_speed'] is not None: info=f'max wind speed: {config['max_wind_speed']}'
    info_list_exclusion.append(f'{info}')
else: print('Wind file not found or not selected in config.')

#add solar exclusions
def solar_filter(mask): #desired yearly, specific solar production (kWh/kW) 
    if config['min_solar_production'] is not None and config['max_solar_production'] is not None:
        return (mask < config['min_solar_production']) | (mask > config['max_solar_production'])
    elif config['min_solar_production'] is not None:
        return mask < config['min_solar_production']
    elif config['max_solar_production'] is not None:
        return mask > config['max_solar_production']
    
if solar==1 and (config['min_solar_production'] is not None or config['max_solar_production'] is not None): 
    excluder.add_raster(solarRasterPath, codes=solar_filter, crs=EPSG)
    if config['min_solar_production'] is not None and config['max_solar_production'] is not None: info=f'min_solar_production: {config['min_solar_production']}, max_solar_production: {config['max_solar_production']}'
    elif config['min_solar_production'] is not None: info=f'min_solar_production: {config['min_solar_production']}'
    elif config['max_solar_production'] is not None: info=f'max_solar_production: {config['max_solar_production']}'
    info_list_exclusion.append(f'{info}')
else: print('Solar file not found or not selected in config.')


#add exclusions from vector data
if railways==1 and config['railways_buffer'] is not None: 
    excluder.add_geometry(railwaysPath, buffer=config['railways_buffer'])
    info_list_exclusion.append(f'railways buffer: {config['railways_buffer']}')
else: print('Railways file not found or not selected in config.')

if roads==1 and config['roads_buffer'] is not None: 
    excluder.add_geometry(roadsPath, buffer=config['roads_buffer'])
    info_list_exclusion.append(f'roads buffer: {config['roads_buffer']}')
else: print('Roads file not found or not selected in config.')

if airports==1 and config['airports_buffer'] is not None: 
    excluder.add_geometry(airportsPath, buffer=config['airports_buffer'])
    info_list_exclusion.append(f'airports buffer: {config['airports_buffer']}')
else: print('Airports file not found or not selected in config.')

if waterbodies==1 and config['waterbodies_buffer'] is not None: 
    excluder.add_geometry(waterbodiesPath, buffer=config['waterbodies_buffer'])
    info_list_exclusion.append(f'waterbodies buffer: {config['waterbodies_buffer']}')
else: print('Waterbodies file not found or not selected in config.')

if military==1 and config['military_buffer'] is not None: 
    excluder.add_geometry(militaryPath, buffer=config['military_buffer'])
    info_list_exclusion.append(f'military buffer: {config['military_buffer']}')
else: print('Military file not found or not selected in config.')

if coastlines==1 and config['coastlines_buffer'] is not None: 
    excluder.add_geometry(coastlinesPath, buffer=config['coastlines_buffer'])
    info_list_exclusion.append(f'coastlines buffer: {config['coastlines_buffer']}')
else: print('Coastlines file not found or not selected in config.')

if protectedAreas==1 and config['protectedAreas_buffer'] is not None: 
    excluder.add_geometry(protectedAreasPath, buffer=config['protectedAreas_buffer'])
    info_list_exclusion.append(f'protected areas buffer: {config['railways_buffer']}')
else: print('Protected Areas file not found or not selected in config.')


#add additional exclusion polygons
if additional_exclusion_polygons==1 and config['additional_exclusion_polygons_buffer']:   
    for i, (buffer_value, filename) in enumerate(zip(config['additional_exclusion_polygons_buffer'], os.listdir(additional_exclusion_polygons_Path))):
        filepath = os.path.join(additional_exclusion_polygons_Path, filename)    # Construct the full file path
        excluder.add_geometry(filepath, buffer=buffer_value)
        info_list_exclusion.append(f'additional exclusion polygon file {i+1}: {buffer_value}')
else: print('additional exclusion polygon files not found or not selected in config.')




#calculate available areas
masked, transform = shape_availability(region.geometry, excluder)

eligible_share = masked.sum() * excluder.res**2 / region.geometry.item().area
print()
print(f"The eligibility share is: {eligible_share:.2%}")

print()
print('following data was considered during exclusion:')
for item in info_list_exclusion:
    print('- ', item)



#area filter
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



min_pixels_connected = config['min_pixels_connected']
min_pixels_x=config['min_pixels_x']
min_pixels_y=config['min_pixels_y']

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
    'crs': rasterio.crs.CRS.from_epsg(EPSG),  # WGS84, modify as needed
    'transform': transform,
    'compress': 'LZW' 
}

# Define output directory
output_dir = os.path.join(data_path, 'available_land')
os.makedirs(output_dir, exist_ok=True)

# Write the array to a new .tif file
if masked_area_filtered in array:
    with rasterio.open(os.path.join(output_dir, f'{config['scenario']}_available_land_filtered-min{min_pixels_connected}_{region_name}_EPSG{EPSG}.tif'), 'w', **metadata) as dst:
        dst.write(array, 1)
else:
    with rasterio.open(os.path.join(output_dir, f'{config['scenario']}_available_land_total_{region_name}_EPSG{EPSG}.tif'), 'w', **metadata) as dst:
        dst.write(array, 1)    