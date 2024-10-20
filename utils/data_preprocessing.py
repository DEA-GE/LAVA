import os
import geopandas as gpd
import json
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping
from unidecode import unidecode
from rasterio.warp import calculate_default_transform, reproject, Resampling

import zipfile
import requests
import io
import fiona

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
    logging.warning('no existing WDPA country folder found')

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
        compress='lzw',
        nodata=richdem_file.no_data) 
    #save raster file
    with rasterio.open(outFilePath, 'w', **profile) as dst:
        dst.write(richdem_file.astype(rasterio.int16), 1)  


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





def clip_reproject_raster(input_raster_path, region_name_clean, gdf, landcover_elevation, target_crs, resampling_method, output_dir):
    """
        Reads a TIFF raster, clips it to the extent of a GeoPandas DataFrame, reprojects it to a given CRS considerung the set resampling method,
        and saves the clipped raster in a specified output folder.
    
        :param input_raster_path: Path to the input TIFF raster file.
        :param region_name_clean: in main script cleaned region name
        :param gdf: The GeoPandas DataFrame to use for clipping the raster.
        :param landcover_elevation: string with "landcover" or "elevation". 
        :param target_crs: The target CRS to reproject the raster to (e.g., 'EPSG:3035').
        :param resampling_method: resampling method to be used (string)
        :param output_dir: output directory (defined in main script)
        """
    
    resampling_options = {
        'nearest': Resampling.nearest,
        'bilinear': Resampling.bilinear,
        'cubic': Resampling.cubic
    }

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
        with rasterio.open(os.path.join(output_dir, f'{landcover_elevation}_{region_name_clean}_{ori_raster_crs}.tif'), 'w', **out_meta) as dest:
            dest.write(out_image)

    # reproject landcover raster to local UTM CRS
    with rasterio.open(os.path.join(output_dir, f'{landcover_elevation}_{region_name_clean}_{ori_raster_crs}.tif')) as src:
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
        output_path = os.path.join(output_dir, f'{landcover_elevation}_{region_name_clean}_EPSG{target_crs}.tif')


        # Reproject and save the raster
        with rasterio.open(output_path, 'w', **kwargs, compress='lzw') as dst:
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




def reproj_match(infile, match, resampling_method, outfile): #source: https://pygis.io/docs/e_raster_resample.html
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
            dtype=rasterio.int16,
            count=1,
            nodata=-9999,
            compress='lzw') 
        

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