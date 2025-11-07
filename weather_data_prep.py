import atlite
import os
import yaml
import argparse
import geopandas as gpd


### --------- Input data and configuration ------------- ###

dirname = os.getcwd() 
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

region_name = config['study_region_name']
weather_year = config["weather_year"]
weather_data_extend = config['weather_data_extend'] 
country_code = config["country_code"]


# Initialize parser for command line arguments and define arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default=region_name, help="study region name")
parser.add_argument("--method",default="manual", help="method to run the script, e.g., snakemake or manual")
parser.add_argument("--weather_year", default=weather_year, help="weather year for the energy profiles")
args = parser.parse_args()

# If running via Snakemake, use the region name and folder name from command line arguments
if args.method == "snakemake":
    region_name= args.region
    weather_year = args.weather_year
    print(f'\nWeather data preparation')
    print(f"Running via snakemake - measures: weather_year={weather_year}")
else:
    print('\nWeather data preparation')
    print(f"Running manually - measures: weather_year={weather_year}")

# Weather data path
if config.get('weather_external_data_path'):
    weather_data_path = os.path.abspath(config["weather_external_data_path"])
else:
    weather_data_path = os.path.join(dirname, 'Raw_Spatial_Data', 'Weather_data')
os.makedirs(weather_data_path, exist_ok=True)


if weather_data_extend == 'geo_bounds':
    bounds = config["weather_data_geo_bounds"]
    bounds = [bounds['west'], bounds['south'], bounds['east'], bounds['north']]  # minx, miny, maxx, maxy
    cutout_file_path_1 = os.path.join(weather_data_path, f"{country_code}_{weather_year}_1.nc")
    cutout_file_path_2 = os.path.join(weather_data_path, f"{country_code}_{weather_year}_2.nc")
    cutout_file_path_3 = os.path.join(weather_data_path, f"{country_code}_{weather_year}_3.nc")
    cutout_file_path_4 = os.path.join(weather_data_path, f"{country_code}_{weather_year}_4.nc")
elif weather_data_extend == 'study_region':
    regionPath = os.path.join(dirname, 'data', f'{region_name}', f'{region_name}_EPSG4326.geojson')
    region = gpd.read_file(regionPath)
    bounds = region.total_bounds # minx, miny, maxx, maxy
    cutout_file_path_1 = os.path.join(weather_data_path, f"{region_name}_{weather_year}_1.nc")
    cutout_file_path_2 = os.path.join(weather_data_path, f"{region_name}_{weather_year}_2.nc")
    cutout_file_path_3 = os.path.join(weather_data_path, f"{region_name}_{weather_year}_3.nc")
    cutout_file_path_4 = os.path.join(weather_data_path, f"{region_name}_{weather_year}_4.nc")
else:
    raise ValueError("Invalid weather_data_extend value in config.yaml. Use 'geo_bounds' or 'region'.")

# Calculate bounding box which is 0.5 degrees bigger
d = 0.5
bounds = bounds + [-d, -d, d, d]
print(f"Bounding box (EPSG:4326): \nminx (West): {bounds[0]}, miny (South): {bounds[1]}, maxx (East): {bounds[2]}, maxy (North): {bounds[3]}")

#----------- Prepare weather data cutouts from ERA5 via Copernicus API ------------- ###
print("Processing weather year: ", weather_year)

t_start_1 = f"{weather_year}-01-01"
t_end_1   = f"{weather_year}-03-31"
t_start_2 = f"{weather_year}-04-01"
t_end_2   = f"{weather_year}-06-30"
t_start_3 = f"{weather_year}-07-01"
t_end_3   = f"{weather_year}-09-30"
t_start_4 = f"{weather_year}-10-01"
t_end_4   = f"{weather_year}-12-31"

# Request only needed features to keep jobs small
features = {
    "temperature": ["t2m"],         # 2m temperature
    "wind": ["wnd100m", "wnd10m"],  # wind at 100m & 10m
    "influx": ["influx_direct", "influx_diffuse"],  # solar components
    # add/remove as needed
}

# Define cutouts
cutout_1 = atlite.Cutout(path=cutout_file_path_1, features=features, module="era5", x=slice(bounds[0], bounds[2]), y=slice(bounds[1], bounds[3]), time=slice(t_start_1, t_end_1))
cutout_2 = atlite.Cutout(path=cutout_file_path_2, features=features, module="era5", x=slice(bounds[0], bounds[2]), y=slice(bounds[1], bounds[3]), time=slice(t_start_2, t_end_2))
cutout_3 = atlite.Cutout(path=cutout_file_path_3, features=features, module="era5", x=slice(bounds[0], bounds[2]), y=slice(bounds[1], bounds[3]), time=slice(t_start_3, t_end_3))
cutout_4 = atlite.Cutout(path=cutout_file_path_4, features=features, module="era5", x=slice(bounds[0], bounds[2]), y=slice(bounds[1], bounds[3]), time=slice(t_start_4, t_end_4))

# Connect to API and preprare/download cutouts
print(f"Preparing cutout from Climate Data Store API and downloading data to {weather_data_path}...")

if not os.path.exists(cutout_file_path_1):
    print(f"Time period: {t_start_1} to {t_end_1}")
    cutout_1.prepare()
else:
    print(f"Cutout file for time period {t_start_1} to {t_end_1} already exists. Skipping download.")

if not os.path.exists(cutout_file_path_2):
    print(f"Time period: {t_start_2} to {t_end_2}")
    cutout_2.prepare()
else:
    print(f"Cutout file for time period {t_start_2} to {t_end_2} already exists. Skipping download.")

if not os.path.exists(cutout_file_path_3):
    print(f"Time period: {t_start_3} to {t_end_3}")
    cutout_3.prepare()
else:
    print(f"Cutout file for time period {t_start_3} to {t_end_3} already exists. Skipping download.")

if not os.path.exists(cutout_file_path_4):
    print(f"Time period: {t_start_4} to {t_end_4}")
    cutout_4.prepare()
else:
    print(f"Cutout file for time period {t_start_4} to {t_end_4} already exists. Skipping download.")