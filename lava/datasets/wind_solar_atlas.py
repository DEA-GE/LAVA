import logging
import os

import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping

import io
import requests
import zipfile

from lava.utils.study_area import StudyArea


def _clip_to_4326(raster_path, study_area: StudyArea, data_name, scale_factor=1):
    """Clip a raster to the study region and save it as <data_name>_<region>_EPSG4326.tif."""
    with rasterio.open(raster_path) as src:
        out_image, out_transform = mask(
            src,
            study_area.boundary_4326.geometry.apply(mapping),
            crop=True,
            all_touched=True,
        )
        if scale_factor != 1:
            out_image = (out_image.astype(np.float32) * float(scale_factor)).astype(
                np.float32, copy=False
            )
        out_meta = src.meta.copy()
        out_meta.update(
            {
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "dtype": rasterio.float32,
            }
        )
        output_path = os.path.join(
            study_area.output_dir, f"{data_name}_{study_area.name}_EPSG4326.tif"
        )
        with rasterio.open(output_path, "w", **out_meta) as dest:
            dest.write(out_image.astype(np.float32, copy=False))
    return output_path


def prepare_wind_atlas(study_area: StudyArea, country_code):
    """Download (if needed) and clip the Global Wind Atlas wind speed raster."""
    print("\nprocessing global wind atlas")
    raw_spatial_data_folder = study_area.raw_spatial_data_folder
    wind_raster_filePath = os.path.join(
        raw_spatial_data_folder,
        "global_solar_wind_atlas",
        f"{country_code}_wind_speed_100.tif",
    )
    if not os.path.exists(wind_raster_filePath):
        try:
            download_global_wind_atlas(
                country_code=country_code, height=100, data_path=raw_spatial_data_folder
            )  # global wind atlas apparently uses 3 letter ISO code
        except Exception as e:
            logging.error(f"global wind atlas download failed: {e}")

    else:
        print("Global wind atlas data already downloaded")

    _clip_to_4326(wind_raster_filePath, study_area, "wind")


def prepare_solar_atlas(study_area: StudyArea):
    """Download (if needed) and clip the Global Solar Atlas PVOUT raster (scaled to yearly values)."""
    print("\nprocessing global solar atlas")
    raw_spatial_data_folder = study_area.raw_spatial_data_folder
    solar_atlas_folder_path = os.path.join(
        raw_spatial_data_folder, "global_solar_wind_atlas", "World_solar_atlas"
    )

    solar_raster_filePath = None
    for root, dirs, files in os.walk(solar_atlas_folder_path):
        if "PVOUT.tif" in files:
            solar_raster_filePath = os.path.join(root, "PVOUT.tif")
            break  # Stop searching once found

    if solar_raster_filePath is None:
        download_global_solar_atlas(data_path=raw_spatial_data_folder)
        for root, dirs, files in os.walk(solar_atlas_folder_path):
            if "PVOUT.tif" in files:
                solar_raster_filePath = os.path.join(root, "PVOUT.tif")
                break
    else:
        print("Global solar atlas data already downloaded")

    if solar_raster_filePath is None:
        logging.error(
            "PVOUT.tif was not found in the extracted world solar atlas folder."
        )
    else:
        _clip_to_4326(solar_raster_filePath, study_area, "solar", scale_factor=365)


def download_global_wind_atlas(country_code: str, height: int, data_path: str = None):
    """
    Downloads wind speed data from the Global Wind Atlas API for a given country and height.

    Parameters:
        country_code (str): ISO 3166-1 alpha-3 country code (e.g., "AFG" for Afghanistan).
        height (int): Wind height in meters (e.g., 100).
        save_path (str, optional): Custom file name or path to save the file. If None, uses default naming.

    Returns:
        bool: True if successful, False otherwise.
    """
    url = f"https://globalwindatlas.info/api/gis/country/{country_code}/wind-speed/{height}"

    try:
        print(f"Downloading wind data for '{country_code}' from: {url}")
        response = requests.get(url)
        if response.ok:
            filePath = os.path.join(
                data_path,
                "global_solar_wind_atlas",
                f"{country_code}_wind_speed_{height}.tif",
            )
            with open(filePath, "wb") as f:
                f.write(response.content)
            # print(f"Downloaded to: {filePath}")
            return True
        else:
            print(f"Failed to download. HTTP status: {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"global wind atlas download failed: {e}")
        return False


def download_global_solar_atlas(data_path: str):
    """
    Downloads and extracts the world PVOUT GeoTIFF ZIP file from Global Solar Atlas.

    Parameters:
        data_path (str): Base raw spatial data directory.

    Returns:
        str | None: Extraction folder path if successful, otherwise None.
    """

    url = "https://api.globalsolaratlas.info/download/World/World_PVOUT_GISdata_LTAy_AvgDailyTotals_GlobalSolarAtlas-v2_GEOTIFF.zip"
    timeout = 900  # world file is large
    print(f"Downloading world solar data from: {url}")

    # Define the full extraction path
    extract_folder = os.path.join(
        data_path, "global_solar_wind_atlas", "World_solar_atlas"
    )
    os.makedirs(extract_folder, exist_ok=True)

    # download
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            print("Download successful. Extracting files...")

            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                zip_ref.extractall(extract_folder)

            # print(f"Files extracted to '{extract_folder}'")

            # Assuming the zip contains a single folder (standard GSA structure)
            folder_name = zip_ref.namelist()[0].split("/")[0]  # top-level folder name
            return folder_name
        else:
            logging.error(
                f"Failed to download world solar atlas data. Status code: {response.status_code}"
            )
            return None

    except requests.Timeout:
        logging.warning(
            f"Download world solar atlas data timed out after {timeout} seconds."
        )
        return None
    except Exception as e:
        logging.error(f"solar atlas download failed: {e}")
        return None
