# based on: https://github.com/GreenDealUkraina/res-profiles 


import atlite
import numpy as np
import xarray as xr
import pandas as pd
import geopandas as gpd
import os
import yaml
import logging
from utils.data_preprocessing import *
from atlite.gis import ExclusionContainer


logging.basicConfig(level=logging.INFO)

dirname = os.getcwd() 

# --- Load timeseries settings from config ---
with open(os.path.join(dirname, "configs/config_template.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

# Set variables from config (prepend dirname to all constructed paths)
year = config["weather_year"]
cutout_name = config["cutout_name"].format(year=year)
cutout_dir = os.path.join(dirname, config["cutout_dir"])
cutout_path = os.path.join(cutout_dir, f"{cutout_name}.nc")
drop_leap_day = config["drop_leap_day"]
test_mode = config["test_mode"]
shapes_path = os.path.join(dirname, config["shapes_path"])
output_dir = os.path.join(dirname, config["output_dir"])
show_progress = config["show_progress"]
technologies = config["technologies"]
os.makedirs(output_dir, exist_ok=True)

# --- Load region shapes ---
logging.info(f"Loading shapes from {shapes_path}")
shapes = gpd.read_file(shapes_path)
name_col = config.get("shapes_name_column", "name")
shapes = shapes.set_index(name_col).rename_axis("region")
regions = shapes.geometry
logging.info(f"  {len(regions)} regions loaded")

# --- Build time snapshots ---
snapshots_config = {
    "start": f"{year}-01-01",
    "end": f"{year + 1}-01-01",
    "inclusive": "left",
}
sns = pd.date_range(
    start=snapshots_config["start"],
    end=snapshots_config["end"],
    freq="h",
    inclusive=snapshots_config["inclusive"]
)
if drop_leap_day:
    sns = sns[~((sns.month == 2) & (sns.day == 29))]
if test_mode:
    sns = sns[:168]  # first week only
logging.info(f"  Time range: {sns[0]} to {sns[-1]} ({len(sns)} timesteps)")

# --- Load ERA5 cutout from local folder ---
if not os.path.exists(cutout_path):
    raise FileNotFoundError(f"Cutout file not found: {cutout_path}")
logging.info(f"  Loading cutout: {cutout_path}")
cutout = atlite.Cutout(cutout_path)
cutout.data = cutout.data.sel(time=sns)
logging.info(
    f"  Cutout grid: {cutout.shape} (y × x), "
    f"x=[{float(cutout.coords['x'].min()):.1f}, {float(cutout.coords['x'].max()):.1f}], "
    f"y=[{float(cutout.coords['y'].min()):.1f}, {float(cutout.coords['y'].max()):.1f}]"
)

# --- Compute indicator matrix: which grid cells belong to which region ---
logging.info("  Computing region-grid indicator matrix...")

indicator = cutout.availabilitymatrix(
    regions, ExclusionContainer(), disable_progressbar=not show_progress
)
indicator = np.ceil(indicator)  # binary 0/1

# Uniform layout: equal weight per grid cell
layout = xr.DataArray(
    np.ones(cutout.shape),
    [cutout.coords["y"], cutout.coords["x"]],
)

# Stack spatial dimensions for matrix multiplication
matrix = indicator.stack(spatial=["y", "x"])

# --- Generate and save timeseries profiles for each technology ---
for tech_name, tech_params in technologies.items():
    logging.info(f"  Technology: {tech_name}")
    import time
    t0 = time.time()

    resource = tech_params["resource"].copy()
    correction_factor = tech_params.get("correction_factor", 1.0)
    clip_threshold = tech_params.get("clip_p_max_pu", None)

    method = resource.pop("method")
    func = getattr(cutout, method)
    resource["show_progress"] = show_progress

    ##### Custom turbine for windspeeds technology
    if tech_name == "windspeeds":
        wind_speed = np.arange(0, 100, 1)
        max_wind_speed = float(cutout.data["wnd100m"].max().values)
        helper_turbine = {'V': wind_speed, 'POW': wind_speed, 'hub_height': 100, 'P': max_wind_speed}
        resource["turbine"] = helper_turbine
    #####

    profile = func(
        matrix=matrix,
        layout=layout,
        index=matrix.indexes["region"],
        per_unit=True,
        return_capacity=False,
        **resource,
    )


    if correction_factor != 1.0:
        profile = correction_factor * profile
    if clip_threshold is not None:
        profile = profile.where(profile >= clip_threshold, 0)

    df = profile.to_pandas()

    #### For windspeeds technology, multiply by max_wind_speed before exporting
    if tech_name == "windspeeds":
        df = df * max_wind_speed
    ####

    out_file = os.path.join(output_dir, f"profile_{tech_name}_{year}.csv")
    df.to_csv(out_file)

    duration = time.time() - t0
    logging.info(
        f"    Saved {os.path.basename(out_file)}  "
        f"({len(df)} timesteps × {len(df.columns)} regions, "
        f"{duration:.1f}s)"
    )

logging.info("Done — all profiles generated.")








