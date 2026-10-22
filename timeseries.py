# based on: https://github.com/GreenDealUkraina/res-profiles


import atlite
import numpy as np
import xarray as xr
import pandas as pd
import geopandas as gpd
import os
import yaml
import logging
import argparse
from atlite.gis import ExclusionContainer
import rasterio
from pathlib import Path
from utils.data_preprocessing import clean_region_name


logging.basicConfig(level=logging.INFO)

dirname = os.getcwd()


# --- Helper function to load custom or atlite turbine/panel files ---
def load_turbine_or_panel(name, dirname):
    """
    Load turbine or panel from custom configs/advanced_settings folder first,
    then fall back to atlite's internal files.

    Args:
        name: Name of the turbine/panel (e.g., "HW_farm", "Vestas_V112_3MW", "CSi")
        dirname: Working directory path

    Returns:
        Path to custom yaml file, or original name string if using atlite internal files
    """
    if name is None:
        return None

    # Check if custom file exists in advanced_settings folder
    custom_path = os.path.join(dirname, "configs/advanced_settings", f"{name}.yaml")
    if os.path.exists(custom_path):
        logging.info(f"    Loading custom turbine/panel from: {custom_path}")
        return Path(custom_path)

    # Fall back to atlite's internal files (pass name as string)
    logging.info(f"    Using atlite internal turbine/panel: {name}")
    return name


# --- Load timeseries settings from config ---
with open(os.path.join(dirname, "configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

# CLI args (fall back to config.yaml defaults)
parser = argparse.ArgumentParser()
parser.add_argument("--region", default=config["study_region_name"])
parser.add_argument("--weather_year", default=config["weather_year"], type=int)
parser.add_argument(
    "--scenario",
    default=config.get("scenario"),
    help="Exclusion scenario (defaults to the 'scenario' value in config.yaml).",
)
parser.add_argument(
    "--technology",
    default=config.get("technology"),
    help=(
        "Workflow technology whose available-land raster and timeseries resource "
        "should be used (for example onshorewind or solar). Defaults to the "
        "'technology' value in config.yaml."
    ),
)
args = parser.parse_args()

if args.scenario is None:
    parser.error("Provide --scenario or set 'scenario' in config.yaml.")
if args.technology is None:
    parser.error("Provide --technology or set 'technology' in config.yaml.")

study_region_name = clean_region_name(args.region)
year = int(args.weather_year)
scenario = args.scenario
technology_exclusion = args.technology

# Workflow/exclusion technology names are not always the same as the keys used
# by atlite in the timeseries section of config.yaml.
technology_aliases = {
    "onshorewind": "onwind",
    "offshorewind": "offwind",
}
profile_technology = technology_aliases.get(
    technology_exclusion, technology_exclusion
)

logging.info(
    f"region={study_region_name}, year={year}, scenario={scenario}, technology={technology_exclusion}"
)

cutout_name = config["cutout_name"].format(year=year)
cutout_dir = os.path.join(dirname, config["cutout_dir"])
cutout_path = os.path.join(cutout_dir, f"{cutout_name}.nc")
drop_leap_day = config["drop_leap_day"]
test_mode = config["test_mode"]
shapes_path = os.path.join(
    dirname, config.get("shapes_path").format(study_region_name=study_region_name)
)
output_dir = os.path.join(dirname, "data", study_region_name, "0_profiles")
os.makedirs(output_dir, exist_ok=True)
show_progress = config["show_progress"]
technologies = config["technologies"]
if profile_technology not in technologies:
    configured = sorted(key for key in technologies if key != "enable")
    raise ValueError(
        f"Technology '{technology_exclusion}' maps to '{profile_technology}', "
        f"which is not defined in config.yaml. Available definitions: {configured}"
    )
enabled_techs = [profile_technology]

# Resolve available_land raster path with placeholders
available_land_raster_template = config["available_land"]["raster"]
available_land_raster = os.path.join(
    dirname,
    available_land_raster_template.format(
        study_region_name=study_region_name,
        technology=technology_exclusion,
        scenario=scenario,
    ),
)

logging.info(f"  Timeseries technology to process: {profile_technology}")

# --- Load region shapes ---
logging.info(f"Loading shapes from {shapes_path}")
shapes = gpd.read_file(shapes_path)
name_col = config.get("shapes_name_column", "name")
if name_col in shapes.columns:
    shapes = shapes.set_index(name_col).rename_axis("region")
elif len(shapes) == 1:
    # Spatial preparation writes one feature per study region. Custom regions
    # may use their own attribute schema, so their filename/CLI region is the
    # reliable profile label.
    shapes.index = pd.Index([study_region_name], name="region")
else:
    available_columns = [column for column in shapes.columns if column != "geometry"]
    raise KeyError(
        f"Shape name column '{name_col}' is missing from {shapes_path}. "
        f"Available columns: {available_columns}"
    )
regions = shapes.geometry
logging.info(f"  {len(regions)} regions loaded")

# --- Load ERA5 cutout from local folder ---
if not os.path.exists(cutout_path):
    raise FileNotFoundError(f"Cutout file not found: {cutout_path}")
logging.info(f"  Loading cutout: {cutout_path}")
cutout = atlite.Cutout(cutout_path)

# Use the actual timestamps in the input cutout.  A cutout may cover a full
# year, a season, or arbitrary selected periods; it is the source of truth for
# the profile timeline.
sns = pd.DatetimeIndex(cutout.data.indexes["time"])
if sns.empty:
    raise ValueError(
        f"The cutout has no timestamps: {cutout_path}."
    )
if drop_leap_day:
    sns = sns[~((sns.month == 2) & (sns.day == 29))]
if test_mode:
    sns = sns[:168]  # first 168 available hours
if sns.empty:
    raise ValueError("No timestamps remain after applying time filters.")
logging.info("  Using %d cutout timestamps from %s to %s", len(sns), sns.min(), sns.max())
cutout.data = cutout.data.sel(time=sns)


if config["available_land"]["enable"]:
    # --- Raster: how much of each grid cell is eligible, i.e. availbale land
    with rasterio.open(available_land_raster) as src:
        crs = src.crs
        res = src.res[0]

    excluder = ExclusionContainer(
        crs=crs,
        res=res,
    )  # crs and resolution
    excluder.add_raster(available_land_raster, codes=1, invert=True, crs=crs)

    indicator = cutout.availabilitymatrix(regions, excluder)

else:
    # --- Compute indicator matrix: which grid cells belong to which region ---

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
for tech_name in enabled_techs:
    tech_params = technologies[tech_name]
    logging.info(f"  Technology: {tech_name}")

    resource = tech_params["resource"].copy()
    correction_factor = tech_params.get("correction_factor", 1.0)
    clip_threshold = tech_params.get("clip_p_max_pu", None)

    method = resource.pop("method")
    func = getattr(cutout, method)
    resource["show_progress"] = show_progress

    # Load custom or atlite turbine/panel files
    if "turbine" in resource:
        resource["turbine"] = load_turbine_or_panel(resource["turbine"], dirname)
    if "panel" in resource:
        resource["panel"] = load_turbine_or_panel(resource["panel"], dirname)

    ##### Custom turbine for windspeeds technology
    if tech_name == "windspeeds":
        wind_speed = np.arange(0, 100, 1)
        max_wind_speed = float(cutout.data["wnd100m"].max().values)
        helper_turbine = {
            "V": wind_speed,
            "POW": wind_speed,
            "hub_height": 100,
            "P": max_wind_speed,
        }
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

    out_file = os.path.join(
        output_dir,
        f"{study_region_name}_{technology_exclusion}_{scenario}_profile_{year}.csv",
    )
    df.to_csv(out_file)

    logging.info(
        f"    Saved {os.path.basename(out_file)}  "
        f"({len(df)} timesteps × {len(df.columns)} regions)"
    )


logging.info("Done — all profiles generated.")

# --- Save technologies dictionary, shapes filename, and cutout name to a text file ---
tech_file = os.path.join(
    output_dir,
    f"technologies_{technology_exclusion}_{scenario}_{year}.txt",
)
with open(tech_file, "w", encoding="utf-8") as f:
    f.write(f"shapes_file: {os.path.basename(shapes_path)}\n")
    f.write(f"cutout_file: {os.path.basename(cutout_path)}\n\n")
    f.write("technologies:\n")
    import yaml

    yaml.dump(
        {profile_technology: technologies[profile_technology]},
        f,
        allow_unicode=True,
        default_flow_style=False,
    )
