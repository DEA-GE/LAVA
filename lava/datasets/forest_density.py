import logging
import os

from lava.utils.study_area import StudyArea
from lava.utils.common import rel_path
from lava.utils.raster import clip_raster


def prepare_forest_density(study_area: StudyArea, forest_density_filename):
    """Clip the forest density raster (optional local file)."""
    print("\nprocessing forest density (raster)")
    raw_forest_density_path = os.path.join(
        study_area.raw_spatial_data_folder, "landcover", forest_density_filename
    )
    if not os.path.exists(raw_forest_density_path):
        logging.warning(
            f"Forest density raster not found: {rel_path(raw_forest_density_path)}"
        )
    else:
        try:
            clip_raster(
                raw_forest_density_path,
                study_area.name,
                study_area.boundary_4326,
                study_area.output_dir,
                "forest_density",
            )
        except Exception as e:
            logging.warning(f"Failed to clip/reproject forest density raster: {e}")
