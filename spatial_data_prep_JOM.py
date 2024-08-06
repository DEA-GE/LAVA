# -*- coding: utf-8 -*-
"""
Created on Wed Oct 18 14:30:10 2023
Changed on Wed Jul 24

@author: Alycia Leonard, University of Oxford
@author: Jonas Meier, Danish Energy Agency (added some more code)

spatial_data_prep.py

This script prepares raw spatial data for land exclusion in GLAES and hexagon preparation in SPIDER.
The raw inputs should be downloaded to /Raw_Spatial_Data before execution.
The outputs are saved in /Inputs_Glaes/data and /Inputs_Spider/data respectively.

compare boundaries between different data sources: https://www.geoboundaries.org/visualize.html?country=DEU&mainSource=OSM-Boundaries&comparisonSource=geoBoundaries+%28Open%29&mainLevel=2&comparisonLevel=2
This script uses administrative boundries from GADM.org via pygadm
"""

import time
import os
import geopandas as gpd
import json
import pickle
import rasterio
import pygadm
from rasterio.mask import mask
from shapely.geometry import mapping
from unidecode import unidecode
from rasterio.warp import calculate_default_transform, reproject, Resampling

#https://www.earthenv.org/topography

#-------data config-------
only_mainland = 0
GOAS = 0 
consider_OSM_railways = 1
consider_OSM_roads = 0
EPSG_manual = ''
#----------------------------
############### Define study region ############### use geopackage from gadm.org to inspect in QGIS
country_code='DEU' #    #PRT  #Städteregion Aachen in level 2 #Porto in level 1 #Elbe-Elster in level 2
OSM_folder_name = 'BerlinBrandenburg' #usually same as country_code
gadm_level=2
region_name='Elbe-Elster'  #needs a name (if country is studied, then use country name)
##################################################


# Record the starting time
start_time = time.time()

# Get paths to data files
dirname = os.path.dirname(__file__)
data_path = os.path.join(dirname, 'Raw_Spatial_Data')
landcoverRasterPath = os.path.join(data_path, "PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif")
demRasterPath = os.path.join(data_path, 'gebco','gebco_cutout.tif')
OSM_country_path = os.path.join(data_path, 'OSM', OSM_folder_name) 



# Get region name without accents, spaces, apostrophes, or periods for saving files
region_name_clean = unidecode(region_name)
region_name_clean = region_name_clean.replace(" ", "")
region_name_clean = region_name_clean.replace(".", "")
region_name_clean = region_name_clean.replace("'", "")


# Define output directories
glaes_output_dir = os.path.join(dirname, 'data', f'{region_name_clean}')
os.makedirs(glaes_output_dir, exist_ok=True)


print("Prepping " + region_name + "...")


#get region boundary
if gadm_level==0:
    gadm_data = pygadm.Items(admin=country_code)
    region = gadm_data
else:
    gadm_data = pygadm.Items(admin=country_code, content_level=gadm_level)
    region = gadm_data.loc[gadm_data[f'NAME_{gadm_level}']==region_name]
region.set_crs('epsg:4326', inplace=True) #pygadm lib extracts information from the GADM dataset as GeoPandas GeoDataFrame. GADM.org provides files in coordinate reference system is longitude/latitude and the WGS84 datum.
print(f'region geojson loaded CRS: {region.crs}')
region.to_file(os.path.join(glaes_output_dir, f'{region_name_clean}_4326.geojson'), driver='GeoJSON', encoding='utf-8')


# calculate UTM zone based on representative point of country
representative_point = region.representative_point().iloc[0]
latitude, longitude = representative_point.y, representative_point.x
EPSG = int(32700 - round((45 + latitude) / 90, 0) * 100 + round((183 + longitude) / 6, 0))
#if EPSG was set manuel in the beginning then use that one
if EPSG_manual:
    EPSG=int(EPSG_manual)


print(f'CRS to be used: {EPSG}')
with open(os.path.join(glaes_output_dir, f'{region_name_clean}_EPSG.pkl'), 'wb') as file:
    pickle.dump(EPSG, file)

# reproject country to defined CRS
region.to_crs(epsg=EPSG, inplace=True) 
print(f'region projected to defined CRS: {region.crs}')
region.to_file(os.path.join(glaes_output_dir, f'{region_name_clean}_{EPSG}.geojson'), driver='GeoJSON', encoding='utf-8')

# Convert region back to EPSC 4326 to trim landcover
region.to_crs(epsg=4326, inplace=True)


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
    

if consider_OSM_railways == 1:
    print('processing railways')
    OSM_railways = OSM_read_clip_reproject(OSM_country_path, 'railways', region, EPSG)
    OSM_railways.to_file(os.path.join(glaes_output_dir, f'OSM_railways_{region_name_clean}_{EPSG}.geojson'), driver='GeoJSON', encoding='utf-8')

if consider_OSM_roads == 1:
    print('processing roads')
    OSM_roads = OSM_read_clip_reproject(OSM_country_path, 'roads', region, EPSG)
    #filter roads. see https://www.geofabrik.de/data/geofabrik-osm-gis-standard-0.7.pdf page19
    OSM_roads_filtered = OSM_roads[OSM_roads['code'].isin([5111, 5112, 5113, 5114, 5115, 5121, 5122, 5125, 5131, 5132, 5133, 5134, 5135])]
    #OSM_roads_clipped_filtered = OSM_roads_clipped[~OSM_roads_clipped['code'].isin([5141])] #keep all roads except with code listed (eg 5141)
    #reset index for clean, zero-based index of filtered data
    OSM_roads_filtered.reset_index(drop=True, inplace=True)
    #save file
    OSM_roads_filtered.to_file(os.path.join(glaes_output_dir, f'OSM_roads_{region_name_clean}_{EPSG}.geojson'), driver='GeoJSON', encoding='utf-8')



def clip_reproject_raster(input_raster_path, gdf, landcover_elevation, target_crs, resampling_method):
    """
        Reads a TIFF raster, clips it to the extent of a GeoPandas DataFrame, reprojects it to a given CRS considerung the set resampling method,
        and saves the clipped raster in a specified output folder.
    
        :param input_raster_path: Path to the input TIFF raster file.
        :param gdf: The GeoPandas DataFrame to use for clipping the raster.
        :param landcover_elevation: string with "landcover" or "elevation".
        :param target_crs: The target CRS to reproject the raster to (e.g., 'EPSG:3035').
        :param resampling_method: resampling method to be used (string)
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
        with rasterio.open(os.path.join(glaes_output_dir, f'{landcover_elevation}_{region_name_clean}_{ori_raster_crs}.tif'), 'w', **out_meta) as dest:
            dest.write(out_image)

    # reproject landcover raster to local UTM CRS
    with rasterio.open(os.path.join(glaes_output_dir, f'{landcover_elevation}_{region_name_clean}_{ori_raster_crs}.tif')) as src:
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
        output_path = os.path.join(glaes_output_dir, f'{landcover_elevation}_{region_name_clean}_EPSG{target_crs}.tif')


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



print('landcover')
clip_reproject_raster(landcoverRasterPath, region, 'landcover', EPSG, 'nearest')

try:
    print('DEM')
    clip_reproject_raster(demRasterPath, region, 'DEM', EPSG, 'bilinear')
except:
    print('Input shapes do not overlap raster. DEM raster for study region is not correct')




def reproj_match(infile, match, outfile): #source: https://pygis.io/docs/e_raster_resample.html
    """Reproject a file to match the shape and projection of existing raster. 
    
    Parameters
    ----------
    infile : (string) path to input file to reproject
    match : (string) path to raster with desired shape and projection 
    outfile : (string) path to output file tif
    """
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
                    resampling=Resampling.nearest)

infile=os.path.join(glaes_output_dir, f'DEM_{region_name_clean}_EPSG{EPSG}.tif')
match=os.path.join(glaes_output_dir, f'landcover_{region_name_clean}_EPSG{EPSG}.tif')
outfile=os.path.join(glaes_output_dir, f'DEM_{region_name_clean}_EPSG{EPSG}_resampled.tif')
reproj_match(infile, match, outfile)


print("Done!")

