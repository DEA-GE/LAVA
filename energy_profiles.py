import atlite
from atlite.gis import ExclusionContainer
import numpy as np
import xarray as xr
import pandas as pd
import matplotlib.pyplot as plt
import geopandas as gpd
from rasterio.plot import show
import os
import json
from pathlib import Path
import yaml
from utils.data_preprocessing import clean_region_name
import pickle
import argparse
import glob


#-----------------------------------Snakemake input to be implemented-----------------------------------#
weather_year = 1990
# region
# pontential_path


#------------------------------------------- Load configuration
dirname = os.getcwd() 
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 

region_folder_name = config['region_folder_name']
region_name = config['region_name'] #if country is studied, then use country name
region_name = clean_region_name(region_name)
technology=config["technology"]
scenario= config["scenario"]
weather_year = config["weather_year"]
print(f"Config parameters: region={region_name}, technology={technology}, weather_year={weather_year}")

# override values via command line arguments through snakemake
parser = argparse.ArgumentParser()
parser.add_argument("--region",default=region_name,  help="region and folder name")
parser.add_argument("--technology", default=technology, help="technology type")
parser.add_argument("--weather_year", default=weather_year, help="weather year for the energy profiles") 
args = parser.parse_args()

# Override values if provided in command line arguments wiht snakemake

region_name = clean_region_name(args.region)
region_folder_name = args.region
technology = args.technology
weather_year = args.weather_year
if (
    args.region != config['region_name'] or
    args.technology != config['technology'] or
    str(args.weather_year) != str(config['weather_year'])
):
    print(
        f"Using command line arguments: "
        f"region_name={region_name}, "
        f"region_folder_name={region_folder_name}, "
        f"technology={technology}, "
        f"weather_year={weather_year}"
    )

#load the technology specific configuration file
tech_config_file = os.path.join("configs", f"{technology}.yaml")
with open(tech_config_file, "r", encoding="utf-8") as f:
    tech_config = yaml.load(f, Loader=yaml.FullLoader)

data_path = os.path.join(dirname, 'data', region_folder_name)
output_path = os.path.join(data_path,"energy_profiles")
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

# load pixel size
if config['resolution_manual'] is not None:
    res = config['resolution_manual']
else:
    with open(os.path.join(data_path, f'pixel_size_{region_name}_{local_crs_tag}.json'), 'r') as fp:
        res = json.load(fp)


# TO DO: The 3 files per weather year should be merge into one file as part of the bias correction process 
weather_data_path = os.path.join(config['weather_data_path'], f'China_mainland_{weather_year}_1.nc')

# Load region geometry
regionPath = os.path.join(data_path, f'{region_name}_{local_crs_tag}.geojson')
region = gpd.read_file(regionPath)


# Open json file with resource grades
resource_grades_file = os.path.join(data_path, 'suitability', f'{region_name}_{scenario}_relevant_resource_grades.json')
with open(resource_grades_file, 'r') as f:
    resource_grades = json.load(f) 

# Load weather data cutout

# List all files in the weather data path starting with 'China_mainland' and ending with '.nc'
cutout_files = glob.glob(os.path.join(config['weather_data_path'], f'*_{weather_year}_*'))

cutout = atlite.Cutout(path=cutout_files[0])

# Regional entent
x1, y1, x2, y2 = region.to_crs(global_crs_obj).total_bounds 
offset = 1 # Offset to ensure the cutout includes the entire region

# Load bias correction data
ERA5_wnd100m_bias_path = os.path.join(config['weather_data_path'], 'bias_correction_factors', 'ERA5_wnd100m_bias.nc')
ERA5_wnd100m_bias = xr.open_dataset(ERA5_wnd100m_bias_path).sel(x=slice(x1 - offset, x2 + offset), y=slice(y1 - offset, y2 + offset))


# Preallocate a dataframe for resource grades and time series
time = pd.date_range(start=f'{weather_year}-01-01', end=f'{weather_year}-12-31 23:00', freq='h')
df_rg = pd.DataFrame(index=time, columns=resource_grades)

for cutout_file in cutout_files:
    print(f"Processing cutout file: {cutout_file}")
    cutout = atlite.Cutout(path=cutout_file).sel(x=slice(x1 - offset, x2 + offset), y=slice(y1 - offset, y2 + offset))
    # Apply bias correction to the weather data
    cutout.data['wnd100m'] = cutout.data['wnd100m'] * ERA5_wnd100m_bias['wnd100m']

    for rg in resource_grades:
        print(f"Processing resource grade: {rg}")
        # Load the resource grade
        potentialPath = os.path.join(
            data_path, 'suitability', 
            f"{rg}_{scenario}_{local_crs_tag}.tif"
        )
        
        # Loading potential
        excluder = ExclusionContainer(crs=local_crs_obj, res=res)
        excluder.add_raster(potentialPath, codes=1, invert=True)

        # Availability of the area
        masked, transform = excluder.compute_shape_availability(region)
        fig, ax = plt.subplots()
        excluder.plot_shape_availability(region)
        available_area = masked.sum(dtype=np.float64) * excluder.res**2
        eligible_share = available_area / region.geometry.item().area
        print(f"The eligibility share is: {eligible_share:.2%}")

        # `A` is an DataArray with 3 dimensions (`shape`, `x`, `y`) and very sparse data. 
        # It indicates the relative overlap of weather cell `(x, y)` with geometry `region` while excluding the area specified by the `excluder`. 
        A = cutout.availabilitymatrix(region, excluder)

        # Aggregation of potential to weather data cells
        fig, ax = plt.subplots()
        region.plot(ax=ax, edgecolor="k", color="None")
        A.plot(ax=ax, cmap="Greens")
        #cutout.grid.plot(ax=ax, color="None", edgecolor="grey")

        capacity_matrix = A.stack(spatial=["y", "x"])

        # Simulate the technology profiles based on the configuration
        match technology:
            case "solar":
                ds_tech = cutout.pv(
                    matrix=capacity_matrix,
                    panel=tech_config["solarpanel"],
                    orientation="latitude_optimal",
                    index=region.index,
                    per_unit=True
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

            case "solartracking":
                ds_tech = cutout.pv(
                    matrix=capacity_matrix,
                    panel=tech_config["solarpanel"],
                    orientation="latitude_optimal",
                    index=region.index,
                    tracking="horizontal",
                    per_unit=True
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

            case "onshorewind":
                ds_tech = cutout.wind(
                    matrix=capacity_matrix,
                    turbine=Path(tech_config["windturbine_onshore"]),
                    index=region.index,
                    per_unit=True
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

            case "offshorewind":
                ds_tech = cutout.wind(
                    matrix=capacity_matrix,
                    turbine=tech_config["windturbine_offshore"],
                    index=region.index,
                    per_unit=True
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

            case "hydro":
                plants, basins = hydro()
                ds_tech = cutout.hydro(
                    plants=plants,
                    hydrobasins=basins
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

            case _:
                raise ValueError(f"Unknown technology: {technology}")

        # Add resource grade to the dataframe
        df_tech = ds_tech.to_pandas()
        df_rg.loc[df_tech.index, rg] = df_tech.iloc[:, 0]

# Check for missing values and give warning if any are found
if df_rg.isnull().values.any():
    print("Warning: Missing values found in the resource grades dataframe.")

# Save the resource grade time series to a CSV file
output_file=os.path.join(output_path, f"{region_name}_{scenario}_{technology}_{weather_year}.csv")
df_rg.to_csv(output_file)