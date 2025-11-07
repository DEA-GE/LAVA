import xarray as xr
import os
import rioxarray as rxr
import matplotlib.pyplot as plt
import geopandas as gpd
import yaml
import glob


def raster2grid(raster_path, target_grid, var_name, method):
    """
    Resample a raster file to match the grid of a target xarray DataArray or Dataset.

    Parameters:
    -----------
    raster_path : str
        Path to the input raster file (e.g., GeoTIFF).
    target_grid : xarray.DataArray or xarray.Dataset
        The target grid whose resolution, bounds, and CRS will be matched.
    method : str
        Resampling method: 'nearest', 'bilinear', or 'cubic'.

    Returns:
    --------
    resampled : xarray.DataArray
        The resampled raster aligned to the target grid.
    """
    # Open the raster with rioxarray
    raster = rxr.open_rasterio(raster_path, masked=True).squeeze()  # remove band dimension if only one

    raster.name = var_name  # Rename the variable to match the target grid

    # Ensure CRS matches
    raster = raster.rio.reproject_match(target_grid)

    # Align to target resolution and shape using xarray's interp_like
    resampled = raster.interp_like(target_grid, method=method)

    return resampled

def plot_xarray(da, vector_path, vmin, vmax, title, save_path):
    """
    Plot xarray DataArray with a vector overlay using matplotlib only.
    
    Parameters:
    - da: xarray.DataArray (2D) with coordinates (lat, lon) or (y, x)
    - vector_path: path to a vector file (shapefile, GeoJSON)
    - title: title for the plot
    - cmap: matplotlib colormap
    - figsize: figure size
    """

    cmap="viridis"

    gdf = gpd.read_file(vector_path)

    # Create the plot
    fig, ax = plt.subplots(figsize=(10, 6))
    
    im = da.plot(ax=ax, cmap=cmap, vmin=vmin, vmax=vmax, cbar_kwargs={'label': da.name}, alpha=0.8)

    gdf.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=1)

    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.show()

# Function to correct bias in a target dataset using a reference dataset
def ds_bias_correction(ds_ref, ds_target, mean_dims):
    ds_s = ds_ref / ds_target.mean(dim=mean_dims)
    return ds_s

#------------------------------------------- Initialization -------------------------------------------
dirname = os.getcwd() 
with open(os.path.join("configs/config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader) 

country_code = config['country_code']
country_name_solar_atlas = config['country_name_solar_atlas']

# Load the weather data (all years)
if config.get('weather_external_data_path'):
    weather_data_path = os.path.abspath(config["weather_external_data_path"])
else:
    weather_data_path = os.path.join(dirname, 'Raw_Spatial_Data', 'Weather_data')
weather_data_files = glob.glob(os.path.join(weather_data_path, f'*.nc'))


GWAraster_path = os.path.join(dirname, 'Raw_Spatial_Data', 'global_solar_wind_atlas', f'{country_code}_wind_speed_100.tif')
GSAraster_path = os.path.join(dirname, 'Raw_Spatial_Data', 'global_solar_wind_atlas', f'{country_name_solar_atlas}_GISdata_LTAy_YearlyMonthlyTotals_GlobalSolarAtlas-v2_GEOTIFF', 'GHI.tif')

output_path = os.path.join(weather_data_path, 'bias_correction_factors')
os.makedirs(output_path, exist_ok=True)

# ---------------------- ERA5 ----------------------
# Load ERA5 data (all files)
era5_ds = xr.open_mfdataset(weather_data_files)

if config['weather_bias_correction'].get('onshorewind') or config['weather_bias_correction'].get('offshorewind'):
    print("Computing wind bias correction based on Global Wind Atlas data...")
    print("Using ERA5 files: ", weather_data_files)
    print("Max and min bias correction factors will be limited to: ", config['weather_bias_range'])

    # Resample the raster to ERA5 grid and convert to xarray grid
    GWA_ds = raster2grid(GWAraster_path, era5_ds['wnd100m'].rio.write_crs("EPSG:4326"), 'wnd100m', 'linear')

    # Find ERA5 bias relative to GWA reference
    ERA5_wnd100m_bias = ds_bias_correction(GWA_ds, era5_ds['wnd100m'], mean_dims=['time'])

    # Fill NaN values with 1 (no bias where no reference data is available)
    ERA5_wnd100m_bias = ERA5_wnd100m_bias.fillna(1)

    # Limit bias correction factors to reasonable ranges
    min_val, max_val = config['weather_bias_range']
    ERA5_wnd100m_bias = ERA5_wnd100m_bias.clip(min=min_val, max=max_val)

    # Export bias
    ERA5_wnd100m_bias.to_netcdf(output_path + "/ERA5_wnd100m_bias.nc")

    # Export rasters
    ERA5_wnd100m_bias.rio.to_raster(output_path + "/ERA5_wnd100m_bias.tif")

if config['weather_bias_correction'].get('solar'):
    print("Computing solar bias correction based on Global Solar Atlas data...")
    print("Using ERA5 files: ", weather_data_files)
    print("Max and min bias correction factors will be limited to: ", config['weather_bias_range'])
    # Calclulate GHI (kWh/m2/hour)
    era5_ds['ghi'] = (era5_ds["influx_direct"] + era5_ds["influx_diffuse"]) / 1000

    # Resample the raster to ERA5 grid and convert to xarray grid (kWh/m2/year)
    GSA_ds = raster2grid(GSAraster_path, era5_ds['ghi'].rio.write_crs("EPSG:4326"), 'ghi', 'linear')

    # Find ERA5 bias relative to GSA reference
    ERA5_ghi_bias = ds_bias_correction(GSA_ds / 8760, era5_ds['ghi'], mean_dims=['time'])

    # Fill NaN values with 1 (no bias where no reference data is available)
    ERA5_ghi_bias = ERA5_ghi_bias.fillna(1)

    # Limit bias correction factors to reasonable ranges
    min_val, max_val = config['weather_bias_range']
    ERA5_ghi_bias = ERA5_ghi_bias.clip(min=min_val, max=max_val)

    # Export bias
    ERA5_ghi_bias.to_netcdf(output_path + "/ERA5_ghi_bias.nc")
    
    # Export rasters
    ERA5_ghi_bias.rio.to_raster(output_path + "/ERA5_ghi_bias.tif")