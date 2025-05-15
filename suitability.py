import rasterio
import numpy as np
import warnings
import os

os.chdir("C:/Users/jck/OneDrive - EAEA/Documents/01_Projects/25 CETO/Model/GIS project/")


value_raster_path = 'DNK_wind-speed_100m_EPSG3857.tif'
exclusion_raster_path = 'excluson_test_EPSG3857.tif'
value_min = 6.5
value_max = 7
exclude_value=1

def suitability_tier(
    value_raster_path,
    exclusion_raster_path,
    value_min,
    value_max,
    exclude_value=0
):
    """
    Calculates the area in km² where the value raster is within [value_min, value_max]
    and the exclusion raster is NOT equal to `exclude_value`.

    Parameters:
    - value_raster_path: Path to the value raster file.
    - exclusion_raster_path: Path to the exclusion mask raster file (same shape/resolution).
    - value_min: Minimum threshold value (inclusive).
    - value_max: Maximum threshold value (inclusive).
    - exclude_value: Value in exclusion raster to exclude (default is 1).

    Returns:
    - area_km2: Area in square kilometers.
    """
    with rasterio.open(value_raster_path) as val_src, rasterio.open(exclusion_raster_path) as excl_src:
        # Check that both rasters match in dimensions
        if (val_src.width != excl_src.width or val_src.height != excl_src.height):
            raise ValueError("Value raster and exclusion raster must have the same dimensions")

        print(val_src.height)

        # CRS check
        crs = val_src.crs
        if crs is None:
            warnings.warn("Raster has no defined CRS. Area calculation may be invalid.")
        elif crs.is_geographic:
            warnings.warn(f"Raster CRS is geographic (units in degrees): {crs.to_string()}. "
                          "Consider reprojecting to a projected CRS (e.g. UTM) for accurate area calculation.")

        val_data = val_src.read(1, masked=True)
        excl_data = excl_src.read(1, masked=True)

        transform = val_src.transform
        pixel_area_m2 = abs(transform.a * transform.e)
        print(transform.e)
        pixel_area_km2 = pixel_area_m2 / 1e6

        # Build mask: within value range and not excluded
        valid_mask = (val_data >= value_min) & (val_data <= value_max)
        not_excluded = (excl_data != exclude_value)
        combined_mask = valid_mask & not_excluded

        area_km2 = np.sum(combined_mask) * pixel_area_km2

    return area_km2
