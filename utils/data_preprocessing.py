import os
import geopandas as gpd
import json
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping
from unidecode import unidecode
from rasterio.warp import calculate_default_transform, reproject, Resampling



def OSM_read_clip_reproject(OSM_folder_path, railways_roads, gdf, target_crs):
    """
    Reads OSM shapefile, clips it to the extent of a GeoPandas DataFrame and reprojects it to a given CRS.

    :param OSM_folder_path: Path to the folder with all OSM shapefiles.
    :railways_roads: string "railways" or "roads" to select which file is used.
    :param gdf: The GeoPandas DataFrame to use for clipping the shapefile.
    :target_crs: The target CRS to reproject the shapefile to (e.g., 'EPSG:3035').
    """
    #read files
    OSM_transport_infra = gpd.read_file(os.path.join(OSM_folder_path, f'gis_osm_{railways_roads}_free_1.shp'))
    #clip files 
    OSM_transport_infra_clipped = gpd.clip(OSM_transport_infra, gdf)
    #reproject and save files
    OSM_transport_infra_clipped.to_crs(epsg=target_crs, inplace=True)
    
    return OSM_transport_infra_clipped





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
            'height': height
        })

        # Create the output file path
        output_path = os.path.join(output_dir, f'{landcover_elevation}_{region_name_clean}_EPSG{target_crs}.tif')


        # Reproject and save the raster
        with rasterio.open(output_path, 'w', **kwargs) as dst:
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
    """Reproject a file to match the shape and projection of existing raster. 
    
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
        dst_kwargs = src.meta.copy()
        dst_kwargs.update({"crs": dst_crs,
                           "transform": dst_transform,
                           "width": dst_width,
                           "height": dst_height,
                           "nodata": 0})
        print("Coregistered to shape:", dst_height,dst_width,'\n Affine',dst_transform)
        # open output
        with rasterio.open(outfile, "w", **dst_kwargs) as dst:
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