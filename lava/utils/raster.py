import os
import math

import numpy as np
import rasterio
import geopandas as gpd
from affine import Affine
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import mapping
from scipy.ndimage import label


def save_richdem_file(richdem_file, base_dem_FilePath, outFilePath):
    with rasterio.open(base_dem_FilePath) as src:
        file_profile = src.profile
    # For the new file's profile, we start with the profile of the source
    profile = file_profile

    profile.update(
        dtype=rasterio.int16, count=1, compress="DEFLATE", nodata=richdem_file.no_data
    )
    # save raster file
    with rasterio.open(outFilePath, "w", **profile) as dst:
        dst.write(richdem_file, 1)  # richdem_file.astype(rasterio.int16)


def clip_raster(
    input_raster_path, region_name_clean, gdf, output_dir, data_name=None, dtype=None
):
    """
    Clips a raster to the geometry defined in a GeoDataFrame and saves the clipped raster.

    Parameters:
    - input_raster_path (str): Path to the input raster file.
    - region_name_clean (str): Cleaned name of the region for filename purposes.
    - gdf (GeoDataFrame): GeoDataFrame containing the geometry to clip to.
    - output_dir (str): Directory to save the clipped raster.
    - data_name (str, optional): Output filename prefix.
    - dtype (str, optional): Output raster dtype key (e.g. 'int8', 'int16', 'float32'). If None, keep source dtype.

    Returns:
    - str: Path to the clipped GeoTIFF written to the output directory.
    """

    # get the filename from file path and remove its extension
    filename = os.path.basename(input_raster_path)
    filename = os.path.splitext(filename)[0]

    dtype_options = {
        "int8": rasterio.int8,
        "uint8": rasterio.uint8,
        "int16": rasterio.int16,
        "uint16": rasterio.uint16,
        "float32": rasterio.float32,
        "float64": rasterio.float64,
    }

    if dtype is not None and dtype not in dtype_options:
        raise ValueError(
            f"Unsupported dtype '{dtype}'. Supported values are: {list(dtype_options.keys())}"
        )

    with rasterio.open(input_raster_path) as src:
        # Mask the raster using the vector file's geometry.
        # all_touched=True keeps every pixel that touches the polygon boundary,
        # not just pixels whose centre falls inside — prevents edge pixels from
        # being incorrectly dropped at the region boundary.
        out_image, out_transform = mask(
            src, gdf.geometry.apply(mapping), crop=True, all_touched=True
        )
        # Copy the metadata from the source raster
        out_meta = src.meta.copy()
        # Update the metadata for the clipped raster
        out_meta.update(
            {
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "compress": "DEFLATE",
            }
        )

        if dtype is not None:
            out_dtype = dtype_options[dtype]
            out_image = out_image.astype(out_dtype, copy=False)
            out_meta.update({"dtype": out_dtype})

        ori_raster_crs = str(src.crs)
        ori_raster_crs = ori_raster_crs.replace(":", "")
        # print(f'original raster CRS: {src.crs}')
        # Save the clipped raster as a new GeoTIFF file.
        output_prefix = filename if data_name is None else data_name
        output_path = os.path.join(
            output_dir, f"{output_prefix}_{region_name_clean}_{ori_raster_crs}.tif"
        )
        with rasterio.open(output_path, "w", **out_meta) as dest:
            dest.write(out_image)

    return output_path


def clip_reproject_raster(
    input_raster_path,
    region_name_clean,
    gdf,
    data_name,
    target_crs,
    resampling_method,
    dtype,
    output_dir,
    scale_factor=1,
):
    """
    Reads a TIFF raster, clips it to the extent of a GeoPandas DataFrame, reprojects it to a given CRS considerung the set resampling method,
    and saves the clipped raster in a specified output folder.

    :param input_raster_path: Path to the input TIFF raster file.
    :param region_name_clean: in main script cleaned region name
    :param gdf: The GeoPandas DataFrame to use for clipping the raster.
    :param data_name: string with "landcover" or "elevation" or "wind" or "solar" or any other name which specifies the data.
    :param target_crs: The target CRS to reproject the raster to (e.g., 'EPSG:3035').
    :param resampling_method: resampling method to be used (string)
    :param output_dir: output directory (defined in main script)
    :param scale_factor: Multiply clipped pixel values by this factor before saving/reprojection.
    """

    # get CRS tag as clean string
    auth = target_crs.to_authority()
    crs_tag = "".join(auth) if auth else target_crs.to_string().replace(":", "_")

    resampling_options = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
        "mode": Resampling.mode,
    }

    dtype_options = {
        "int8": rasterio.int8,
        "uint8": rasterio.uint8,
        "int16": rasterio.int16,
        "uint16": rasterio.uint16,
        "float32": rasterio.float32,
        "float64": rasterio.float64,
    }

    with rasterio.open(input_raster_path) as src:
        # Mask the raster using the vector file's geometry.
        # all_touched=True keeps every pixel that touches the polygon boundary,
        # not just pixels whose centre falls inside — prevents edge pixels from
        # being incorrectly dropped at the region boundary.
        out_image, out_transform = mask(
            src, gdf.geometry.apply(mapping), crop=True, all_touched=True
        )
        if scale_factor != 1:
            # Apply scaling and cast back to the dtype defined for this function call.
            target_dtype = dtype_options[dtype]
            out_image = (out_image.astype(np.float32) * float(scale_factor)).astype(
                target_dtype, copy=False
            )
        # Copy the metadata from the source raster
        out_meta = src.meta.copy()
        # Update the metadata for the clipped raster
        out_meta.update(
            {
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
            }
        )

        ori_raster_crs = str(src.crs)
        ori_raster_crs = ori_raster_crs.replace(":", "")
        # print(f'original raster CRS: {src.crs}')
        # Save the clipped raster as a new GeoTIFF file
        with rasterio.open(
            os.path.join(
                output_dir, f"{data_name}_{region_name_clean}_{ori_raster_crs}.tif"
            ),
            "w",
            **out_meta,
        ) as dest:
            dest.write(out_image)

    # reproject landcover raster to local UTM CRS
    with rasterio.open(
        os.path.join(
            output_dir, f"{data_name}_{region_name_clean}_{ori_raster_crs}.tif"
        )
    ) as src:
        # Calculate the transformation and dimensions for the target CRS
        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds
        )
        kwargs = src.meta.copy()
        kwargs.update(
            {
                "crs": target_crs,
                "transform": transform,
                "width": width,
                "height": height,
                "dtype": dtype_options[dtype],
            }
        )

        # Create the output file path
        output_path = os.path.join(
            output_dir, f"{data_name}_{region_name_clean}_{crs_tag}.tif"
        )

        # Reproject and save the raster
        with rasterio.open(output_path, "w", **kwargs, compress="DEFLATE") as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=resampling_options[resampling_method],
                )


def reproject_raster(
    input_raster_path,
    region_name_clean,
    target_crs,
    resampling_method,
    dtype,
    outputFilePath,
):

    resampling_options = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
        "mode": Resampling.mode,
    }

    dtype_options = {
        "int8": rasterio.int8,
        "uint8": rasterio.uint8,
        "int16": rasterio.int16,
        "uint16": rasterio.uint16,
        "float32": rasterio.float32,
        "float64": rasterio.float64,
    }

    # reproject landcover raster to local UTM CRS
    with rasterio.open(os.path.join(input_raster_path)) as src:
        # Calculate the transformation and dimensions for the target CRS
        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds
        )
        kwargs = src.meta.copy()
        kwargs.update(
            {
                "crs": target_crs,
                "transform": transform,
                "width": width,
                "height": height,
                "dtype": dtype_options[dtype],
            }
        )

        # Create the output file path
        output_path = outputFilePath

        # Reproject and save the raster
        with rasterio.open(output_path, "w", **kwargs, compress="DEFLATE") as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=resampling_options[resampling_method],
                )

            # Preserve colormap if present
            if src.count == 1:
                try:
                    colormap = src.colormap(1)
                    if colormap:
                        dst.write_colormap(1, colormap)
                except (ValueError, KeyError):
                    pass  # No colormap present or band index invalid


def co_register(
    infile, match, resampling_method, outfile, dtype
):  # source: https://pygis.io/docs/e_raster_resample.html
    """Reproject a file to match the shape and projection of existing raster. (co-registration)

    Parameters
    ----------
    infile : (string) path to input file to reproject
    match : (string) path to raster with desired shape and projection
    outfile : (string) path to output file tif
    """
    resampling_options = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
        "mode": Resampling.mode,
    }

    dtype_options = {
        "int8": rasterio.int8,
        "uint8": rasterio.uint8,
        "int16": rasterio.int16,
        "uint16": rasterio.uint16,
        "float32": rasterio.float32,
        "float64": rasterio.float64,
    }

    # open input
    with rasterio.open(infile) as src:
        # open input to match
        with rasterio.open(match) as match:
            dst_crs = match.crs

            # calculate the output transform matrix
            dst_transform, dst_width, dst_height = calculate_default_transform(
                src.crs,  # input CRS
                dst_crs,  # output CRS
                match.width,  # input width
                match.height,  # input height
                *match.bounds,  # unpacks input outer boundaries (left, bottom, right, top)
            )

        # set properties for output
        dst_profile = src.profile.copy()

        # dst_kwargs.update({"crs": dst_crs,
        #                   "transform": dst_transform,
        #                   "width": dst_width,
        #                   "height": dst_height,
        #                   "nodata": -9999,
        #                   "dtype": rasterio.int16})

        dst_profile.update(
            crs=dst_crs,
            transform=dst_transform,
            width=dst_width,
            height=dst_height,
            dtype=dtype_options[dtype],
            count=1,
            nodata=-9999,
            compress="DEFLATE",
        )

        # print("Coregistered to shape:", dst_height,dst_width,'\n Affine',dst_transform)
        # open output
        with rasterio.open(outfile, "w", **dst_profile) as dst:
            # iterate through bands and write using reproject function
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    resampling=resampling_options[resampling_method],
                )


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


def overlay_value_raster(
    mask_array,
    dst_transform,
    dst_crs,
    src_array,
    src_transform,
    src_crs,
    src_nodata=None,
):
    """
    Reproject a continuous value array onto the eligible-land mask grid and
    return values only for eligible pixels (mask == True), NaN elsewhere.
    Everything is done in-memory; no files are written.

    Parameters
    ----------
    mask_array : numpy.ndarray (bool)
        Boolean array where True marks eligible pixels.
    dst_transform : affine.Affine
        Affine transform of the output/mask grid.
    dst_crs : CRS-like
        CRS of the output/mask grid.
    src_array : numpy.ndarray
        2-D array of source values (e.g. wind speed or PV output).
    src_transform : affine.Affine
        Affine transform of *src_array*.
    src_crs : CRS-like
        CRS of *src_array*.
    src_nodata : float or None
        Nodata value of the source array.

    Returns
    -------
    numpy.ndarray (float32)
        Array of the same shape as *mask_array* with reprojected values where
        the mask is True and np.nan elsewhere.
    """
    height, width = mask_array.shape
    dst_array = np.full((height, width), fill_value=np.nan, dtype=np.float32)

    reproject(
        source=src_array.astype(np.float32),
        destination=dst_array,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.nearest,
        src_nodata=src_nodata,
        dst_nodata=np.nan,
    )

    dst_array[~mask_array] = np.nan
    return dst_array


def diff(array1, array2):
    # Compute difference mask (where data1 is present but data2 is not)
    diff_mask = (array1 > 0) & (array2 == 0)

    return diff_mask.astype(int)


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
