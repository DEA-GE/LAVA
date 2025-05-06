"""
This script is used to create the resource grades using the Atlite excluder function.
It reads the land and infrastructure data prepared in the spatial data preparation script and stores it in the "input data" folder. 
For each region, it produces several resource grades based on desired criteria.
The output is a series of raster files stored in the "processed input data" folder.
"""

"""
TODO:
- Add the option to include global wind and solar atlases
- EPSG is loaded from the file, which one should be used?
- store the output in the "processed input data" folder
- read from the folder input data
- include looping for all regions

"""



# Install atlite if not already installed

# Import necessary libraries
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
from utils.data_preprocessing import *
from unidecode import unidecode
import atlite
import atlite

# Load configuration file
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 

# Clean and prepare region name
region_name = clean_region_name(config['region_name'])

# Define paths and directories
dirname = os.getcwd()
data_path = os.path.join(dirname, 'data', config['region_folder_name']) # this would read from the folder "input data"
data_from_DEM = os.path.join(data_path, 'derived_from_DEM')

# Load EPSG code for the region
with open(os.path.join(data_path, region_name + '_EPSG.pkl'), 'rb') as file:
    EPSG = pickle.load(file)
if config['EPSG_manual']:
    EPSG = int(config['EPSG_manual'])  # Use custom EPSG if specified

# Load region geometry
regionPath = os.path.join(data_path, f'{region_name}_{EPSG}.geojson')
region = gpd.read_file(regionPath)


# Check for required input files and set flags
landcoverPath = os.path.join(data_path, f'landcover_{region_name}_EPSG{EPSG}.tif')
landcover = 0 if not os.path.isfile(landcoverPath) else 1
demRasterPath = os.path.join(data_path, f'DEM_{region_name}_EPSG{EPSG}_resampled.tif')
dem = 0 if not os.path.isfile(demRasterPath) else 1
slopeRasterPath = os.path.join(data_from_DEM, f'slope_{region_name}_EPSG{EPSG}_resampled.tif')
slope = 0 if not os.path.isfile(slopeRasterPath) else 1
northfacingRasterPath = os.path.join(data_from_DEM, f'north_facing_{region_name}_EPSG{EPSG}_resampled.tif')
nfacing = 0 if not os.path.isfile(northfacingRasterPath) else 1


# Load additional input files and set flags
coastlinesPath = os.path.join(data_path, f'goas_{region_name}_{EPSG}.gpkg')
coastlines = 0 if not os.path.isfile(coastlinesPath) else 1
protectedAreasPath = os.path.join(data_path, f'protected_areas_{region_name}_{EPSG}.gpkg')
protectedAreas = 0 if not os.path.isfile(protectedAreasPath) else 1
roadsPath = os.path.join(data_path, f'OSM_roads_{region_name}_{EPSG}.gpkg')
roads = 0 if not os.path.isfile(roadsPath) else 1
railwaysPath = os.path.join(data_path, f'OSM_railways_{region_name}_{EPSG}.gpkg')
railways = 0 if not os.path.isfile(railwaysPath) else 1
airportsPath = os.path.join(data_path, f'OSM_airports_{region_name}_{EPSG}.gpkg')
airports = 0 if not os.path.isfile(airportsPath) else 1
waterbodiesPath = os.path.join(data_path, f'OSM_waterbodies_{region_name}_{EPSG}.gpkg')
waterbodies = 0 if not os.path.isfile(waterbodiesPath) else 1
militaryPath = os.path.join(data_path, f'OSM_military_{region_name}_{EPSG}.gpkg')
military = 0 if not os.path.isfile(militaryPath) else 1

# Load landcover codes and pixel size
with open(os.path.join(data_path, f'landuses_{region_name}.json'), 'r') as fp:
    landuses = json.load(fp)
if EPSG != 4326:
    with open(os.path.join(data_path, f'pixel_size_{region_name}_{EPSG}.json'), 'r') as fp:
        res = json.load(fp)
else:
    # this resolution is quite high. 0.001 degrees is 100m, using 1km is more reasonable
    res = 0.0009920634920634887558  # Default resolution for EPSG:4326

# Initialize Atlite ExclusionContainer
excluder = atlite.ExclusionContainer(crs=EPSG, res=res)

# Add raster-based exclusions
if landcover:
    excluder.add_raster(landcoverPath, codes=config['landcover_without_buffer'], crs=EPSG)
    if config['landcover_with_buffer']:
        for key, value in config['landcover_with_buffer'].items():
            excluder.add_raster(landcoverPath, codes=key, buffer=value, crs=EPSG)
if dem:
    excluder.add_raster(demRasterPath, codes=range(config['max_elevation'], 10000), crs=EPSG)
if slope:
    excluder.add_raster(slopeRasterPath, codes=range(config['max_slope'], 90), crs=EPSG)
if nfacing:
    excluder.add_raster(northfacingRasterPath, codes=1, crs=EPSG)

#include global wind atlas
#include global solar atlas

# Add vector-based exclusions
if railways:
    excluder.add_geometry(railwaysPath, buffer=config['railways_buffer'])
if roads:
    excluder.add_geometry(roadsPath, buffer=config['roads_buffer'])
if airports:
    excluder.add_geometry(airportsPath, buffer=config['airports_buffer'])
if waterbodies:
    excluder.add_geometry(waterbodiesPath, buffer=config['waterbodies_buffer'])
if military:
    excluder.add_geometry(militaryPath, buffer=config['military_buffer'])
if coastlines:
    excluder.add_geometry(coastlinesPath, buffer=config['coastlines_buffer'])
if protectedAreas:
    excluder.add_geometry(protectedAreasPath, buffer=config['protectedAreas_buffer'])

# Calculate available areas
masked, transform = shape_availability(region.geometry, excluder)
eligible_share = masked.sum() * excluder.res**2 / region.geometry.item().area
print(f"The eligibility share is: {eligible_share:.2%}")

# Plot the availability map
fig, ax = plt.subplots(figsize=(10, 10))
excluder.plot_shape_availability(region)

# Filter areas based on minimum connected pixels
def area_filter(boolean_array, min_size):
    labeled_array, num_features = label(boolean_array)
    component_sizes = np.bincount(labeled_array.ravel())
    large_component_mask = np.zeros_like(component_sizes, dtype=bool)
    large_component_mask[1:] = component_sizes[1:] >= min_size
    return large_component_mask[labeled_array]

min_pixels_connected = config['min_pixels_connected']
masked_area_filtered = area_filter(masked, min_size=min_pixels_connected)


"""
the output should be the resource grades in the processed input data folder
"""

# Save the filtered eligible land as a raster file
array = masked_area_filtered.astype(np.uint8)
metadata = {
    'driver': 'GTiff',
    'dtype': rasterio.uint8,
    'nodata': 0,
    'width': array.shape[1],
    'height': array.shape[0],
    'count': 1,
    'crs': rasterio.crs.CRS.from_epsg(EPSG),
    'transform': transform,
    'compress': 'LZW'
}
output_filename = f'available_land_filtered-min{min_pixels_connected}_{region_name}_EPSG{EPSG}.tif'
with rasterio.open(os.path.join(data_path, output_filename), 'w', **metadata) as dst:
    dst.write(array, 1)
