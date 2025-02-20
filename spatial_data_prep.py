# -*- coding: utf-8 -*-
"""
created August 2024

@author: Jonas Meier


This script prepares raw spatial data for land exclusion in GLAES or ATLITE.
The raw inputs should be downloaded to /Raw_Spatial_Data before execution. For landcover the openEO API can be used to download data automatically.
The outputs are saved in /data.

compare boundaries between different data sources: https://www.geoboundaries.org/visualize.html?country=DEU&mainSource=OSM-Boundaries&comparisonSource=geoBoundaries+%28Open%29&mainLevel=2&comparisonLevel=2
This script uses administrative boundries from GADM.org via pygadm
"""

import time
import os
import geopandas as gpd
import json
import pickle
import yaml
import rasterio
import numpy as np
import pygadm
import openeo
from rasterio.mask import mask
from shapely.geometry import mapping
from unidecode import unidecode
from rasterio.warp import calculate_default_transform, reproject, Resampling
import richdem
from utils.data_preprocessing import *
import logging

# Record the starting time
start_time = time.time()

logging.basicConfig(handlers=[
        logging.FileHandler("data-prep.log", mode='w'),
        logging.StreamHandler()
        ], level=logging.INFO) #source: https://stackoverflow.com/questions/13733552/logger-configuration-to-log-to-file-and-print-to-stdout

with open("configs/config.yaml", "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

#-------data config------- 
landcover_source = config['landcover_source']
consider_coastlines = config['consider_coastlines']
consider_railways = config['consider_railways']
consider_roads = config['consider_roads']
consider_airports = config['consider_airports']
consider_waterbodies = config['consider_waterbodies']
consider_military = config['consider_military']  
consider_additional_exclusion_polygons = config['consider_additional_exclusion_polygons']
EPSG_manual = config['EPSG_manual']  #if None use empty string
consider_WDPA = config['consider_WDPA']
wdpa_url = config['wdpa_url']

#----------------------------
############### Define study region ############### use geopackage from gadm.org to inspect in QGIS
region_folder_name = config['region_folder_name']
region_name = config['region_name'] #always needed (if country is studied, then use country name)
OSM_folder_name = config['OSM_folder_name'] #usually same as country_code, only needed if OSM is to be considered
DEM_filename = config['DEM_filename']
landcover_filename = config['landcover_filename']

#use GADM boundary
region_name = config['region_name'] #if country is studied, then use country name
country_code = config['country_code']  #3-digit ISO code  #PRT  #Städteregion Aachen in level 2 #Porto in level 1 #Elbe-Elster in level 2 #Zell am See in level 2 - to be adapted for china
gadm_level = config['gadm_level']
#or use custom region
custom_polygon_filename = config['custom_polygon_filename'] #if None use empty string           'Aceh_single.geojson'
##################################################
#north facing pixels
X = config['X']
Y = config['Y']
Z = config['Z']


# Record the starting time
start_time = time.time()

# Get paths to data files or folders
dirname = os.path.dirname(__file__)
data_path = os.path.join(dirname, 'Raw_Spatial_Data')
landcoverRasterPath = os.path.join(data_path, landcover_filename)
demRasterPath = os.path.join(data_path, 'DEM', DEM_filename)
coastlinesFilePath = os.path.join(data_path, 'GOAS', 'goas.gpkg')
wdpa_folder = os.path.join(data_path, 'WDPA')
if consider_railways == 1 or consider_roads == 1 or consider_airports == 1 or consider_waterbodies == 1:
    OSM_country_path = os.path.join(data_path, 'OSM', OSM_folder_name) 


# Get region name without accents, spaces, apostrophes, or periods for saving files
region_name_clean = unidecode(region_name)
region_name_clean = region_name_clean.replace(" ", "")
region_name_clean = region_name_clean.replace(".", "")
region_name_clean = region_name_clean.replace("'", "") 


# Define output directories
output_dir = os.path.join(dirname, 'data', f'{region_folder_name}')
os.makedirs(output_dir, exist_ok=True)


logging.info(f'Prepping {region_name}...')

#get region boundary
if custom_polygon_filename:
    custom_polygon_filepath = os.path.join('Raw_Spatial_Data','custom_polygon', custom_polygon_filename)
    region = gpd.read_file(custom_polygon_filepath)
    if region.crs != 4326:
        logging.warning('crs of custom polygon file for study region is not in EPSG 4326')
    logging.info('using custom polygon for study area')
elif gadm_level==0:
    gadm_data = pygadm.Items(admin=country_code)
    region = gadm_data
    region.set_crs('epsg:4326', inplace=True) #pygadm lib extracts information from the GADM dataset as GeoPandas GeoDataFrame. GADM.org provides files in coordinate reference system is longitude/latitude and the WGS84 datum.
    logging.info('using whole country as study area')
else:
    gadm_data = pygadm.Items(admin=country_code, content_level=gadm_level)
    region = gadm_data.loc[gadm_data[f'NAME_{gadm_level}']==region_name]
    region.set_crs('epsg:4326', inplace=True) #pygadm lib extracts information from the GADM dataset as GeoPandas GeoDataFrame. GADM.org provides files in coordinate reference system is longitude/latitude and the WGS84 datum.
    logging.info('using admin area within country as study area')

region.to_file(os.path.join(output_dir, f'{region_name_clean}_4326.geojson'), driver='GeoJSON', encoding='utf-8')


# calculate UTM zone based on representative point of country 
representative_point = region.representative_point().iloc[0]
latitude, longitude = representative_point.y, representative_point.x
EPSG = int(32700 - round((45 + latitude) / 90, 0) * 100 + round((183 + longitude) / 6, 0))
#if EPSG was set manual in the beginning then use that one
if EPSG_manual:
    EPSG=int(EPSG_manual)
    logging.info(f'using manual set CRS with EPSG code {EPSG}')
else:
    logging.info(f'local CRS to be used: {EPSG}')

with open(os.path.join(output_dir, f'{region_name_clean}_EPSG.pkl'), 'wb') as file:
    pickle.dump(EPSG, file)

# reproject country to defined projected CRS
region.to_crs(epsg=EPSG, inplace=True) 
region.to_file(os.path.join(output_dir, f'{region_name_clean}_{EPSG}.geojson'), driver='GeoJSON', encoding='utf-8')


#calculate bounding box with 1000m buffer (region needs to be in projected CRS so meters are the unit)
region_copy = region
region_copy['buffered']=region_copy.buffer(1000)
# Convert buffered region back to EPSC 4326 to get bounding box latitude and longitude 
region_buffered_4326 = region_copy.set_geometry('buffered').to_crs(epsg=4326)
bounding_box = region_buffered_4326['buffered'].total_bounds 
logging.info(f"Bounding box in EPSG 4326: \nminx: {bounding_box[0]}, miny: {bounding_box[1]}, maxx: {bounding_box[2]}, maxy: {bounding_box[3]}")


#clip global oceans and seas file to study region for coastlines
if consider_coastlines == 1:
    try:
        print('processing coastlines')
        coastlines = gpd.read_file(coastlinesFilePath)
        coastlines_region = coastlines.clip(bounding_box)
        if not coastlines_region.empty:
            coastlines_region.to_file(os.path.join(output_dir, f'goas_{region_name_clean}_4326.gpkg'), driver='GPKG', encoding='utf-8')
            coastlines_region.to_crs(epsg=EPSG, inplace=True)
            coastlines_region.to_file(os.path.join(output_dir, f'goas_{region_name_clean}_{EPSG}.gpkg'), driver='GPKG', encoding='utf-8')
        else:
            logging.info('no coastline in study region')
    except:
        logging.warning('error with global oceans and seas (coastlines)')


# Convert region back to EPSC 4326 to trim raster files and clip polygons
region.to_crs(epsg=4326, inplace=True) 


if consider_railways == 1:
    print('processing railways')
    OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_railways_free_1.shp'))
    OSM_railways = geopandas_clip_reproject(OSM_file, region, EPSG)
    # Check if OSM_airports is not empty before saving
    if not OSM_railways.empty:
        OSM_railways.to_file(os.path.join(output_dir, f'OSM_railways_{region_name_clean}_{EPSG}.gpkg'), driver='GPKG', encoding='utf-8')
    else:
        logging.info("No railways found in the region. File not saved.")

if consider_roads == 1:
    print('processing roads')
    OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_roads_free_1.shp'))
    OSM_roads = geopandas_clip_reproject(OSM_file, region, EPSG)
    #filter roads. see https://www.geofabrik.de/data/geofabrik-osm-gis-standard-0.7.pdf page19
    OSM_roads_filtered = OSM_roads[OSM_roads['code'].isin([5111, 5112, 5113, 5114, 5115, 5121, 5131, 5132, 5133, 5134, 5135])]
    #OSM_roads_clipped_filtered = OSM_roads_clipped[~OSM_roads_clipped['code'].isin([5141])] #keep all roads except with code listed (eg 5141)
    #reset index for clean, zero-based index of filtered data
    OSM_roads_filtered.reset_index(drop=True, inplace=True)
    #save file
    OSM_roads_filtered.to_file(os.path.join(output_dir, f'OSM_roads_{region_name_clean}_{EPSG}.gpkg'), driver='GPKG', encoding='utf-8')

if consider_airports == 1:
    print('processing airports')
    OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_transport_a_free_1.shp'))
    OSM_transport = geopandas_clip_reproject(OSM_file, region, EPSG) #all transport fclasses from the OSM file 
    OSM_airports = OSM_transport[OSM_transport['code'].isin([5651, 5652])] #5651: large airport, 5652: small airport or airfield
    # Check if OSM_airports is not empty before saving
    if not OSM_airports.empty:
        OSM_airports.to_file(os.path.join(output_dir, f'OSM_airports_{region_name_clean}_{EPSG}.gpkg'), driver='GPKG', encoding='utf-8')
    else:
        logging.info("No airports found in the region. File not saved.")

if consider_waterbodies == 1:
    print('processing waterbodies')
    OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_water_a_free_1.shp'))
    OSM_waterbodies = geopandas_clip_reproject(OSM_file, region, EPSG) #all transport fclasses from the OSM file 
    OSM_waterbodies_filtered = OSM_waterbodies[OSM_waterbodies['code'].isin([8200, 8201, 8202])] #8200: unspecified waterbodies like lakes, 8201: reservoir, 8202: river
    # Check if OSM_waterbodies_filtered is not empty before saving
    if not OSM_waterbodies_filtered.empty:
        OSM_waterbodies_filtered.to_file(os.path.join(output_dir, f'OSM_waterbodies_{region_name_clean}_{EPSG}.gpkg'), driver='GPKG', encoding='utf-8')
    else:
        logging.info("No waterbodies found in the region. File not saved.")


if consider_military == 1:
    print('processing military areas')
    OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_landuse_a_free_1.shp'))
    OSM_military = geopandas_clip_reproject(OSM_file, region, EPSG)
    # Check if OSM_military is not empty before saving
    if not OSM_military.empty:
        OSM_military.to_file(os.path.join(output_dir, f'OSM_military_{region_name_clean}_{EPSG}.gpkg'), driver='GPKG', encoding='utf-8')
    else:
        logging.info("No military areas found in the region. File not saved.")


#clip and reproject additional exclusion polygons
if consider_additional_exclusion_polygons == 1:
    print('processing additional exclusion polygons')
    # Define output directory for additional exclusion polygons
    add_excl_polygons_dir = os.path.join(output_dir,'additional_exclusion_polygons')
    os.makedirs(add_excl_polygons_dir, exist_ok=True)
    count = 1
    # Loop through all files in the directory
    for filename in os.listdir(os.path.join(data_path, 'additional_exclusion_polygons')):
        filepath = os.path.join(data_path, 'additional_exclusion_polygons', filename)    # Construct the full file path

        # Check if the file is either a GeoJSON or GeoPackage
        if filename.endswith(".geojson") or filename.endswith(".gpkg"):
            gdf = gpd.read_file(filepath) # Read the file into a GeoDataFrame
            gdf_clipped_reprojected = geopandas_clip_reproject(gdf, region, EPSG)
            if not gdf_clipped_reprojected.empty:
                gdf_clipped_reprojected.to_file(os.path.join(add_excl_polygons_dir, f'additional_exclusion_{count}_{region_name_clean}_{EPSG}.gpkg'), driver='GPKG')
                count = count + 1



print('processing landcover')
if landcover_source == 'openeo':
    logging.info('using openeo to get landcover')

    connection = openeo.connect(url="openeo.dataspace.copernicus.eu").authenticate_oidc()

    output_path = os.path.join(output_dir, f'landcover_{region_name_clean}_EPSG{EPSG}.tif')

    if custom_polygon_filename:
        with open(custom_polygon_filepath, 'r',encoding='utf8') as file: #use region file in EPSG 4326 because openeo default file is in 4326
            aoi = json.load(file) #load polygon for clipping with openeo            
    else:
        with open(os.path.join(output_dir, f'{region_name_clean}_4326.geojson'), 'r',encoding='utf8') as file: #use region file in EPSG 4326 because openeo default file is in 4326
            aoi = json.load(file)

    datacube_landcover = connection.load_collection("ESA_WORLDCOVER_10M_2021_V2")
    #clip landcover directly to area of interest 
    masked_landcover = datacube_landcover.mask_polygon(aoi)
    #reproject landcover to EPSG 32633 and dont change resolution thereby
    landcover = masked_landcover.resample_spatial(projection=EPSG, resolution=0) #resolution=0 does not change resolution
    
    result = landcover.save_result('GTiFF')
    job_options = {
        "do_extent_check": False,
        "executor-memory": "5G", #set executer-memory higher to process larger regions; see https://forum.dataspace.copernicus.eu/t/batch-process-error-when-using-certain-region/1454 
        } #see also https://discuss.eodc.eu/t/memory-overhead-problem/424
    # Creating a new batch job at the back-end by sending the datacube information.
    job = result.create_job(job_options=job_options, title=f'landcover_{region_name_clean}_{EPSG}')
    # Starts the job and waits until it finished to download the result.
    job.start_and_wait()
    job.get_results().download_file(output_path) 

if landcover_source == 'file':
    logging.info('using local file to get landcover')
    clip_reproject_raster(landcoverRasterPath, region_name_clean, region, 'landcover', EPSG, 'nearest', 'int16', output_dir)


print('processing DEM') #block comment: SHIFT+ALT+A, multiple line comment: STRG+#
try:
    clip_reproject_raster(demRasterPath, region_name_clean, region, 'DEM', EPSG, 'nearest', 'int16', output_dir)
    dem_4326_Path = os.path.join(output_dir, f'DEM_{region_name_clean}_EPSG4326.tif')

    #reproject and match resolution of DEM to landcover data (co-registration)
    dem_localCRS_Path=os.path.join(output_dir, f'DEM_{region_name_clean}_EPSG{EPSG}.tif')
    matchPath=os.path.join(output_dir, f'landcover_{region_name_clean}_EPSG{EPSG}.tif')
    dem_resampled_Path=os.path.join(output_dir, f'DEM_{region_name_clean}_EPSG{EPSG}_resampled.tif') 
    co_register(dem_localCRS_Path, matchPath, 'nearest', dem_resampled_Path)

    #slope and aspect map
    # Define output directories
    richdem_helper_dir = os.path.join(output_dir, 'derived_from_DEM')
    os.makedirs(richdem_helper_dir, exist_ok=True)

    #create slope map (https://www.earthdatascience.org/tutorials/get-slope-aspect-from-digital-elevation-model/)
    #save in local CRS
    dem_file = richdem.LoadGDAL(dem_localCRS_Path)
    slope = richdem.TerrainAttribute(dem_file, attrib='slope_degrees')
    slopeFilePathLocalCRS = os.path.join(richdem_helper_dir, f'slope_{region_name_clean}_EPSG{EPSG}.tif')
    save_richdem_file(slope, dem_localCRS_Path, slopeFilePathLocalCRS)
    slope_co_registered_FilePath = os.path.join(richdem_helper_dir, f'slope_{region_name_clean}_EPSG{EPSG}_resampled.tif')
    co_register(slopeFilePathLocalCRS, matchPath, 'nearest', slope_co_registered_FilePath)
    #save in 4326: slope cannot be calculated from EPSG4326 because units get confused (https://github.com/r-barnes/richdem/issues/34)
    slopeFilePath4326 = os.path.join(richdem_helper_dir, f'slope_{region_name_clean}_EPSG4326.tif')
    reproject_raster(slopeFilePathLocalCRS, region_name_clean, 4326, 'nearest', slopeFilePath4326)

    #create aspect map (https://www.earthdatascience.org/tutorials/get-slope-aspect-from-digital-elevation-model/)
    #save in local CRS
    dem_file = richdem.LoadGDAL(dem_localCRS_Path)
    aspect = richdem.TerrainAttribute(dem_file, attrib='aspect')
    aspectFilePathLocalCRS = os.path.join(richdem_helper_dir, f'aspect_{region_name_clean}_EPSG{EPSG}.tif')
    save_richdem_file(aspect, dem_localCRS_Path, aspectFilePathLocalCRS)
    aspect_co_registered_FilePath = os.path.join(richdem_helper_dir, f'aspect_{region_name_clean}_EPSG{EPSG}_resampled.tif')
    co_register(aspectFilePathLocalCRS, matchPath, 'nearest', aspect_co_registered_FilePath)
    #save in 4326: not sure if aspect is calculated correctly in EPSG4326 because units might get confused (https://github.com/r-barnes/richdem/issues/34)
    aspectFilePath4326 = os.path.join(richdem_helper_dir, f'aspect_{region_name_clean}_EPSG4326.tif')
    reproject_raster(aspectFilePathLocalCRS, region_name_clean, 4326, 'nearest', aspectFilePath4326)


    #create map showing pixels with slope bigger X and aspect between Y and Z (north facing with slope where you would not build PV)
    #local CRS co-registered
    create_north_facing_pixels(slope_co_registered_FilePath, aspect_co_registered_FilePath, region_name_clean, richdem_helper_dir, X, Y, Z)
    #EPSG4326
    create_north_facing_pixels(slopeFilePath4326, aspectFilePath4326, region_name_clean, richdem_helper_dir, X, Y, Z)

except Exception as e:
    print(e)
    logging.warning('Something went wrong with DEM')


#download WDPA (WDPA is country specific, so the protected areas for a custom polygon spanning over multiple countries cannot be obtained)
if consider_WDPA == 1:
    print('processing protected areas')
    if find_folder(wdpa_folder, string_in_name=country_code) is None:
        # if there is no folder already existing then create one and download the WDPA
        WDPA_country_folder = os.path.join(wdpa_folder, f'WDPA_{country_code}')
        os.makedirs(WDPA_country_folder, exist_ok=True)
        if country_code in wdpa_url: #check if provided URL matches with country of study region
            #donwload and convert to geopackage
            download_unpack_zip(wdpa_url, WDPA_country_folder)
            gdb_folder = find_folder(WDPA_country_folder, file_ending='.gdb') #gdb means geodatabase
            convert_gdb_to_gpkg(gdb_folder, WDPA_country_folder, f'{country_code}_WDPA.gpkg')
        else:
            logging.warning('No WDPA downloaded. URL and country code do not match')
    else:
        logging.info('folder with protected areas of country of study region already exists')
        WDPA_country_folder = os.path.join(wdpa_folder, f'WDPA_{country_code}')

    #clip WDPA to study region
    wdpaFilePath = os.path.join(WDPA_country_folder, f'{country_code}_WDPA.gpkg')
    wdpa_file = gpd.read_file(wdpaFilePath)
    wdpa_file = geopandas_clip_reproject(wdpa_file, region, EPSG)
    if not wdpa_file.empty:
        wdpa_file.to_file(os.path.join(output_dir, f'protected_areas_{region_name_clean}_{EPSG}.gpkg'), driver='GPKG', encoding='utf-8')
    else:
        logging.info("No protected areas found in the region. File not saved.")



print("Done!")

elapsed = time.time() - start_time
logging.info(f'elapsed seconds: {round(elapsed)}')
print(elapsed)
