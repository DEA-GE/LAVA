import numpy as np
from scipy.ndimage import label
import rasterio
from rasterio.warp import reproject, Resampling


# area filter
def area_filter(boolean_array, min_size):
    # Label connected components in the array
    labeled_array, num_features = label(boolean_array)
    
    # Count the number of pixels in each component
    component_sizes = np.bincount(labeled_array.ravel())
    
    # Create a mask for components that meet the size requirement (ignoring the background)
    large_component_mask = np.zeros_like(component_sizes, dtype=bool)
    large_component_mask[1:] = component_sizes[1:] >= min_size  # Skip the background component (index 0)
    
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
def overlap(array1, array2):
    # Compute overlap mask (where both rasters have data)
    overlap_mask = (array1 > 0) & (array2 > 0)

    return overlap_mask.astype(int)

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
        union_mask |= (array > 0)

    return union_mask.astype(int)

# Function to compute difference between two masked arrays
def diff(array1, array2):
    # Compute difference mask (where data1 is present but data2 is not)
    diff_mask = (array1 > 0) & (array2 == 0)

    return diff_mask.astype(int)

# Function to filter a raster based on a value raster and a range
def filter(filter_array, value_array, vmin, vmax):
    vmin=float(vmin)
    vmax=float(vmax)
    filtered_mask = (filter_array > 0) & (value_array >= vmin) & (value_array <= vmax)

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
        path, 'w',
        driver='GTiff',
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=array.dtype,
        crs=crs,
        transform=ref.transform,
        nodata=0
    ) as dst:
        dst.write(array, 1)
