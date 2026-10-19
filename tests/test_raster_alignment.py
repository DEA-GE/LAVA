import numpy as np
import geopandas as gpd
import rasterio
from pyproj import CRS
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import Resampling
from shapely.geometry import box

from lava.datasets.wind_solar_atlas import _clip_to_4326
from lava.utils.study_area import StudyArea
from lava.utils.raster import align_to_reference


def test_align_to_reference_reprojects_between_crs() -> None:
    with MemoryFile() as source_file, MemoryFile() as reference_file:
        with source_file.open(
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_bounds(0, 0, 1, 1, 2, 2),
        ) as source:
            source.write(np.array([[1, 2], [3, 4]], dtype="float32"), 1)
            with reference_file.open(
                driver="GTiff",
                height=2,
                width=2,
                count=1,
                dtype="float32",
                crs="EPSG:3857",
                transform=from_bounds(0, 0, 111319.49, 111325.14, 2, 2),
            ) as reference:
                aligned = align_to_reference(
                    source, reference, resampling=Resampling.bilinear
                )

    assert aligned.shape == (2, 2)
    assert np.isfinite(aligned).all()


def test_atlas_clip_stays_in_global_crs(tmp_path) -> None:
    source_path = tmp_path / "atlas.tif"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    boundary = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    study_area = StudyArea(
        name="test_region",
        boundary_4326=boundary,
        local_crs=CRS.from_epsg(3857),
        raw_spatial_data_folder=tmp_path,
        output_dir=output_dir,
        boundary_mollweide=boundary,
        boundary_buffered_4000_4326=boundary.geometry,
        bounding_box_4326=np.array([0, 0, 1, 1]),
    )
    with rasterio.open(
        source_path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 1, 0.5, 0.5),
    ) as source:
        source.write(np.ones((2, 2), dtype="float32"), 1)

    output_path = _clip_to_4326(source_path, study_area, "wind")

    with rasterio.open(output_path) as clipped:
        assert clipped.crs == CRS.from_epsg(4326)
    assert output_path.endswith("wind_test_region_EPSG4326.tif")
    assert not (output_dir / "wind_test_region_EPSG3857.tif").exists()
