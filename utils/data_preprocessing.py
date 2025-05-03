import os
import geopandas as gpd
import json
import rasterio
from rasterio.crs import CRS
from rasterio.mask import mask
from shapely.geometry import mapping
from unidecode import unidecode
from rasterio.warp import calculate_default_transform, reproject, Resampling
import numpy as np

import zipfile
import requests
import io
import fiona
import urllib.parse

import logging


#download WDPA functions
def download_unpack_zip(url, output_dir):
    response = requests.get(url)
    # Check if the download was successful
    if response.status_code == 200:
        # Open the downloaded content as a zipfile
        logging.info("Download complete, extracting files...")
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(path=output_dir)
        logging.info(f"Files extracted to {os.path.abspath(output_dir)}")
    else:
        logging.warning(f"Failed to download the file, status code: {response.status_code}")

# Function to find the geodatabase folder
def find_folder(directory, file_ending=None, string_in_name=None):
    for root, dirs, files in os.walk(directory):
        for folder in dirs:
            if file_ending is not None:
                if folder.endswith(file_ending):
                    return os.path.join(root, folder)
                    logging.info('Found folder with geodatabase')
            if string_in_name is not None:
                if string_in_name in folder:
                    return os.path.join(root, folder)
                    logging.info('WDPA folder of country already existed')
    return None
  

def convert_gdb_to_gpkg(gdb_folder, output_dir, filename):
    layers = fiona.listlayers(gdb_folder) #list all layers
    poly_layer = next((layer for layer in layers if 'poly' in layer.lower()), None) #find the layer containing the word "poly" for the polygon layer
    if poly_layer:
        gdf = gpd.read_file(gdb_folder, layer=poly_layer)
        gdf.to_file(os.path.join(output_dir, filename), driver='GPKG', encoding='utf-8')
        logging.info(f'WDPA saved as gpkg to {output_dir}')
    else:
        logging.warning("No layer containing 'poly' in its name was found. No WDPA saved.")






#geodata functions

def save_richdem_file(richdem_file, base_dem_FilePath, outFilePath):
    with rasterio.open(base_dem_FilePath) as src:
        file_profile = src.profile
    # For the new file's profile, we start with the profile of the source
    profile = file_profile

    profile.update(
        dtype=rasterio.int16,
        count=1,
        compress='DEFLATE',
        nodata=richdem_file.no_data) 
    #save raster file
    with rasterio.open(outFilePath, 'w', **profile) as dst:
        dst.write(richdem_file, 1)  #richdem_file.astype(rasterio.int16)


def geopandas_clip_reproject(geopandas_file, gdf, target_crs):
    """
    Clips vector file to the extent of a GeoPandas DataFrame and reprojects it to a given CRS.

    
    :param gdf: The GeoPandas DataFrame to use for clipping the shapefile.
    :target_crs: The target CRS to reproject the shapefile to (e.g., 'EPSG:3035').
    """
    
    #clip files 
    geopandas_clipped = gpd.clip(geopandas_file, gdf)
    #reproject and save files
    geopandas_clipped.to_crs(epsg=target_crs, inplace=True)
    
    return geopandas_clipped


def clip_raster(input_raster_path, region_name_clean, gdf,output_dir):
    """
    Clips a raster to the geometry defined in a GeoDataFrame and saves the clipped raster.

    Parameters:
    - input_raster_path (str): Path to the input raster file.
    - region_name_clean (str): Cleaned name of the region for filename purposes.
    - gdf (GeoDataFrame): GeoDataFrame containing the geometry to clip to.
    - output_dir (str): Directory to save the clipped raster.

    Returns:
    - None. Saves the clipped raster as a new GeoTIFF in the output directory.
    """

    #get the filename from file path and remove its extension
    filename = os.path.basename(input_raster_path)
    filename = os.path.splitext(filename)[0]

    with rasterio.open(input_raster_path) as src:
        # Mask the raster using the vector file's geometry
        out_image, out_transform = mask(src, gdf.geometry.apply(mapping), crop=True)
        # Copy the metadata from the source raster
        out_meta = src.meta.copy()
        # Update the metadata for the clipped raster
        out_meta.update({
            'height': out_image.shape[1],
            'width': out_image.shape[2],
            'transform': out_transform
        })

        ori_raster_crs = str(src.crs)
        ori_raster_crs = ori_raster_crs.replace(":", "")
        print(f'original raster CRS: {src.crs}')
        # Save the clipped raster as a new GeoTIFF file
        with rasterio.open(os.path.join(output_dir, f'{filename}_{region_name_clean}_{ori_raster_crs}.tif'), 'w', **out_meta) as dest:
            dest.write(out_image)




def clip_reproject_raster(input_raster_path, region_name_clean, gdf, data_name, target_crs, resampling_method, dtype, output_dir):
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
        """
    
    resampling_options = {
        'nearest': Resampling.nearest,
        'bilinear': Resampling.bilinear,
        'cubic': Resampling.cubic
    }

    dtype_options = {
        'int8': rasterio.int8,
        'uint8': rasterio.uint8,
        'int16': rasterio.int16,
        'uint16': rasterio.uint16,
        'float32': rasterio.float32
    }

    with rasterio.open(input_raster_path, 'r+') as src:
        #manually set crs 4326
        #src.crs = CRS.from_epsg(4326)
        # Mask the raster using the vector file's geometry
        out_image, out_transform = mask(src, gdf.geometry.apply(mapping), crop=True)
        # Copy the metadata from the source raster
        out_meta = src.meta.copy()
        # Update the metadata for the clipped raster
        out_meta.update({
            'height': out_image.shape[1],
            'width': out_image.shape[2],
            'transform': out_transform
        })

        ori_raster_crs = str(src.crs)
        ori_raster_crs = ori_raster_crs.replace(":", "")
        print(f'original raster CRS: {src.crs}')
        # Save the clipped raster as a new GeoTIFF file
        with rasterio.open(os.path.join(output_dir, f'{data_name}_{region_name_clean}_{ori_raster_crs}.tif'), 'w', **out_meta) as dest:
            dest.write(out_image)

    # reproject landcover raster to local UTM CRS
    with rasterio.open(os.path.join(output_dir, f'{data_name}_{region_name_clean}_{ori_raster_crs}.tif')) as src:
        # Calculate the transformation and dimensions for the target CRS
        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds)
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': target_crs,
            'transform': transform, 
            'width': width,
            'height': height,
            'dtype': dtype_options[dtype]
        })

        # Create the output file path
        output_path = os.path.join(output_dir, f'{data_name}_{region_name_clean}_EPSG{target_crs}.tif')


        # Reproject and save the raster
        with rasterio.open(output_path, 'w', **kwargs, compress='DEFLATE') as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=resampling_options[resampling_method])
                
            print(f'reprojected raster CRS: {dst.crs}')
    



def reproject_raster(input_raster_path, region_name_clean, target_crs, resampling_method, outputFilePath):
       
    resampling_options = {
        'nearest': Resampling.nearest,
        'bilinear': Resampling.bilinear,
        'cubic': Resampling.cubic
    }

    # reproject landcover raster to local UTM CRS
    with rasterio.open(os.path.join(input_raster_path)) as src:
        # Calculate the transformation and dimensions for the target CRS
        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds)
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': target_crs,
            'transform': transform, 
            'width': width,
            'height': height,
            'dtype': rasterio.int16
        })

        # Create the output file path
        output_path = outputFilePath


        # Reproject and save the raster
        with rasterio.open(output_path, 'w', **kwargs, compress='DEFLATE') as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=resampling_options[resampling_method])
                
            print(f'reprojected raster CRS: {dst.crs}')


def co_register(infile, match, resampling_method, outfile, dtype): #source: https://pygis.io/docs/e_raster_resample.html
    """Reproject a file to match the shape and projection of existing raster. (co-registration)
    
    Parameters
    ----------
    infile : (string) path to input file to reproject
    match : (string) path to raster with desired shape and projection 
    outfile : (string) path to output file tif
    """
    resampling_options = {
        'nearest': Resampling.nearest,
        'bilinear': Resampling.bilinear,
        'cubic': Resampling.cubic
    }

    dtype_options = {
        'int8': rasterio.int8,
        'uint8': rasterio.uint8,
        'int16': rasterio.int16,
        'uint16': rasterio.uint16,
        'float32': rasterio.float32
    }

    # open input
    with rasterio.open(infile) as src:
        src_transform = src.transform
        
        # open input to match
        with rasterio.open(match) as match:
            dst_crs = match.crs
            
            # calculate the output transform matrix
            dst_transform, dst_width, dst_height = calculate_default_transform(
                src.crs,     # input CRS
                dst_crs,     # output CRS
                match.width,   # input width
                match.height,  # input height 
                *match.bounds,  # unpacks input outer boundaries (left, bottom, right, top)
            )

        # set properties for output
        dst_profile = src.profile.copy()
        
        #dst_kwargs.update({"crs": dst_crs,
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
            compress='DEFLATE') 
        

        print("Coregistered to shape:", dst_height,dst_width,'\n Affine',dst_transform)
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
                    resampling=resampling_options[resampling_method])
                


def landcover_information(landcoverRasterPath, data_path, region_name, EPSG):
    # Open the raster using a context manager
    with rasterio.open(landcoverRasterPath) as landcover:
        band = landcover.read(1, masked=True) # Read the first band, masked=True is masking no data values
        
        res = landcover.transform[0] #pixel size
        #save pixel size local CRS
        with open(os.path.join(data_path, f'pixel_size_{region_name}_{EPSG}.json'), 'w') as fp:
            json.dump(res, fp)

        #Available land cover codes
        land_codes = np.unique(band.data).tolist()
        #save landuses as json file
        with open(os.path.join(data_path, f'landuses_{region_name}.json'), 'w') as fp:
            json.dump(land_codes, fp)
                


def create_north_facing_pixels(slopeFilePath, aspectFilePath, region_name_clean, richdem_helper_dir, X, Y, Z):
    if 'resampled' in slopeFilePath:
        resampled = '_resampled'
    else:
        resampled = ''
     
    # Open the slope and aspect rasters
    with rasterio.open(slopeFilePath) as src_slope:
        slope = src_slope.read(1)  # Read the slope data
        profile = src_slope.profile  # Get the profile for writing the output file
        crs_slope = src_slope.crs  # Access the CRS from metadata
        EPSG_slope = crs_slope.to_epsg() #get EPSG code

    with rasterio.open(aspectFilePath) as src_aspect:
        aspect = src_aspect.read(1)  # Read the aspect data
        crs_aspect = src_aspect.crs  # Access the CRS from metadata
        EPSG_aspect = crs_aspect.to_epsg() #get EPSG code

    if EPSG_slope==EPSG_aspect:

        #create map showing pixels with slope bigger X and aspect between Y and Z (north facing with slope where you would not build PV)
        condition = (slope > X) & ((aspect >= Y) | (aspect <= Z))
        result = np.where(condition, 1, 0) # Create a new raster with the filtered results

        profile.update(dtype=rasterio.int16, count=1, nodata=0, compress='DEFLATE') # Update the profile for the output raster

        if result.sum() > 0:
            # Write the result to a new raster file
            with rasterio.open(os.path.join(richdem_helper_dir, f'north_facing_{region_name_clean}_EPSG{EPSG_slope}{resampled}.tif'), 'w', **profile) as dst:
                dst.write(result.astype(rasterio.int16), 1)
        if result.sum() == 0:
            logging.info('no north-facing pixel exceeding threshold slope')
    
    else:
        print('EPSG codes of used rasters is not the same')



#download global wind atlas
def download_global_wind_atlas(country_code: str, height: int, data_path: str = None):
    """
    Downloads wind speed data from the Global Wind Atlas API for a given country and height.

    Parameters:
        country_code (str): ISO 3166-1 alpha-3 country code (e.g., "AFG" for Afghanistan).
        height (int): Wind height in meters (e.g., 100).
        save_path (str, optional): Custom file name or path to save the file. If None, uses default naming.
    
    Returns:
        bool: True if successful, False otherwise.
    """
    url = f"https://globalwindatlas.info/api/gis/country/{country_code}/wind-speed/{height}"
    
    try:
        print(f"Downloading wind data for '{country_code}' from: {url}")
        response = requests.get(url)
        if response.ok:
            filePath = os.path.join(data_path, 'global_solar_wind_atlas', f"{country_code}_wind_speed_{height}.tif")
            with open(filePath, "wb") as f:
                f.write(response.content)
            print(f"Downloaded to: {filePath}")
            return True
        else:
            print(f"Failed to download. HTTP status: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False
    


#download global solar atlas
def download_global_solar_atlas(country_name: str, data_path: str, measure = 'LTAym_YearlyMonthlyTotals'):
    """
    Downloads and extracts the GIS data (GeoTIFF) ZIP file for the specified country from https://globalsolaratlas.info/download.

    Parameters:
        country_name (str): Name of the country as used in the URL (e.g., "benin").
        save_path (str): Directory where the files will be saved. Defaults to current directory.

    """
    
    # Encode the country name to handle spaces and special characters in the URL
    encoded_country_name = urllib.parse.quote(country_name)
    # Replace spaces with hyphens for the URL format
    country_name_with_hyphens = country_name.replace(" ", "-")

    # Construct the download URL
    # single country
    url = f"https://api.globalsolaratlas.info/download/{encoded_country_name}/{country_name_with_hyphens}_GISdata_{measure}_GlobalSolarAtlas-v2_GEOTIFF.zip"
    timeout = 300 # 5 Minutes
    # or whole world
    if country_name=='world':
        url = 'https://api.globalsolaratlas.info/download/World/World_PVOUT_GISdata_LTAy_AvgDailyTotals_GlobalSolarAtlas-v2_GEOTIFF.zip'
        print("Attention: solar atlas whole world is a very big file! (ca. 350MB)")
        timeout = 900 # 15 Minutes
    print(f"Downloading solar data for '{country_name}' from: {url}")
    
    # Define the full extraction path
    extract_folder = os.path.join(data_path, 'global_solar_wind_atlas', f"{country_name}_solar_atlas")
    os.makedirs(extract_folder, exist_ok=True)
    
    # download  
    try:
        response = requests.get(url, timeout=timeout)  
        if response.status_code == 200:
            print("Download successful. Extracting files...")

            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                zip_ref.extractall(extract_folder)

            print(f"Files extracted to '{extract_folder}'")

            # Assuming the zip contains a single folder (standard GSA structure)
            folder_name = zip_ref.namelist()[0].split('/')[0]  # top-level folder name
            return folder_name
        else:
            print(f"Failed to download data for '{country_name}'. Status code: {response.status_code}")
            
    except requests.Timeout:
        print(f"Download solar atlas data timed out after {timeout} seconds for '{country_name}'.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None



def clean_region_name(region_name: str) -> str:
    """
    Cleans a region name string by:
    - Removing accents and diacritics
    - Removing spaces, periods, and apostrophes

    Parameters:
        region_name (str): The original region name

    Returns:
        str: A sanitized version of the region name
    """
    region_name_clean = unidecode(region_name)
    region_name_clean = region_name_clean.replace(" ", "")
    region_name_clean = region_name_clean.replace(".", "")
    region_name_clean = region_name_clean.replace("'", "")
    return region_name_clean