import logging
import os

import requests

from lava.utils.study_area import StudyArea
from lava.utils.raster import clip_raster


def prepare_population_worldpop(study_area: StudyArea, country_code, year):
    """Download (if needed) and clip WorldPop population data."""
    print("\nprocessing population data")
    try:
        population_filePath = os.path.join(
            study_area.output_dir, f"population_{study_area.name}_EPSG4326.tif"
        )
        if not os.path.exists(
            population_filePath
        ):  # process data if file not exists in output folder
            population_raw_filePath = os.path.join(
                study_area.raw_spatial_data_folder,
                "population",
                f"population_{country_code}_{year}.tif",
            )
            if not os.path.exists(population_raw_filePath):
                download_worldpop(
                    country_code=country_code,
                    year=year,
                    output_dir=os.path.join(
                        study_area.raw_spatial_data_folder, "population"
                    ),
                )
            clip_raster(
                population_raw_filePath,
                study_area.name,
                study_area.boundary_4326,
                study_area.output_dir,
                "population",
                dtype="float32",
            )
    except Exception as e:
        logging.error(f"population data failed: {e}")


def prepare_population_file(study_area: StudyArea, country_code, year):
    """Clip a local population raster."""
    print("\nprocessing local population data")
    try:
        population_filePath = os.path.join(
            study_area.output_dir, f"population_{study_area.name}_EPSG4326.tif"
        )
        if not os.path.exists(
            population_filePath
        ):  # process data if file not exists in output folder
            population_raw_filePath = os.path.join(
                study_area.raw_spatial_data_folder,
                "population",
                f"population_{country_code}_{year}.tif",
            )
            clip_raster(
                population_raw_filePath,
                study_area.name,
                study_area.boundary_4326,
                study_area.output_dir,
                "population",
                dtype="float32",
            )
    except Exception as e:
        logging.error(f"population data failed: {e}")


def download_worldpop(country_code: str, year: int, output_dir: str):
    """
    Downloads WorldPop population data for a given country and year.

    Parameters:
        country_code (str): ISO 3166-1 alpha-3 country code (e.g., "DEU", "KEN").
        year (int): Year of the population data (e.g., 2020).
        output_dir (str): Directory where the file will be saved.

    Returns:
        str: Path to the downloaded file if successful, None otherwise.
    """
    # Convert country code to lowercase for filename
    country_lower = country_code.lower()
    country_upper = country_code.upper()

    # Hardcoded defaults
    release = "2025A"
    version = "1"
    resolution = "100m"
    data_type = "constrained"

    # Construct the URL
    url = (
        f"https://data.worldpop.org/GIS/Population/Global_2015_2030/R{release}/"
        f"{year}/{country_upper}/v{version}/{resolution}/{data_type}/"
        f"{country_lower}_pop_{year}_CN_{resolution}_R{release}_v{version}.tif"
    )

    # Construct output filepath
    os.makedirs(output_dir, exist_ok=True)
    filename = f"population_{country_upper}_{year}.tif"
    output_path = os.path.join(output_dir, filename)

    try:
        response = requests.get(url, timeout=300)

        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
        else:
            logging.error(f"Failed to download. HTTP status: {response.status_code}")
            return None

    except requests.Timeout:
        logging.error(f"Download timed out after 300 seconds for '{country_code}'.")
        return None
    except Exception as e:
        logging.error(f"Error downloading WorldPop data: {e}")
        return None
