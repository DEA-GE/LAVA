import argparse
import geopandas as gpd
import pygadm
import atlite
import os
import logging
import yaml
from utils.data_preprocessing import *

logging.basicConfig(level=logging.INFO)

dirname = os.getcwd() 

with open(os.path.join(dirname, "configs/config_template.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)  

#---set variables for script----------------------------------------------------------
# read from config as default
weather_data_folder = config.get('weather_data_folder')
weather_years = config["weather_years"]["years"]
weather_year_start = config["weather_years"]["start"]
weather_year_end = config["weather_years"]["end"]
ERA5_variables = config.get('ERA5_variables')
weather_data_extend = config.get('weather_data_extend')
study_region_name = config['study_region_name']
region_name = clean_region_name(study_region_name) 

# alternatively get input via command line/snakemake
parser = argparse.ArgumentParser()
parser.add_argument("--weather_data_folder", default=weather_data_folder, help="output directory for weather data")
parser.add_argument("--weather_years", default=weather_years, type=int, nargs='+', help="weather years to download") # accept one or more values
parser.add_argument("--ERA5_variables", default=ERA5_variables, nargs='+', help="ERA5 variables to download") # accept one or more values
parser.add_argument("--weather_data_extend", default=weather_data_extend, help="extent of weather data to download")
parser.add_argument("--study_region_name", default=study_region_name, help="study region name")
parser.add_argument("--region", default=region_name, help="cleaned region name")
parser.add_argument("--method", default="manual", help="method to run the script, e.g., snakemake or manual")
args = parser.parse_args()

# If running via Snakemake, use the region name and folder name from command line arguments
if args.method == "snakemake":
    print(f'\nWeather data download')
    print(f"Running via snakemake")
else:
    print('\nWeather data download')
    print(f"Running manually")

# Update variables from command line arguments
weather_data_folder = args.weather_data_folder
weather_years = args.weather_years
ERA5_variables = args.ERA5_variables
weather_data_extend = args.weather_data_extend
study_region_name = args.study_region_name
region_name = args.region

# print all parameters used for the script
print(f"\nArguments used:")
for arg, value in vars(args).items():
    print(f"  {arg}: {value}")


# decide to download weather data for the whole country or only for study region
if weather_data_extend == 'gadm_country':
    country_code = config['country_code']
    region = pygadm.Items(admin=country_code)
    region.set_crs('epsg:4326', inplace=True) 
    logging.info(f"download weather data for gadm_country: {country_code}")
    region_name = country_code
elif weather_data_extend == 'gadm_region':
    regionPath = os.path.join(dirname, 'data', f'{region_name}', f'{region_name}_EPSG4326.geojson')
    region = gpd.read_file(regionPath)
    region.set_crs('epsg:4326', inplace=True) 
    logging.info(f"download weather data for gadm_region: {region_name}")
elif weather_data_extend == 'custom_study_area':
    custom_study_area_filename = config.get('custom_study_area_filename')
    regionPath = os.path.join('Raw_Spatial_Data','custom_study_area', custom_study_area_filename)
    region = gpd.read_file(regionPath)
    logging.info(f"download weather data for custom_study_area: {custom_study_area_filename}")
elif weather_data_extend == 'bbox':
    bbox = config.get('bbox')
    logging.info(f"download weather data for bounding box: {bbox}")
#--------------------------------------------------------------

# outout directory
output_dir = os.path.join(dirname, weather_data_folder)
os.makedirs(output_dir, exist_ok=True)


# calculate bounding box which is 0.3 degrees bigger
if not weather_data_extend == 'bbox':
    d = 0.3
    bounds = region.total_bounds + [-d, -d, d, d]
    print(f"Bounding box (EPSG:4326): \nminx: {bounds[0]}, miny: {bounds[1]}, maxx: {bounds[2]}, maxy: {bounds[3]}")
elif weather_data_extend == 'bbox':
    bounds = bbox
    print(f"Bounding box (EPSG:4326): \nminx: {bounds[0]}, miny: {bounds[1]}, maxx: {bounds[2]}, maxy: {bounds[3]}")

for weather_year in weather_years:
    print(f"\nDownloading weather data for year {weather_year} \n start: {weather_year_start} \n end: {weather_year_end}")
    # download settings
    cutout = atlite.Cutout(
        path=os.path.join(output_dir,f"{region_name}-{weather_year}-era5.nc"), 
        module="era5", 
        x=slice(bounds[0], bounds[2]),  
        y=slice(bounds[1], bounds[3]),
 #       time=str(weather_year)
        time=slice(f"{weather_year}-{weather_year_start}",f"{weather_year}-{weather_year_end}")
    )

    # download
    print('\ncheck status: https://cds.climate.copernicus.eu/requests?tab=all\n')
    cutout.prepare(features=ERA5_variables, monthly_requests=True, concurrent_requests=True, compression=None) 
    #cutout.prepare(features=['influx', 'temperature'], monthly_requests=True, concurrent_requests=True, compression=None)
