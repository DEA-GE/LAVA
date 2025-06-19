import rasterio
import numpy as np
import pandas as pd
import warnings
import os
import rasterio
import matplotlib.pyplot as plt
from rasterio.warp import reproject, Resampling
from rasterio.io import MemoryFile
import itertools

os.chdir("E:/CETO 2025 Spatial Analysis data/")

#------- Assumptions -------
# Make dictionary of wg and sg threshold
wg_thr = {'WG1': [0, 5], 'WG2': [5, 7], 'WG3': [7, 10]}
sg_thr = {'SG1': [0, 4.6], 'SG2': [4.6, 4.7], 'SG3': [4.7, 10]}
tiers = {'Tier1': [0, 0.5e6], 'Tier2': [0.5e6, 1e6], 'Tier3': [1e6, 2e6]}
sub_dist_cost_factor = 10

province = 'NeiMongol'


# ------ Load rasters ------
src1 = rasterio.open('NeiMongol/Wind_avail_test.tif')
src2 = rasterio.open('NeiMongol/Solar_avail_test.tif')

GWA = rasterio.open('GIS/GWA/CHN_wind-speed_100m.tif')
GSA = rasterio.open('GIS/GSA/GHI.tif')

substation_distance = rasterio.open('NeiMongol/proximity/substation_distance_raster_EPSG32650.tif')

transform = substation_distance.transform
pixel_area_m2 = abs(transform.a * transform.e)
pixel_area_km2 = pixel_area_m2 / 1e6


# -------------- TO DO: Check that rasters are formatted correcly and use same CRS --------------
if src1.transform != src2.transform or src1.width != src2.width or src1.height != src2.height:
    raise ValueError("Rasters must have the same extent, resolution, and transform.")

# CRS check
if crs is None:
    warnings.warn("Raster has no defined CRS. Area calculation may be invalid.")
elif crs.is_geographic:
    warnings.warn(f"Raster CRS is geographic (units in degrees): {crs.to_string()}. "
                    "Consider reprojecting to a projected CRS (e.g. UTM) for accurate area calculation.")


#---- Reproject rasters to a common CRS ----
GWA_reproj = align_to_reference(GWA, src1)
GSA_reproj = align_to_reference(GSA, src2)
substation_distance_reproj = align_to_reference(substation_distance, src1)
wind_avail_reproj = align_to_reference(src1, src1)
solar_avail_reproj = align_to_reference(src2, src2)


# Transform raster based on a given raster
def align_to_reference(src, ref):
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
        resampling=Resampling.nearest,
        dst_nodata=nodata,
    )
    '''
    profile = ref.profile.copy()
    profile.update({
        "dtype": dtype,
        "count": 1,
        "nodata": nodata,
    })

    memfile = MemoryFile()
    with memfile.open(**profile) as dataset:
        dataset.write(dst_array, 1)

    return memfile.open()
    '''
    return dst_array

# Function to compute overlap between two masked arrays
def overlap(data1, data2):
    # Compute overlap mask (where both rasters have data)
    overlap_mask = data1 & data2

    return overlap_mask

# Function to compute difference between two rasters
def diff(data1, data2):
    # Compute difference mask (where data1 is present but data2 is not)
    diff_mask = data1 & ~data2

    return diff_mask

# Function to filter a raster based on a value raster and a range
def filter(src, src_value, vmin, vmax):
    '''
    if src1.transform != src_value.transform or src1.width != src_value.width or src1.height != src_value.height:
        raise ValueError("Rasters must have the same extent, resolution, and transform.")

    data1 = src.read(1, masked=True)
    data2 = src_value.read(1, masked=True)

    filtered_mask = (~data1.mask) & (data2 >= vmin) & (data2 < vmax)
    '''

    filtered_mask = src & (src_value >= vmin) & (src_value < vmax)

    return filtered_mask

# Function to calculate the area in km² based on a value raster and an exclusion raster
def tier_potential(value_raster_path, exclusion_raster, cost_value_min, cost_value_max, exclude_value=0):
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

        val_data = val_src.read(1, masked=True)
        excl_data = excl_src.read(1, masked=True)



        # Build mask: within value range and not excluded
        valid_mask = (val_data >= value_min) & (val_data <= value_max)
        not_excluded = (excl_data != exclude_value)
        combined_mask = valid_mask & not_excluded

        area_km2 = np.sum(combined_mask) * pixel_area_km2

    return area_km2


# Cost map calculation
sub_dist = substation_distance_reproj
costmap = sub_dist * sub_dist_cost_factor

SG = sg_thr.keys()
WG = wg_thr.keys()
SG_WG_comb = list(itertools.product(SG, WG))  # All combinations of SG and WG

wind_maps = {wg: filter(wind_avail_reproj, GWA_reproj, wg_thr[wg][0], wg_thr[wg][1]) for wg in WG}
solar_maps = {sg: filter(solar_avail_reproj, GSA_reproj, sg_thr[sg][0], sg_thr[sg][1]) for sg in SG}

a_indiv = [f"{province}_{sg}" for sg in SG] + [f"{province}_{wg}" for wg in WG]
a_comb = [f"{province}_{sg}_{wg}" for sg, wg in SG_WG_comb]
areas = a_indiv + a_comb

df_tier_potentials = pd.DataFrame(index=areas, columns=tiers.keys())

# Find all solar potentials that do not overlap with wind potentials
for sg in SG:
    print(f'Processing solar potential: {sg}')
    
    inclusion_area = diff(solar_maps[sg], wind_avail_reproj)

    for t in tiers:
        tier_area = filter(inclusion_area, costmap, tiers[t][0], tiers[t][1])
        df_tier_potentials.loc[f"{province}_{sg}", t] = np.sum(tier_area) * pixel_area_km2

# Find all wind potentials that do not overlap with solar potentials
for wg in WG:
    print(f'Processing wind potential: {wg}')
    
    inclusion_area = diff(wind_maps[wg], solar_avail_reproj)

    for t in tiers:
        tier_area = filter(inclusion_area, costmap, tiers[t][0], tiers[t][1])
        df_tier_potentials.loc[f"{province}_{wg}", t] = np.sum(tier_area) * pixel_area_km2

# Find all ares with combinations of solar and wind potentials
for sg, wg in SG_WG_comb:
    print(f'Processing combination: {sg} and {wg}')
    
    inclusion_area = overlap(solar_maps[sg], wind_maps[wg])

    for i, t in enumerate(tiers):
        tier_area = filter(inclusion_area, costmap, tiers[t][0], tiers[t][1])
        df_tier_potentials.loc[f"{province}_{sg}_{wg}", t] = np.sum(tier_area) * pixel_area_km2


plt.figure(figsize=(10, 6))
plt.imshow(costmap, cmap='viridis')
#plt.imshow(inclusion_area, cmap='viridis')
#plt.imshow(solar_maps['SG3'], cmap='viridis')
#plt.imshow(wind_maps['WG3'], cmap='viridis')
plt.colorbar(label='Overlap Value')
plt.xlabel('Longitude')
plt.ylabel('Latitude')
plt.show()


