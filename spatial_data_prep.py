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
import pygadm
import openeo
import richdem
from utils.data_preprocessing import *
import logging
from pyproj import CRS


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
consider_wind_atlas = config['consider_wind_atlas']
consider_solar_atlas = config['consider_solar_atlas']  
consider_additional_exclusion_polygons = config['additional_exclusion_polygons_folder_name']
consider_additional_exclusion_rasters = config['additional_exclusion_rasters_folder_name']
CRS_manual = config['CRS_manual']  #if None use empty string
consider_protected_areas = config['consider_protected_areas']
wdpa_url = config['wdpa_url']

#----------------------------
############### Define study region ############### use geopackage from gadm.org to inspect in QGIS
region_folder_name = config['region_folder_name']
OSM_folder_name = config['OSM_folder_name'] #usually same as country_code, only needed if OSM is to be considered
DEM_filename = config['DEM_filename']
landcover_filename = config['landcover_filename']

#use GADM boundary
region_name = config['region_name'] #if country is studied, then use country name
country_code = config['country_code']  #3-digit ISO code  #PRT  #Städteregion Aachen in level 2 #Porto in level 1 #Elbe-Elster in level 2 #Zell am See in level 2
gadm_level = config['gadm_level']
#or use custom region
custom_study_area_filename = config['custom_study_area_filename'] #if None use empty string           'Aceh_single.geojson'
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
landcoverRasterPath = os.path.join(data_path, 'landcover', landcover_filename)
demRasterPath = os.path.join(data_path, 'DEM', DEM_filename)
coastlinesFilePath = os.path.join(data_path, 'GOAS', 'goas.gpkg')
protected_areas_folder = os.path.join(data_path, 'protected_areas')
wind_solar_atlas_folder = os.path.join(data_path, 'global_solar_wind_atlas')
if consider_railways == 1 or consider_roads == 1 or consider_airports == 1 or consider_waterbodies == 1:
    OSM_country_path = os.path.join(data_path, 'OSM', OSM_folder_name) 


# Get region name without accents, spaces, apostrophes, or periods for saving files
region_name_clean = clean_region_name(region_name)
# region_name_clean = unidecode(region_name)
# region_name_clean = region_name_clean.replace(" ", "")
# region_name_clean = region_name_clean.replace(".", "")
# region_name_clean = region_name_clean.replace("'", "") 


# Define output directories
output_dir = os.path.join(dirname, 'data', f'{region_folder_name}')
os.makedirs(output_dir, exist_ok=True)

print()
print()
logging.info(f'Prepping {region_name}...')

#get region boundary
if custom_study_area_filename:
    custom_study_area_filepath = os.path.join('Raw_Spatial_Data','custom_study_area', custom_study_area_filename)
    region = gpd.read_file(custom_study_area_filepath)
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
    region = gadm_data.loc[gadm_data[f'NAME_{gadm_level}']==region_name].copy()
    region.set_crs('epsg:4326', inplace=True) #pygadm lib extracts information from the GADM dataset as GeoPandas GeoDataFrame. GADM.org provides files in coordinate reference system is longitude/latitude and the WGS84 datum.
    logging.info('using admin area within country as study area')

region.to_file(os.path.join(output_dir, f'{region_name_clean}_EPSG4326.geojson'), driver='GeoJSON', encoding='utf-8')


# calculate UTM zone based on representative point of country 
representative_point = region.representative_point().iloc[0]
latitude, longitude = representative_point.y, representative_point.x
EPSG = int(32700 - round((45 + latitude) / 90, 0) * 100 + round((183 + longitude) / 6, 0))
#if EPSG was set manual in the beginning then use that one
if CRS_manual:
    local_crs_obj = CRS.from_user_input(CRS_manual)  # Accepts 'EPSG:3035', 'ESRI:102003', WKT, or PROJ strings
    logging.info(f'Using manually set CRS: {local_crs_obj.to_string()}')
else:
    local_crs_obj = CRS.from_user_input(EPSG)
    logging.info(f'Local CRS to be used: {local_crs_obj.to_string()}')
print(local_crs_obj)

# Extract tag for filename, e.g., 'EPSG3035' or 'ESRI102003'
auth = local_crs_obj.to_authority()
local_crs_tag = ''.join(auth) if auth else local_crs_obj.to_string().replace(":", "_")
# Save the CRS object as a pickle file
with open(os.path.join(output_dir, f'{region_name_clean}_local_CRS.pkl'), 'wb') as file:
    pickle.dump(local_crs_obj, file)

# reproject country to defined projected CRS
region.to_crs(local_crs_obj, inplace=True) 
region.to_file(os.path.join(output_dir, f'{region_name_clean}_{local_crs_tag}.geojson'), driver='GeoJSON', encoding='utf-8')
# also have region polygon in equal-area Mollweide projection
region_mollweide = region.to_crs(CRS.from_user_input('ESRI:54009')) 

# set global CRS EPSG:4326
global_crs_obj = CRS.from_user_input('4326')
auth = global_crs_obj.to_authority()
global_crs_tag = ''.join(auth) if auth else global_crs_obj.to_string().replace(":", "_")
# Save the CRS object as a pickle file
with open(os.path.join(output_dir, f'{region_name_clean}_global_CRS.pkl'), 'wb') as file:
    pickle.dump(global_crs_obj, file)

#calculate bounding box with 1000m buffer (region needs to be in projected CRS so meters are the unit)
region_copy = region
region_copy['buffered']=region_copy.buffer(1000)
# Convert buffered region back to EPSC 4326 to get bounding box latitude and longitude 
region_buffered_4326 = region_copy.set_geometry('buffered').to_crs(global_crs_obj)
bounding_box = region_buffered_4326['buffered'].total_bounds 
logging.info(f"Bounding box in EPSG 4326: \nminx: {bounding_box[0]}, miny: {bounding_box[1]}, maxx: {bounding_box[2]}, maxy: {bounding_box[3]}")


#clip global oceans and seas file to study region for coastlines
if consider_coastlines == 1:
    goas_region_filePath = os.path.join(output_dir, f'goas_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(goas_region_filePath): #process data if file not exists in output folder
        try:
            print('processing coastlines')
            coastlines = gpd.read_file(coastlinesFilePath)
            coastlines_region = coastlines.clip(bounding_box)
            if not coastlines_region.empty:
                coastlines_region.to_file(os.path.join(output_dir, f'goas_{region_name_clean}_{global_crs_tag}.gpkg'), driver='GPKG', encoding='utf-8')
                #coastlines_region.to_crs(local_crs_obj, inplace=True)
                #coastlines_region.to_file(goas_region_filePath, driver='GPKG', encoding='utf-8')
            else:
                logging.info('no coastline in study region')
        except:
            logging.warning('error with global oceans and seas (coastlines)')
    else:
        print(f"GOAS data already exists for region")


# Convert region back to EPSC 4326 to trim raster files and clip polygons
region.to_crs(global_crs_obj, inplace=True) 


if consider_railways == 1:
    OSM_railways_filePath = os.path.join(output_dir, f'OSM_railways_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(OSM_railways_filePath): #process data if file not exists in output folder
        print('processing railways')
        OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_railways_free_1.shp'))
        OSM_railways = gpd.clip(OSM_file, region)
        #OSM_railways = geopandas_clip_reproject(OSM_file, region, global_crs_tag)
        # Check if OSM_airports is not empty before saving
        if not OSM_railways.empty:
            OSM_railways.to_file(OSM_railways_filePath, driver='GPKG', encoding='utf-8')
        else:
            logging.info("No railways found in the region. File not saved.")
    else:
        print(f"OSM railways data already exists for region")

if consider_roads == 1:
    OSM_roads_filePath = os.path.join(output_dir, f'OSM_roads_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(OSM_roads_filePath): #process data if file not exists in output folder
        print('processing roads')
        OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_roads_free_1.shp'))
        OSM_roads = gpd.clip(OSM_file, region)
        #OSM_roads = geopandas_clip_reproject(OSM_file, region, EPSG)
        # filter roads. see https://www.geofabrik.de/data/geofabrik-osm-gis-standard-0.7.pdf page19
        OSM_roads_filtered = OSM_roads[OSM_roads['code'].isin([5111, 5112, 5113, 5114, 5115, 5121, 5131, 5132, 5133, 5134, 5135])]
        #OSM_roads_filtered = OSM_roads_clipped[~OSM_roads_clipped['code'].isin([5141])] #keep all roads except with code listed (eg 5141)
        # reset index for clean, zero-based index of filtered data
        OSM_roads_filtered.reset_index(drop=True, inplace=True) 
        # save file
        OSM_roads_filtered.to_file(OSM_roads_filePath, driver='GPKG', encoding='utf-8')
    else:
        print(f"OSM roads data already exists for region")

if consider_airports == 1:
    OSM_airports_filePath = os.path.join(output_dir, f'OSM_airports_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(OSM_airports_filePath): #process data if file not exists in output folder
        print('processing airports')
        OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_transport_a_free_1.shp'))
        OSM_transport = gpd.clip(OSM_file, region) #all transport fclasses from the OSM file 
        #OSM_transport = geopandas_clip_reproject(OSM_file, region, EPSG) #all transport fclasses from the OSM file 
        OSM_airports = OSM_transport[OSM_transport['code'].isin([5651, 5652])] #5651: large airport, 5652: small airport or airfield
        # Check if OSM_airports is not empty before saving
        if not OSM_airports.empty:
            OSM_airports.to_file(OSM_airports_filePath, driver='GPKG', encoding='utf-8')
        else:
            logging.info("No airports found in the region. File not saved.")
    else:
        print(f"OSM airports data already exists for region")

if consider_waterbodies == 1:
    OSM_waterbodies_filePath = os.path.join(output_dir, f'OSM_waterbodies_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(OSM_waterbodies_filePath): #process data if file not exists in output folder
        print('processing waterbodies')
        OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_water_a_free_1.shp'))
        OSM_waterbodies = gpd.clip(OSM_file, region) #all water fclasses from the OSM file 
        #OSM_waterbodies = geopandas_clip_reproject(OSM_file, region, EPSG) #all water fclasses from the OSM file 
        OSM_waterbodies_filtered = OSM_waterbodies[OSM_waterbodies['code'].isin([8200, 8201, 8202])] #8200: unspecified waterbodies like lakes, 8201: reservoir, 8202: river
        # Check if OSM_waterbodies_filtered is not empty before saving
        if not OSM_waterbodies_filtered.empty:
            OSM_waterbodies_filtered.to_file(OSM_waterbodies_filePath, driver='GPKG', encoding='utf-8')
        else:
            logging.info("No waterbodies found in the region. File not saved.")
    else:
        print(f"OSM waterbodies data already exists for region")


if consider_military == 1:
    OSM_military_filePath = os.path.join(output_dir, f'OSM_military_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(OSM_military_filePath): #process data if file not exists in output folder
        print('processing military areas')
        OSM_file = gpd.read_file(os.path.join(OSM_country_path, f'gis_osm_landuse_a_free_1.shp'))
        OSM_landuses_clipped = gpd.clip(OSM_file, region) #all landuses fclasses from the OSM file 
        #OSM_landuses_clipped = geopandas_clip_reproject(OSM_file, region, EPSG) #all landuses fclasses from the OSM file 
        OSM_military = OSM_landuses_clipped[OSM_landuses_clipped['code'].isin([7213])] #7213: military
        # Check if OSM_military is not empty before saving
        if not OSM_military.empty:
            OSM_military.to_file(OSM_military_filePath, driver='GPKG', encoding='utf-8')
        else:
            logging.info("No military areas found in the region. File not saved.")
    else:
        print(f"OSM military data already exists for region")


#clip and reproject additional exclusion polygons
if consider_additional_exclusion_polygons:
    print('processing additional exclusion polygons')
    # Define output directory for additional exclusion polygons
    add_excl_polygons_dir = os.path.join(output_dir,'additional_exclusion_polygons')
    os.makedirs(add_excl_polygons_dir, exist_ok=True)
    source_dir = os.path.join(data_path, 'additional_exclusion_polygons', config['additional_exclusion_polygons_folder_name'])
    counter = 1
    # Loop through all files in the directory
    for filename in os.listdir(source_dir):
        filepath = os.path.join(source_dir, filename)    # Construct the full file path
        # Check if the file is either a GeoJSON or GeoPackage
        if filename.endswith(".geojson") or filename.endswith(".gpkg"):
            gdf = gpd.read_file(filepath) # Read the file into a GeoDataFrame
            gdf_clipped_reprojected = geopandas_clip_reproject(gdf, region, global_crs_obj)
            filename_base = os.path.splitext(filename)[0]  # Remove file extension
            if not gdf_clipped_reprojected.empty:
                gdf_clipped_reprojected.to_file(os.path.join(add_excl_polygons_dir, f'{counter}_{filename_base}_{region_name_clean}_{global_crs_tag}.gpkg'), driver='GPKG')
                counter = counter + 1

#clip and reproject additional rasters
if consider_additional_exclusion_rasters:
    print('processing additional exclusion rasters')
    add_excl_rasters_dir = os.path.join(output_dir,'additional_exclusion_rasters') 
    os.makedirs(add_excl_rasters_dir, exist_ok=True) # Define output directory for additional exclusion rasters
    source_dir = os.path.join(data_path, 'additional_exclusion_rasters', config['additional_exclusion_rasters_folder_name'])
    counter = 1
    # Loop through all files in the directory
    for filename in os.listdir(source_dir):
        filepath = os.path.join(source_dir, filename)    # Construct the full file path
        # Check if the file is either a GeoJSON or GeoPackage
        if filename.endswith(".tif"):
            clip_reproject_raster(filepath, region_name_clean, region_mollweide, f'{counter}', global_crs_obj, 'nearest', 'float64', add_excl_rasters_dir)
            counter = counter + 1



if landcover_source == 'openeo':
    print('processing landcover')
    logging.info('using openeo to get landcover')

    openeo_landcover_filePath = os.path.join(output_dir, f'landcover_openeo_{region_name_clean}_{global_crs_tag}.tif')
    
    if not os.path.exists(openeo_landcover_filePath):
        connection = openeo.connect(url="openeo.dataspace.copernicus.eu").authenticate_oidc()

        if custom_study_area_filename:
            with open(custom_study_area_filepath, 'r', encoding="utf-8") as file: #use region file in EPSG 4326 because openeo default file is in 4326
                aoi = json.load(file) #load polygon for clipping with openeo            
        else:
            with open(os.path.join(output_dir, f'{region_name_clean}_EPSG4326.geojson'), 'r') as file: #use region file in EPSG 4326 because openeo default file is in 4326
                aoi = json.load(file)

        datacube_landcover = connection.load_collection("ESA_WORLDCOVER_10M_2021_V2")
        # clip landcover directly to area of interest 
        landcover = datacube_landcover.mask_polygon(aoi)
        
        # reproject landcover to EPSG 32633 and dont change resolution thereby
        #landcover = masked_landcover.resample_spatial(projection=EPSG, resolution=config['resolution_landcover']) #resolution=0 does not change resolution
        
        result = landcover.save_result('GTiFF')
        job_options = {
            "do_extent_check": False,
            "executor-memory": "5G", #set executer-memory higher to process larger regions; see https://forum.dataspace.copernicus.eu/t/batch-process-error-when-using-certain-region/1454 
            } #see also https://discuss.eodc.eu/t/memory-overhead-problem/424
        # Creating a new batch job at the back-end by sending the datacube information.
        job = result.create_job(job_options=job_options, title=f'landcover_openeo_{region_name_clean}_{global_crs_tag}')
        # Starts the job and waits until it finished to download the result.
        job.start_and_wait()
        job.get_results().download_file(openeo_landcover_filePath) 

        # color openeo landcover file
        try:
            from utils import legends 
            openeo_landcover_colored_filePath = os.path.join(output_dir, f'landcover_openeo_colored_{region_name_clean}_{global_crs_tag}.tif')
            colors_dict_int = getattr(legends, 'colors_dict_esa_worldcover2021_int') #color codes as RGB integers
            with rasterio.open(openeo_landcover_filePath) as landcover:
                band = landcover.read(1, masked=True) # Read the first band, masked=True is masking no data values
                meta = landcover.meta
                colors_dict_int_sorted = dict(sorted(colors_dict_int.items())) #can only write color values as int with rasterio 
                meta.update({'compress': 'DEFLATE', 'photometric': 'palette'}) # You can also try 'DEFLATE', 'JPEG', or 'PACKBITS'
                # save colored version
                with rasterio.open(openeo_landcover_colored_filePath, 'w', **meta) as dst:
                    dst.write(band, indexes=1)
                    dst.write_colormap(1, colors_dict_int_sorted) #be aware of dtype: landcover file is saved with int16, so RGB color values also needs to be an integer?
        except Exception as e:
            print(e)
            logging.warning('Something went wrong with coloring the landcover data')

        # reproject landcover to local CRS
        # grayscale (for DEM calculations below)
        landcover_openeo_local_CRS = os.path.join(output_dir, f'landcover_openeo_{region_name_clean}_{local_crs_tag}.tif')
        reproject_raster(openeo_landcover_filePath, region_name_clean, local_crs_obj, 'nearest', 'uint8', landcover_openeo_local_CRS)
        # colored
        landcover_openeo_local_CRS_colored = os.path.join(output_dir, f'landcover_openeo_colored_{region_name_clean}_{local_crs_tag}.tif')
        reproject_raster(openeo_landcover_colored_filePath, region_name_clean, local_crs_obj, 'nearest', 'uint8', landcover_openeo_local_CRS_colored)

        # save pixel size and unique land cover codes
        landcover_information(landcover_openeo_local_CRS, output_dir, region_name, local_crs_tag)


    elif os.path.exists(openeo_landcover_filePath):
        logging.info('Landcover not downloaded from openeo. There is already a clipped landcover file in the output folder.')

    processed_landcover_filePath = openeo_landcover_filePath

if landcover_source == 'file':
    print('processing landcover')
    local_landcover_filePath = os.path.join(output_dir, f'landcover_local_{region_name_clean}_{global_crs_tag}.tif')
    if not os.path.exists(local_landcover_filePath): #process data if file not exists in output folder
        print('processing landcover')
        logging.info('using local file to get landcover')
        clip_reproject_raster(landcoverRasterPath, region_name_clean, region, 'landcover_local', local_crs_obj, 'nearest', 'int16', output_dir)
        landcover_information(local_landcover_filePath, output_dir, region_name, local_crs_tag)

    else:
        print(f"Local landcover already processed to region.")
    
    processed_landcover_filePath = os.path.join(output_dir, f'landcover_local_{region_name_clean}_{local_crs_tag}.tif')


print('processing DEM') #block comment: SHIFT+ALT+A, multiple line comment: STRG+#
try:
    clip_reproject_raster(demRasterPath, region_name_clean, region, 'DEM', local_crs_obj, 'nearest', 'int16', output_dir)
    dem_4326_Path = os.path.join(output_dir, f'DEM_{region_name_clean}_EPSG4326.tif')
    #reproject and match resolution of DEM to landcover data (co-registration)
    dem_localCRS_Path=os.path.join(output_dir, f'DEM_{region_name_clean}_{local_crs_tag}.tif')
    dem_resampled_Path=os.path.join(output_dir, f'DEM_{region_name_clean}_{local_crs_tag}_resampled.tif') 
    co_register(dem_localCRS_Path, processed_landcover_filePath, 'nearest', dem_resampled_Path, dtype='int16')

    #slope and aspect map
    # Define output directories
    richdem_helper_dir = os.path.join(output_dir, 'derived_from_DEM')
    os.makedirs(richdem_helper_dir, exist_ok=True)

    #create slope map (https://www.earthdatascience.org/tutorials/get-slope-aspect-from-digital-elevation-model/)
    #save in local CRS
    dem_file = richdem.LoadGDAL(dem_localCRS_Path)
    slope = richdem.TerrainAttribute(dem_file, attrib='slope_degrees')
    slopeFilePathLocalCRS = os.path.join(richdem_helper_dir, f'slope_{region_name_clean}_{local_crs_tag}.tif')
    save_richdem_file(slope, dem_localCRS_Path, slopeFilePathLocalCRS)
    slope_co_registered_FilePath = os.path.join(richdem_helper_dir, f'slope_{region_name_clean}_{local_crs_tag}_resampled.tif')
    co_register(slopeFilePathLocalCRS, processed_landcover_filePath, 'nearest', slope_co_registered_FilePath, dtype='int16')
    #save in 4326: slope cannot be calculated from EPSG4326 because units get confused (https://github.com/r-barnes/richdem/issues/34)
    slopeFilePath4326 = os.path.join(richdem_helper_dir, f'slope_{region_name_clean}_EPSG4326.tif')
    reproject_raster(slopeFilePathLocalCRS, region_name_clean, 4326, 'nearest', 'int16', slopeFilePath4326)

    #create aspect map (https://www.earthdatascience.org/tutorials/get-slope-aspect-from-digital-elevation-model/)
    #save in local CRS
    dem_file = richdem.LoadGDAL(dem_localCRS_Path)
    aspect = richdem.TerrainAttribute(dem_file, attrib='aspect')
    aspectFilePathLocalCRS = os.path.join(richdem_helper_dir, f'aspect_{region_name_clean}_{local_crs_tag}.tif')
    save_richdem_file(aspect, dem_localCRS_Path, aspectFilePathLocalCRS)
    aspect_co_registered_FilePath = os.path.join(richdem_helper_dir, f'aspect_{region_name_clean}_{local_crs_tag}_resampled.tif')
    co_register(aspectFilePathLocalCRS, processed_landcover_filePath, 'nearest', aspect_co_registered_FilePath, dtype='int16')
    #save in 4326: not sure if aspect is calculated correctly in EPSG4326 because units might get confused (https://github.com/r-barnes/richdem/issues/34)
    aspectFilePath4326 = os.path.join(richdem_helper_dir, f'aspect_{region_name_clean}_EPSG4326.tif')
    reproject_raster(aspectFilePathLocalCRS, region_name_clean, 4326, 'nearest', 'int16', aspectFilePath4326)


    # create map showing pixels with slope bigger X and aspect between Y and Z (north facing with slope where you would not build PV)
    # local CRS co-registered
    #create_north_facing_pixels(slope_co_registered_FilePath, aspect_co_registered_FilePath, region_name_clean, richdem_helper_dir, X, Y, Z)
    create_north_facing_pixels(slopeFilePath4326, aspectFilePath4326, region_name_clean, richdem_helper_dir, X, Y, Z)

except Exception as e:
    print(e)
    logging.warning('Something went wrong with DEM')


#protected areas
#download WDPA (WDPA is country specific, so the protected areas for a custom polygon spanning over multiple countries cannot be obtained)
if consider_protected_areas == 'WDPA' or consider_protected_areas == 'file':

    protected_areas_filePath = os.path.join(output_dir, f'protected_areas_{consider_protected_areas}_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(protected_areas_filePath): #process data if file not exists in output folder

        print('processing protected areas')
        if consider_protected_areas == 'WDPA':    
            logging.info('using WDPA')
            if find_folder(protected_areas_folder, string_in_name=country_code) is None:
                # if there is no folder already existing then create one and download the WDPA
                WDPA_country_folder = os.path.join(protected_areas_folder, f'WDPA_{country_code}')
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
                WDPA_country_folder = os.path.join(protected_areas_folder, f'WDPA_{country_code}')
            
            raw_protected_areas_filepath = os.path.join(WDPA_country_folder, f'{country_code}_WDPA.gpkg')

        elif consider_protected_areas == 'file':
            logging.info("using local file for protected areas")
            protected_areas_filename=config['protected_areas_filename']
            raw_protected_areas_filepath = os.path.join(protected_areas_folder, protected_areas_filename)

        #clip to study region (WDPA or local file)
        protected_areas_file = gpd.read_file(raw_protected_areas_filepath)
        protected_areas_file = geopandas_clip_reproject(protected_areas_file, region, global_crs_obj)
        if not protected_areas_file.empty:
            protected_areas_file.to_file(protected_areas_filePath, driver='GPKG', encoding='utf-8')
        else:
            logging.info("No protected areas found in the region. File not saved.")
    
    else:
        print(f"Protected areas file already exists for region.")


#global wind atlas
if consider_wind_atlas == 1:
    wind_raster_filePath = os.path.join(wind_solar_atlas_folder, f'{country_code}_wind_speed_100.tif')

    if not os.path.exists(wind_raster_filePath):
        print('processing global wind atlas')
        download_global_wind_atlas(country_code=country_code, height=100, data_path=data_path) #global wind atlas apparently uses 3 letter ISO code
    else:
        print(f"Global wind atlas data already downloaded: {wind_raster_filePath}")
        
    #clip and reproject to local CRS (also saves file which is only clipped but not reprojected)
    clip_reproject_raster(wind_raster_filePath, region_name_clean, region, 'wind', local_crs_obj, 'nearest', 'float32', output_dir)
    #co-register raster to land cover
    wind_raster_clipped_reprojected_filePath = os.path.join(output_dir, f'wind_{region_name_clean}_{local_crs_tag}.tif')
    wind_raster_co_registered_filePath = os.path.join(output_dir, f'wind_{region_name_clean}_{local_crs_tag}_resampled.tif')
    co_register(wind_raster_clipped_reprojected_filePath, processed_landcover_filePath, 'nearest', wind_raster_co_registered_filePath, dtype='float32')



#global solar atlas (no check whether file already exists)
if consider_solar_atlas == 1:
    country_name_solar_atlas = config['country_name_solar_atlas']
    solar_atlas_folder_path = os.path.join(wind_solar_atlas_folder, f'{country_name_solar_atlas}_solar_atlas')

    if not os.path.exists(solar_atlas_folder_path):
        print('processing global solar atlas')
        solar_atlas_measure = config['measure']  
        solar_atlas_folder_name = download_global_solar_atlas(country_name=country_name_solar_atlas, data_path=data_path, measure = solar_atlas_measure)
    else:
        print(f"Global solar atlas data already downloaded: {solar_atlas_folder_path}")
    
    solar_raster_filePath = os.path.join(wind_solar_atlas_folder, solar_atlas_folder_path, os.listdir(solar_atlas_folder_path)[0], 'PVOUT.tif')
    #clip and reproject to local CRS (also saves file which is only clipped but not reprojected)
    clip_reproject_raster(solar_raster_filePath, region_name_clean, region, 'solar', local_crs_obj, 'nearest', 'float32', output_dir)
    #co-register raster to land cover
    solar_raster_clipped_reprojected_filePath = os.path.join(output_dir, f'solar_{region_name_clean}_{local_crs_tag}.tif')
    solar_raster_co_registered_filePath = os.path.join(output_dir, f'solar_{region_name_clean}_{local_crs_tag}_resampled.tif')
    co_register(solar_raster_clipped_reprojected_filePath, processed_landcover_filePath, 'nearest', solar_raster_co_registered_filePath, dtype='float32')



print("Done!")

elapsed = time.time() - start_time
logging.info(f'elapsed seconds: {round(elapsed)}')
print(elapsed)
