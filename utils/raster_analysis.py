import numpy as np
from scipy.ndimage import label
import rasterio
from rasterio.warp import reproject, Resampling
import math
import geopandas as gpd
from affine import Affine
from rasterio.crs import CRS
from rasterio.io import MemoryFile


# area filter
def area_filter(boolean_array, min_size):
    # Label connected components in the array
    labeled_array, num_features = label(boolean_array)

    # Count the number of pixels in each component
    component_sizes = np.bincount(labeled_array.ravel())

    # Create a mask for components that meet the size requirement (ignoring the background)
    large_component_mask = np.zeros_like(component_sizes, dtype=bool)
    large_component_mask[1:] = (
        component_sizes[1:] >= min_size
    )  # Skip the background component (index 0)

    # Filter the original array, keeping only large components
    filtered_array = large_component_mask[labeled_array]

    return filtered_array


# Transform raster based on a given raster
def align_to_reference(src, ref, resampling=Resampling.nearest):
    """
    Reproject and resample `src` to match `ref` (CRS, transform, shape).
    Returns a rasterio in-memory dataset aligned to `ref`.

    Parameters:
        src: rasterio dataset to reproject
        ref: rasterio dataset to match

    Returns:
        rasterio.io.DatasetReader (in-memory)
    """
    dtype = src.dtypes[0]
    nodata = src.nodata if src.nodata is not None else 0

    dst_array = np.full((ref.height, ref.width), nodata, dtype=dtype)

    reproject(
        source=src.read(1),
        destination=dst_array,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=ref.transform,
        dst_crs=ref.crs,
        resampling=resampling,
        dst_nodata=nodata,
    )

    # Change nan to zero
    dst_array[dst_array == np.nan] = 0
    return dst_array


def check_alignment(raster_paths):
    """
    Check if all rasters have the same CRS, transform, width, and height.

    Parameters:
        raster_paths (list of str): List of file paths to rasters.

    Returns:
        bool: True if all rasters are aligned, False otherwise.
        str: Message explaining the result.
    """

    with rasterio.open(raster_paths[0]) as ref:
        ref_crs = ref.crs
        ref_transform = ref.transform
        ref_shape = (ref.width, ref.height)

    for path in raster_paths[1:]:
        with rasterio.open(path) as src:
            if src.crs != ref_crs:
                return False, f"CRS mismatch: {path}"
            if src.transform != ref_transform:
                return False, f"Transform mismatch: {path}"
            if (src.width, src.height) != ref_shape:
                return False, f"Dimension mismatch: {path}"

    return "All rasters are aligned."


# Function to compute overlap between two masked arrays
def overlap(arrays):
    """
    Compute overlap mask (where all input arrays have data > 0).

    Parameters
    ----------
    arrays : list of numpy arrays
        All arrays must have the same shape.

    Returns
    -------
    overlap_mask : numpy array (int)
        1 where all arrays > 0, else 0.
    """
    if not arrays:
        raise ValueError("Input list 'arrays' is empty.")

    # Start with a mask of ones and combine with &
    mask = np.ones_like(arrays[0], dtype=bool)
    for arr in arrays:
        mask &= arr > 0

    return mask.astype(int)


# Function to compute union mask of multiple masked array where at least one has data
def union(arrays):
    """
    Compute union of multiple masked arrays where at least one has data.

    Parameters:
        arrays (list of numpy.ndarray): List of masked arrays.

    Returns:
        numpy.ndarray: Union mask where at least one array has data.
    """

    union_mask = np.zeros_like(arrays[0], dtype=int)
    for array in arrays:
        union_mask |= array > 0

    return union_mask.astype(int)


# Function to compute difference between two masked arrays
def diff(array1, array2):
    # Compute difference mask (where data1 is present but data2 is not)
    diff_mask = (array1 > 0) & (array2 == 0)

    return diff_mask.astype(int)


# Function to filter a raster based on a value raster and a range
def filter(filter_array, value_array, vmin, vmax):
    vmin = float(vmin)
    vmax = float(vmax)
    filtered_mask = (filter_array > 0) & (value_array >= vmin) & (value_array < vmax)

    return filtered_mask.astype(int)


def export_raster(array, path, ref, crs):
    """
    Export a numpy array as a raster file.

    Parameters:
        array (numpy.ndarray): The data to export.
        path (str): The file path to save the raster.
        ref (rasterio.io.DatasetReader): Reference raster for CRS and transform.
    """
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=array.dtype,
        crs=crs,
        transform=ref.transform,
        nodata=0,
    ) as dst:
        dst.write(array, 1)


def rasterize(
    vector_path: str,
    crs,
    resolution: float,
    all_touched: bool = False,
    fill_value: float | int = 0,
    pad: float = 0.0,
):
    """
    Wrap a NumPy raster + transform + crs into an in-memory rasterio dataset.

    Returns
    -------
    memfile : rasterio.io.MemoryFile
        Keep this alive as long as you need the dataset.
    ds : rasterio.io.DatasetReader
        Open dataset you can read from (and close when done).
    """

    """
    Rasterize a vector file into an in-memory NumPy array.

    Parameters
    ----------
    geojson_path : str
        Path to the vector file.
    epsg_or_crs : int | str
        Target CRS (e.g. 32632 or "EPSG:32632").
    resolution : float
        Pixel size in meters.
    attribute : str | None
        Column name to burn values from; if None, burns 1.
    all_touched : bool
        If True, include all pixels touched by geometries.
    fill_value : int | float
        Background value for pixels outside geometries.
    pad : float
        Extra buffer (in meters) added around vector bounds.

    Returns
    -------
    raster : np.ndarray
        2D array with rasterized values.
    transform : affine.Affine
        Geotransform for the raster.
    crs : rasterio.crs.CRS
        Coordinate reference system of the raster.
    """

    # --- Load and reproject ---
    gdf = gpd.read_file(vector_path)
    if gdf.empty:
        raise ValueError("Vector has no features.")
    target_crs = CRS.from_user_input(crs)
    gdf = gdf.to_crs(target_crs)
    gdf["geometry"] = gdf.geometry.buffer(0)  # fix invalids

    # Bounds (snap to resolution so grid is neat)
    minx, miny, maxx, maxy = gdf.total_bounds
    minx -= pad
    miny -= pad
    maxx += pad
    maxy += pad

    def _floor(v, res):
        return math.floor(v / res) * res

    def _ceil(v, res):
        return math.ceil(v / res) * res

    minx, miny, maxx, maxy = (
        _floor(minx, resolution),
        _floor(miny, resolution),
        _ceil(maxx, resolution),
        _ceil(maxy, resolution),
    )

    width = int(round((maxx - minx) / resolution))
    height = int(round((maxy - miny) / resolution))
    if width <= 0 or height <= 0:
        raise ValueError("Non-positive raster size; check resolution/pad/geometry.")

    transform = Affine(resolution, 0, minx, 0, -resolution, maxy)

    # (geometry, value) pairs — always burn 1 inside polygon
    shape_value_pairs = [(geom, 1) for geom in gdf.geometry]

    raster = rasterio.features.rasterize(
        shape_value_pairs,
        out_shape=(height, width),
        transform=transform,
        fill=fill_value,
        all_touched=all_touched,
        dtype="float32"
        if any(isinstance(v, float) for _, v in shape_value_pairs)
        else "uint16",
    )

    # Ensure shape is (bands, height, width)
    if raster.ndim == 2:
        arr_to_write = raster[np.newaxis, ...]
    elif raster.ndim == 3:
        arr_to_write = raster
    else:
        raise ValueError("arr must be 2D (H, W) or 3D (C, H, W)")

    count, height, width = arr_to_write.shape
    dtype = arr_to_write.dtype

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": count,
        "dtype": dtype,
        "crs": target_crs,
        "transform": transform,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "deflate",
    }
    # if nodata is not None:
    #    profile["nodata"] = nodata

    memfile = MemoryFile()
    ds = memfile.open(**profile)
    ds.write(arr_to_write)

    return ds, memfile
