import logging
import os

from lava.utils.study_area import StudyArea
from lava.utils.raster import clip_raster


def prepare_buildings(study_area: StudyArea, buildings_filename):
    """Clip the local buildings raster (Mollweide) to the study region."""
    print("\nprocessing buildings raster")
    try:
        buildings_filePath = os.path.join(
            study_area.output_dir,
            f"buildings_{study_area.name}_ESRI54009.tif",
        )
        if not os.path.exists(
            buildings_filePath
        ):  # process data if file not exists in output folder
            buildings_raw_filePath = os.path.join(
                study_area.raw_spatial_data_folder,
                "buildings",
                buildings_filename,
            )
            clip_raster(
                buildings_raw_filePath,
                study_area.name,
                study_area.boundary_mollweide,
                study_area.output_dir,
                "buildings",
                dtype="uint8",
            )
    except Exception as e:
        logging.error(f"buildings data failed: {e}")
