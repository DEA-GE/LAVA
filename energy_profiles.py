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


#-----------------------------------Snakemake input to be implemented-----------------------------------#
weather_year = 1990
# region
# pontential_path


#------------------------------------------- Load configuration
dirname = os.getcwd() 
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 


region_name = config['region_name'] #if country is studied, then use country name
region_name = clean_region_name(region_name)
technology=config["technology"]
scenario= config["scenario"]

data_path = os.path.join(dirname, 'data', config['region_folder_name'])

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
weather_data_path = os.path.join(config['weather_data_path'], f'China_mainland_{weather_year}_2.nc')


# Load region geometry
regionPath = os.path.join(data_path, f'{region_name}_{local_crs_tag}.geojson')
region = gpd.read_file(regionPath)


# Load potential (currently the available land, but should be changed to the areas from the suitability analysis)
min_pixels_connected = config['min_pixels_connected']
# TO DO: Change to different paths for solar and wind
potentialPath = os.path.join(
    data_path, 'available_land', 
    f"{region_name}_{technology}_{scenario}_available_land_{local_crs_tag}.tif"
)


# Load weather data cutout
x1, y1, x2, y2 = region.to_crs(global_crs_obj).total_bounds 
offset = 1 # Offset to ensure the cutout includes the entire region
cutout = atlite.Cutout(path=weather_data_path).sel(x=slice(x1 - offset, x2 + offset), y=slice(y1 - offset, y2 + offset))

#to be deleted only for testing purposes
technology="SolarPV"

#--------------------- Capacity matrix ---------------------

if technology in ["SolarPV", "SolarPVTracking", "OnshoreWind", "OffshoreWind"]:
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

if config['tech'] == "HeatDemand":
    population_path = "E:/CETO 2025 Spatial Analysis data/GIS/Population/China_population_2023.nc"
    pop_layout = xr.open_dataarray(population_path).sel(x=slice(x1 - offset, x2 + offset), y=slice(y1 - offset, y2 + offset))
    # set nan values to zero
    pop_layout = pop_layout.fillna(0)
    # Normalize population layout to the indicator matrix
    pop_layout = pop_layout / pop_layout.max()

    capacity_matrix = pop_layout.stack(spatial=("y", "x"))

# Simulate the technology profiles based on the configuration
match technology:
    case "SolarPV":
        ds_tech = cutout.pv(
            matrix=capacity_matrix,
            panel=config["solarpanel"],
            orientation="latitude_optimal",
            index=region.index,
            per_unit=True
        )
        # Apply derate
        ds_tech = ds_tech * config["tech_derate"]

    case "SolarPVTracking":
        ds_tech = cutout.pv(
            matrix=capacity_matrix,
            panel=config["solarpanel"],
            orientation="latitude_optimal",
            index=region.index,
            tracking="horizontal",
            per_unit=True
        )
        # Apply derate
        ds_tech = ds_tech * config["tech_derate"]

    case "OnshoreWind":
        ds_tech = cutout.wind(
            matrix=capacity_matrix,
            turbine=Path(config["windturbine_onshore"]),
            index=region.index,
            per_unit=True
        )
        # Apply derate
        ds_tech = ds_tech * config["tech_derate"]

    case "OffshoreWind":
        ds_tech = cutout.wind(
            matrix=capacity_matrix,
            turbine=config["windturbine_offshore"],
            index=region.index,
            per_unit=True
        )
        # Apply derate
        ds_tech = ds_tech * config["tech_derate"]

    case "Hydro":
        plants, basins = hydro()
        ds_tech = cutout.hydro(
            plants=plants,
            hydrobasins=basins
        )
        # Apply derate
        ds_tech = ds_tech * config["tech_derate"]

    case "HeatDemand":
        ds_tech = cutout.heat_demand(
            matrix=capacity_matrix,
            threshold=config["heat_demand_threshold"],
            a=1,
            constant=config["heat_demand_constant"]
        )

    case _:
        raise ValueError(f"Unknown technology: {technology}")

# Convert to DataArray to dataframe
df_tech = ds_tech.to_pandas()

if technology == "HeatDemand":
    # Set demand to zero outside of heating season
    start_day = config["heat_demand_start_day"]
    end_day = config["heat_demand_end_day"]
    df_tech.loc[f"{weather_year}-{start_day}":f"{weather_year}-{end_day}"] = 0


# Convert to DataFrame for export
#output_path = os.path.join(data_path, "energy_profiles")
#os.makedirs(output_path, exist_ok=True)
#output_filename=os.path.join(output_path,f"{technology}_profile_{region_name}.csv")
output_filename=f"{technology}_profile_{region_name}.csv"
ds_tech = ds_tech.to_pandas().to_csv(output_filename)









"""










# --------------------- Misc --------------------- #
ds_tech.to_pandas().plot(ylabel="Power [GW]", ls="--", figsize=(10, 4))
wnd.to_pandas().plot(ylabel="Power [GW]", ls="--", figsize=(10, 4))
# Apply derate
ds_tech = ds_tech * m.derate

ds_tech.name = 'Nei-Mongol'

from atlite.windturbines import load_turbine, turbineconfig

def hydro():
    plants = gpd.read_file("E:/CETO 2025 Spatial Analysis data/GIS/Hydro/Hydro_plants.gpkg")
    basins = gpd.read_file("E:/CETO 2025 Spatial Analysis data/GIS/Hydro/Hydrobasin_level4.gpkg")

    return plants, basins

### ---------- Produce profiles ----------- ###



capacity_matrix(m, cutout, excluder)


    EPSG = "EPSG:32650"
    

    # Balmorel time sets and geography
    m.region_file = "E:/CETO 2025 Spatial Analysis data/GIS/Admin boundaries/China_provinces.gpkg"
    m.region_name = 'East-InnerMongolia'
    m.region = gpd.read_file(m.region_file)
    m.region = m.region[m.region['name'] == m.region_name].geometry.to_crs(EPSG)


"""