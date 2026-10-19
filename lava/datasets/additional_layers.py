import os

import geopandas as gpd

from lava.utils.study_area import StudyArea
from lava.utils.raster import clip_raster
from lava.utils.vector import geopandas_clip_reproject
from lava.utils.inclusion_layers import (
    prepare_inclusion_polygon_folder,
    prepare_inclusion_raster_folder,
)


def prepare_additional_exclusion_polygons(study_area: StudyArea, folder_name):
    """Clip and reproject additional exclusion polygons."""
    print("\nprocessing additional exclusion polygons")
    add_excl_polygons_dir = os.path.join(
        study_area.output_dir, "additional_exclusion_polygons"
    )
    os.makedirs(add_excl_polygons_dir, exist_ok=True)
    source_dir = os.path.join(
        study_area.raw_spatial_data_folder, "additional_exclusion_polygons", folder_name
    )
    counter = 1
    for filename in os.listdir(source_dir):
        filepath = os.path.join(source_dir, filename)
        if filename.endswith(".geojson") or filename.endswith(".gpkg"):
            gdf = gpd.read_file(filepath)
            gdf_clipped_reprojected = geopandas_clip_reproject(
                gdf, study_area.boundary_4326, study_area.global_crs
            )
            filename_base = os.path.splitext(filename)[0]
            if not gdf_clipped_reprojected.empty:
                gdf_clipped_reprojected.to_file(
                    os.path.join(
                        add_excl_polygons_dir,
                        f"{counter}_{filename_base}_{study_area.name}_{study_area.global_crs_tag}.gpkg",
                    ),
                    driver="GPKG",
                )
                counter = counter + 1


def prepare_additional_exclusion_rasters(study_area: StudyArea, folder_name):
    """Clip additional exclusion rasters."""
    print("\nprocessing additional exclusion rasters")
    add_excl_rasters_dir = os.path.join(
        study_area.output_dir, "additional_exclusion_rasters"
    )
    os.makedirs(add_excl_rasters_dir, exist_ok=True)
    source_dir = os.path.join(
        study_area.raw_spatial_data_folder, "additional_exclusion_rasters", folder_name
    )
    for filename in os.listdir(source_dir):
        filepath = os.path.join(source_dir, filename)
        if filename.endswith(".tif"):
            data_name = os.path.splitext(filename)[0]
            clip_raster(
                filepath,
                study_area.name,
                study_area.boundary_4326,
                add_excl_rasters_dir,
                data_name,
            )


def prepare_additional_inclusion_polygons(study_area: StudyArea, folder_name):
    """Clip and reproject additional inclusion polygons."""
    print("\nprocessing additional inclusion polygons")
    prepare_inclusion_polygon_folder(
        os.path.join(
            study_area.raw_spatial_data_folder, "additional_inclusion_polygons"
        ),
        os.path.join(study_area.output_dir, "additional_inclusion_polygons"),
        folder_name,
        study_area.boundary_4326,
        study_area.name,
        study_area.global_crs,
        study_area.global_crs_tag,
    )


def prepare_additional_inclusion_rasters(study_area: StudyArea, folder_name):
    """Clip and reproject additional inclusion rasters to the study-area CRS."""
    print("\nprocessing additional inclusion rasters")
    prepare_inclusion_raster_folder(
        os.path.join(
            study_area.raw_spatial_data_folder, "additional_inclusion_rasters"
        ),
        os.path.join(study_area.output_dir, "additional_inclusion_rasters"),
        folder_name,
        study_area.boundary_4326,
        study_area.name,
    )
