import logging
import os

import geopandas as gpd

from datetime import datetime, timedelta
import fiona
import io
import requests
import zipfile

from lava.utils.study_area import StudyArea
from lava.utils.vector import geopandas_clip_reproject


def prepare_protected_areas(
    study_area: StudyArea, source, country_code, local_filename=None
):
    """Clip protected areas (source 'WDPA' or 'file') to the study region.

    WDPA is country specific, so protected areas for a custom polygon spanning
    multiple countries cannot be obtained.
    """
    print("\nprocessing protected areas")
    protected_areas_folder = os.path.join(
        study_area.raw_spatial_data_folder, "protected_areas"
    )
    protected_areas_filePath = os.path.join(
        study_area.output_dir,
        f"protected_areas_{source}_{study_area.name}_{study_area.global_crs_tag}.gpkg",
    )
    if not os.path.exists(
        protected_areas_filePath
    ):  # process data if file not exists in output folder
        if source == "WDPA":
            logging.info("using WDPA")
            raw_WPDA_file = os.path.join(
                protected_areas_folder,
                f"WDPA_{country_code}",
                f"{country_code}_WDPA.gpkg",
            )
            if not os.path.exists(raw_WPDA_file):
                try:
                    WDPA_country_folder = os.path.join(
                        protected_areas_folder, f"WDPA_{country_code}"
                    )
                    os.makedirs(WDPA_country_folder, exist_ok=True)

                    wdpa_url, source_month = retrieve_wdpa_url(country_code)
                    download_unpack_zip(wdpa_url, WDPA_country_folder)
                    gdb_folder = find_folder(
                        WDPA_country_folder, file_ending=".gdb"
                    )  # gdb means geodatabase
                    convert_gdb_to_gpkg(
                        gdb_folder, WDPA_country_folder, f"{country_code}_WDPA.gpkg"
                    )
                    print(f"WDPA downloaded for {source_month}")

                except Exception as e:
                    logging.error(f"WDPA download and conversion failed: {e}")
            else:
                logging.info(
                    "folder with protected areas of country of study region already exists"
                )
                WDPA_country_folder = os.path.join(
                    protected_areas_folder, f"WDPA_{country_code}"
                )

            raw_protected_areas_filepath = os.path.join(
                WDPA_country_folder, f"{country_code}_WDPA.gpkg"
            )

        elif source == "file":
            logging.info("using local file for protected areas")
            raw_protected_areas_filepath = os.path.join(
                protected_areas_folder, local_filename
            )

        # clip to study region (WDPA or local file)
        try:
            protected_areas_file = gpd.read_file(raw_protected_areas_filepath)
            protected_areas_file = geopandas_clip_reproject(
                protected_areas_file, study_area.boundary_4326, study_area.global_crs
            )
            if not protected_areas_file.empty:
                protected_areas_file.to_file(
                    protected_areas_filePath, driver="GPKG", encoding="utf-8"
                )
            else:
                logging.info("No protected areas found in the region. File not saved.")
        except Exception as e:
            logging.error(f"processing protected areas failed: {e}")

    else:
        print("Protected areas file already exists for region.")


def retrieve_wdpa_url(country_code):
    """
    Attempts to locate the latest available WDPA zip file by checking
    the current month, previous month, and next month. Returns the
    first accessible URL or raises an error if none exist.
    """

    def check_file_exists(url):
        response = requests.head(url)
        return response.status_code == 200

    # month formats: e.g., Jan2025
    month_candidates = [
        datetime.now().strftime("%b%Y"),
        (datetime.now() - timedelta(days=30)).strftime("%b%Y"),
        (datetime.now() + timedelta(days=30)).strftime("%b%Y"),
    ]

    for bYYYY in month_candidates:
        url = f"https://d1gam3xoknrgr2.cloudfront.net/current/WDPA_WDOECM_{bYYYY}_Public_{country_code}.zip"
        if check_file_exists(url):
            logging.info(f"Found WDPA file for {bYYYY} from WDPA for {country_code}")
            return url, bYYYY

    raise FileNotFoundError(
        f"No WDPA files found for {month_candidates} using country code: {country_code}"
    )


def download_unpack_zip(url, output_dir):
    response = requests.get(url)
    # Check if the download was successful
    if response.status_code == 200:
        # Open the downloaded content as a zipfile
        logging.info("Download complete, extracting files...")
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(path=output_dir)
    else:
        logging.error(f"WDPA file download failed: {response.status_code}")


def find_folder(directory, file_ending=None, string_in_name=None):
    for root, dirs, files in os.walk(directory):
        for folder in dirs:
            if file_ending is not None:
                if folder.endswith(file_ending):
                    return os.path.join(root, folder)
            if string_in_name is not None:
                if string_in_name in folder:
                    return os.path.join(root, folder)
    return None


def convert_gdb_to_gpkg(gdb_folder, output_dir, filename):
    layers = fiona.listlayers(gdb_folder)  # list all layers
    poly_layer = next(
        (layer for layer in layers if "poly" in layer.lower()), None
    )  # find the layer containing the word "poly" for the polygon layer
    if poly_layer:
        gdf = gpd.read_file(gdb_folder, layer=poly_layer)
        gdf.to_file(os.path.join(output_dir, filename), driver="GPKG", encoding="utf-8")
        logging.info(f"WDPA saved as gpkg to {output_dir}")
    else:
        logging.warning(
            "No layer containing 'poly' in its name was found. No WDPA saved."
        )
