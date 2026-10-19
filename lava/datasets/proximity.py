import os

import geopandas as gpd

from lava.utils.study_area import StudyArea
from lava.utils.common import rel_path
from lava.utils.proximity_calc import generate_distance_raster


def _prepare_proximity(study_area: StudyArea, source_filename, output_filename, label):
    osm_output_dir = os.path.join(study_area.output_dir, "OSM_Infrastructure")
    source_path = os.path.join(osm_output_dir, source_filename)
    if os.path.exists(source_path):
        source_gdf = gpd.read_file(source_path)
        if not source_gdf.empty:
            proximity_dir = os.path.join(study_area.output_dir, "proximity")
            os.makedirs(proximity_dir, exist_ok=True)
            proximity_out = os.path.join(proximity_dir, output_filename)
            if os.path.exists(proximity_out):
                print(
                    f"Proximity raster already exists at {rel_path(proximity_out)}. Skipping generation."
                )
            else:
                generate_distance_raster(
                    shapefile_path=source_path,
                    region_gdf=study_area.boundary_4326,
                    output_path=proximity_out,
                )
            return
    print(f"Proximity distance cannot be calculated as the {label} not provided.")


def prepare_substation_proximity(study_area: StudyArea):
    """Create proximity raster for substations if data exists."""
    print("\ncomputing proximity distance for substations")
    _prepare_proximity(
        study_area, "substations.gpkg", "substation_distance.tif", "substation is"
    )


def prepare_road_proximity(study_area: StudyArea):
    """Create proximity raster for roads if data exists."""
    print("\ncomputing proximity distance for roads")
    _prepare_proximity(study_area, "roads.gpkg", "road_distance.tif", "roads are")
