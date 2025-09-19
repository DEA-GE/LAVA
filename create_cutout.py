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

with open(os.path.join(dirname, "configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)  

#--------------------------------------------------------------
# read from config and load data
weather_years = config['weather_years']
weather_data_extend = config['weather_data_extend'] 
study_region_name = config['study_region_name']
region_name = clean_region_name(study_region_name) 

# decide to download weather data for the whole country or only for study region
if weather_data_extend == 'country':
    country_code = config['country_code']
    region = pygadm.Items(admin=country_code)
    region.set_crs('epsg:4326', inplace=True) 
elif weather_data_extend == 'region':
    regionPath = os.path.join(dirname, 'data', f'{region_name}', f'{region_name}_EPSG4326.geojson')
    region = gpd.read_file(regionPath)
#--------------------------------------------------------------

# outout directory
output_dir = os.path.join(dirname, 'data', 'weather_data', f'{region_name}_weather_data')
os.makedirs(output_dir, exist_ok=True)

# calculate bounding box which is 0.3 degrees bigger
d = 0.3
bounds = region.total_bounds + [-d, -d, d, d]
print(f"Bounding box (EPSG:4326): \nminx: {bounds[0]}, miny: {bounds[1]}, maxx: {bounds[2]}, maxy: {bounds[3]}")

for weather_year in weather_years:
    print(f"Downloading weather data for year {weather_year} ...")

    # download settings
    cutout = atlite.Cutout(
        path=os.path.join(output_dir,f"{region_name}-{weather_year}-era5.nc"), 
        module="era5", 
        x=slice(bounds[0], bounds[2]),  
        y=slice(bounds[1], bounds[3]),
        time=str(weather_year)
        #time=("2022-07-01","2023-06-30")
    )

    # download
    print('\ncheck status: https://cds.climate.copernicus.eu/requests?tab=all\n')
    cutout.prepare(features=['wind','influx','temperature']) #, monthly_requests=True, concurrent_requests=True, compression=None) 
    #cutout.prepare(features=['influx', 'temperature'], monthly_requests=True, concurrent_requests=True, compression=None)
