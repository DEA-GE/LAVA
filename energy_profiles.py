import atlite
import numpy as np
import xarray as xr
import pandas as pd
import matplotlib.pyplot as plt
import geopandas as gpd
import os
import json
from pathlib import Path
import yaml
from utils.data_preprocessing import clean_region_name, rel_path
import pickle
import argparse
import glob

#------------------------------------------- Load configuration
dirname = os.getcwd() 
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 

region_name = config['study_region_name']
region_name = clean_region_name(region_name)
technology = config["technology"]
scenario = config.get('scenario', 'ref') # scenario, e.g., 'ref' or 'high'
weather_year = config["weather_year"]

# override values via command line arguments through snakemake
parser = argparse.ArgumentParser()
parser.add_argument("--region",default=region_name,  help="region name")
parser.add_argument("--technology", default=technology, help="technology type")
parser.add_argument("--method",default="manual", help="method to run the script, e.g., snakemake or manual")
parser.add_argument("--scenario", default=scenario, help="scenario name")
parser.add_argument("--weather_year", default=weather_year, help="weather year for the energy profiles")
args = parser.parse_args()

# If running via Snakemake, use the region name and folder name from command line arguments
if args.method == "snakemake":
    region_name = args.region
    technology = args.technology
    scenario = args.scenario
    weather_year = args.weather_year
    print(f"Running via snakemake - measures: region={region_name}, technology={technology}, scenario={scenario}, weather_year={weather_year}")
else:
    print(f"Running manually - measures: region={region_name}, technology={technology}, scenario={scenario}, weather_year={weather_year}")

#load the technology specific configuration file
tech_config_file = os.path.join("configs", f"{technology}.yaml")
with open(tech_config_file, "r", encoding="utf-8") as f:
    tech_config = yaml.load(f, Loader=yaml.FullLoader)

data_path = os.path.join(dirname, 'data', region_name)
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
if tech_config['resolution_manual'] is not None:
    res = config['resolution_manual']
else:
    with open(os.path.join(data_path, f'pixel_size_{region_name}_{local_crs_tag}.json'), 'r') as fp:
        res = json.load(fp)

# Load region geometry
regionPath = os.path.join(data_path, f'{region_name}_{local_crs_tag}.geojson')
region = gpd.read_file(regionPath)

# Define potential list based on the selected method
input_area = config['input_area']
if input_area == 'resource_grades':
    # Open json file with resource grades
    resource_grades_file = os.path.join(data_path, 'suitability', f'{region_name}_{technology}_{scenario}_relevant_resource_grades.json')
    with open(resource_grades_file, 'r') as f:
        potential_list = json.load(f)
elif input_area == 'available_land':
    potential_list = [region_name]
elif input_area == 'study_region':
    potential_list = [region_name]
else:
    raise ValueError(f"Unknown potential method: {input_area}")

# List all files in the weather data files (in case of multiple files per year)
if config.get('weather_external_data_path'):
    weather_data_path = os.path.abspath(config["weather_external_data_path"])
else:
    weather_data_path = os.path.join(dirname, 'Raw_Spatial_Data', 'Weather_data')
cutout_files = glob.glob(os.path.join(weather_data_path, f'*{weather_year}*'))

# Regional entent
x1, y1, x2, y2 = region.to_crs(global_crs_obj).total_bounds 
offset = 1 # Offset to ensure the cutout includes the entire region

# Open netcdf cutout files
ds = xr.open_mfdataset(cutout_files)

# Pre-allocate a dataframe for potentials and time series
time = pd.date_range(start=f'{weather_year}-01-01', end=f'{weather_year}-12-31 23:00', freq='h')
df_pot = pd.DataFrame(index=time, columns=potential_list)

for cutout_file in cutout_files:
    print(f"Processing cutout file: {rel_path(cutout_file)}")
    
    cutout = atlite.Cutout(path=cutout_file).sel(x=slice(x1 - offset, x2 + offset), y=slice(y1 - offset, y2 + offset))

    # Apply bias correction to the wind data
    if config['weather_bias_correction'][technology]:
        # Load bias correction data
        if technology in ['onshorewind', 'offshorewind']:
            ERA5_wnd100m_bias_path = os.path.join(weather_data_path, 'bias_correction_factors', 'ERA5_wnd100m_bias.nc')
            ERA5_wnd100m_bias = xr.open_dataset(ERA5_wnd100m_bias_path).sel(x=slice(x1 - offset, x2 + offset), y=slice(y1 - offset, y2 + offset))
            # Apply bias correction
            cutout.data['wnd100m'] = cutout.data['wnd100m'] * ERA5_wnd100m_bias['wnd100m']
        elif technology == 'solar':
            ERA5_ghi_bias_path = os.path.join(weather_data_path, 'bias_correction_factors', 'ERA5_ghi_bias.nc')
            ERA5_ghi_bias = xr.open_dataset(ERA5_ghi_bias_path).sel(x=slice(x1 - offset, x2 + offset), y=slice(y1 - offset, y2 + offset))
            # Apply bias correction
            cutout.data['influx_direct'] = cutout.data['influx_direct'] * ERA5_ghi_bias['ghi']
            cutout.data['influx_diffuse'] = cutout.data['influx_diffuse'] * ERA5_ghi_bias['ghi']

    for p in potential_list:
        print(f"Processing potential: {p}")

        # Create excluder
        excluder = atlite.ExclusionContainer(crs=local_crs_obj, res=res)

        # Load the potential
        if input_area == 'resource_grades':
            potentialPath = os.path.join(data_path, 'suitability', f"{p}_{local_crs_tag}.tif")
            excluder.add_raster(potentialPath, codes=1, invert=True)
        elif input_area == 'available_land':
            potentialPath = os.path.join(data_path, 'available_land', f"{region_name}_{technology}_{scenario}_available_land_{local_crs_tag}.tif")
            excluder.add_raster(potentialPath, codes=1, invert=True)
        elif input_area == 'study_region':
            potentialPath = os.path.join(data_path, f"{region_name}_{local_crs_tag}.geojson")
            excluder.add_geometry(potentialPath, invert=True)

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
        #fig, ax = plt.subplots()
        #A.plot(ax=ax, cmap="Greens")
        #region.plot(ax=ax, edgecolor="k", color="None")
        #cutout.grid.plot(ax=ax, color="None", edgecolor="grey")

        capacity_matrix = A.stack(spatial=["y", "x"])
        
        # Simulate the technology profiles based on the configuration
        match technology:
            case "solar":
                technology_path = os.path.join(dirname, 'configs', 'technologies', tech_config["panel"])

                ds_tech = cutout.pv(
                    matrix=capacity_matrix,
                    panel=Path(technology_path),
                    orientation="latitude_optimal",
                    index=region.index,
                    per_unit=True
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

            case "solartracking":
                technology_path = os.path.join(dirname, 'configs', 'technologies', tech_config["panel"])

                ds_tech = cutout.pv(
                    matrix=capacity_matrix,
                    panel=Path(technology_path),
                    orientation="latitude_optimal",
                    index=region.index,
                    tracking="horizontal",
                    per_unit=True
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

            case "onshorewind":
                technology_path = os.path.join(dirname, 'configs', 'technologies', tech_config["turbine"])
                
                ds_tech = cutout.wind(
                    matrix=capacity_matrix,
                    turbine=Path(technology_path),
                    index=region.index,
                    per_unit=True
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

            case "offshorewind":
                technology_path = os.path.join(dirname, 'configs', 'technologies', tech_config["turbine"])

                ds_tech = cutout.wind(
                    matrix=capacity_matrix,
                    turbine=Path(technology_path),
                    index=region.index,
                    per_unit=True
                )
                # Apply derate
                ds_tech = ds_tech * tech_config["tech_derate"]

        # Add resource grade to the dataframe
        df_tech = ds_tech.to_pandas()
        df_pot.loc[df_tech.index, p] = df_tech.iloc[:, 0]

# Check for missing values and give warning if any are found
if df_pot.isnull().values.any():
    print("Warning: Missing values found in the resource grades dataframe.")

# Save the resource grade time series to a CSV file
output_file=os.path.join(output_path, f"{region_name}_{technology}_{scenario}_profile_{weather_year}.csv")
df_pot.to_csv(output_file)