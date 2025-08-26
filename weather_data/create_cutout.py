import geopandas as gpd
import pygadm
import atlite
import os
import logging
import yaml
import pickle
from utils.data_preprocessing import *

logging.basicConfig(level=logging.INFO)

dirname = os.getcwd() 
dirname = os.path.join(dirname, '..') #go one folder up to main dir of tool

with open(os.path.join(dirname, "configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)  

#--------------------------------------------------------------
# read from config and load data
weather_year = config['weather_year']
study_region_name = config['study_region_name']
region_name_clean = clean_region_name(study_region_name) 
custom_study_area_filename = config['custom_study_area_filename']
# load study region
regionPath = os.path.join(dirname, 'Raw_Spatial_Data', 'custom_study_area', f'{custom_study_area_filename}.geojson')
region = gpd.read_file(regionPath)
#--------------------------------------------------------------

# outout directory
output_dir = os.path.join(dirname, 'weather_data', f'{region_name_clean}_weather_data')
os.makedirs(output_dir, exist_ok=True)
data_path = output_dir


# # Load the CRS
# # geo CRS
# with open(os.path.join(data_path, region_name_clean+'_global_CRS.pkl'), 'rb') as file:
#         global_crs_obj = pickle.load(file)
# # projected CRS
# with open(os.path.join(data_path, region_name_clean+'_local_CRS.pkl'), 'rb') as file:
#         local_crs_obj = pickle.load(file)
# # Extract tag for filename, e.g., 'EPSG3035' or 'ESRI102003'
# auth = global_crs_obj.to_authority()
# global_crs_tag = ''.join(auth) if auth else global_crs_obj.to_string().replace(":", "_")
# auth = local_crs_obj.to_authority()
# local_crs_tag = ''.join(auth) if auth else local_crs_obj.to_string().replace(":", "_")

# load study region
# regionPath = os.path.join(data_path, f'{region_name_clean}_{global_crs_tag}.geojson')
# region = gpd.read_file(regionPath)
# calculate bounding box which is 0.3 degrees bigger
d = 0.3
bounds = region.total_bounds + [-d, -d, d, d]
print(f"Bounding box (EPSG:4326): \nminx: {bounds[0]}, miny: {bounds[1]}, maxx: {bounds[2]}, maxy: {bounds[3]}")

# download settings
cutout = atlite.Cutout(
    path=os.path.join(data_path,f"{region_name_clean}-{weather_year}-era5.nc"), 
    module="era5", 
    x=slice(bounds[0], bounds[2]),  
    y=slice(bounds[1], bounds[3]),
    time=str(weather_year)
    #time=("2022-07-01","2023-06-30")
)

# download
# check status: https://cds.climate.copernicus.eu/requests?tab=all
cutout.prepare(features=['wind','influx','temperature']) #, monthly_requests=True, concurrent_requests=True, compression=None) 
#cutout.prepare(features=['influx', 'temperature'], monthly_requests=True, concurrent_requests=True, compression=None)
