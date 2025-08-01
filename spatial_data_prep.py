# -*- coding: utf-8 -*-
"""
@author: Jonas Meier

TBA
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
import xdem
import logging
import argparse
from pyproj import CRS
from utils.data_preprocessing import *
from utils.local_OSM_shp_files import *
from utils.fetch_OSM import osm_to_gpkg
from utils.simplify import generate_overpass_polygon
from utils.proximity_calc import generate_distance_raster

# Record the starting time
start_time = time.time()

# Create handlers
file_handler = logging.FileHandler("data-prep.log", mode='w')
file_handler.setLevel(logging.DEBUG)  # file can record everything

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)  # terminal only shows WARNING and above

logging.basicConfig(
    handlers=[file_handler, stream_handler],
    level=logging.INFO,  # minimum level for logger; handlers override this
    format="%(levelname)s:%(name)s:%(message)s"
    ) #source: https://stackoverflow.com/questions/13733552/logger-configuration-to-log-to-file-and-print-to-stdout

# Suppress specific noisy INFO logs from openeo
#logging.getLogger("openeo.config").setLevel(logging.WARNING)
#logging.getLogger("openeo.rest.connection").setLevel(logging.WARNING)


with open("configs/config.yaml", "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

#-------data config------- 
consider_coastlines = config['coastlines']
consider_railways = config['railways']
consider_roads = config['roads']
consider_airports = config['airports']
consider_waterbodies = config['waterbodies']
consider_military = config['military']
consider_wind_atlas = config['wind_atlas']
consider_solar_atlas = config['solar_atlas']
compute_substation_proximity = config.get('compute_substation_proximity', 0)
compute_road_proximity = config.get('compute_road_proximity', 0)
compute_terrain_ruggedness = config.get('compute_terrain_ruggedness', 0)
consider_additional_exclusion_polygons = config['additional_exclusion_polygons_folder_name']
consider_additional_exclusion_rasters = config['additional_exclusion_rasters_folder_name']
CRS_manual = config['CRS_manual']  #if None use empty string
consider_protected_areas = config['protected_areas_source']
wdpa_url = config['wdpa_url']
OSM_source = config['OSM_source']  #either 'geofabrik' or 'overpass'

#----------------------------
############### Define study region ############### use geopackage from gadm.org to inspect in QGIS
region_folder_name = config['region_folder_name']
OSM_folder_name = config['OSM_folder_name'] #usually same as country_code, only needed if OSM is to be considered
DEM_filename = config['DEM_filename']

#use GADM boundary
region_name = config['region_name'] #if country is studied, then use country name
country_code = config['country_code']  #3-digit ISO code  #PRT  #Städteregion Aachen in level 2 #Porto in level 1 #Elbe-Elster in level 2 #Zell am See in level 2
gadm_level = config['gadm_level']
#or use custom region
custom_study_area_filename = config.get('custom_study_area_filename', None)

#Initialize parser for command line arguments and define arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default=region_name, help="region name")
parser.add_argument("--region_folder_name", default=region_folder_name, help="region folder name")
parser.add_argument("--method",default="manual", help="method to run the script, e.g., snakemake or manual")
args = parser.parse_args()

# If running via Snakemake, use the region name and folder name from command line arguments
if args.method == "snakemake":
    region_name = args.region
    region_folder_name = args.region_folder_name
    print(f"Running via snakemake - measures: region={region_name}, region_folder_name={region_folder_name}")
else:
    print(f"Running manually - measures: region={region_name}, region_folder_name={region_folder_name}")

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
demRasterPath = os.path.join(data_path, 'DEM', DEM_filename)
coastlinesFilePath = os.path.join(data_path, 'GOAS', 'goas.gpkg')
protected_areas_folder = os.path.join(data_path, 'protected_areas')
wind_solar_atlas_folder = os.path.join(data_path, 'global_solar_wind_atlas')
if OSM_source == 'geofabrik':
    OSM_data_path = os.path.join(data_path, 'OSM', OSM_folder_name)



# Get region name without accents, spaces, apostrophes, or periods for saving files
region_name_clean = clean_region_name(region_name)

# Define output directories
output_dir = os.path.join(dirname, 'data', f'{region_folder_name}')
os.makedirs(output_dir, exist_ok=True)

# Set up logging
logging.info(f'\nPrepping {region_name}...')

#get region boundary
if custom_study_area_filename:
    #check if dynamic filename is used
    if "{region_name}" in custom_study_area_filename:
        custom_study_area_filename = custom_study_area_filename.format(region_name=region_name)
    print(f"\nUsing custom study area filename: {custom_study_area_filename}")
    custom_study_area_filepath = os.path.join('Raw_Spatial_Data','custom_study_area', custom_study_area_filename)
    region = gpd.read_file(custom_study_area_filepath).dissolve() # Dissolve to ensure it's a single polygon
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

# simplify polygon of study area (openeo can only handle polygons up to a certain size)
try:
    region["geometry"] = region["geometry"].simplify(config["study_area"]["tolerance"], preserve_topology=True)
except Exception as e:
    logging.warning(f"Polygon of study could not be simplified: {e}")
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
    print('\nprocessing coastlines')
    goas_region_filePath = os.path.join(output_dir, f'goas_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(goas_region_filePath): #process data if file not exists in output folder
        try:
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


# OSM data
if OSM_source == 'geofabrik':
    OSM_output_dir = os.path.join(output_dir, 'OSM_Infrastructure')
    os.makedirs(OSM_output_dir, exist_ok=True) 

    process_all_local_osm_layer(config, region, region_name_clean, OSM_output_dir, OSM_data_path, target_crs=None)

elif OSM_source == 'overpass':

    print('\nprocessing OSM data')

    # Define OSM features to fetch
    # Load all possible OSM features directly from config
    osm_features_config = config.get("osm_features_config", {})
    
    print('Prepare polygon for overpass query')
    #Use the GDAM polygon to fetch OSM data, first simplify the polygon to avoid too many vertices
    polygon = generate_overpass_polygon(region)
    
    # Filter based on config flags
    selected_osm_features_dict = {
        key: val for key, val in osm_features_config.items()
        if config.get(f"{key}", 0)}
    
    # Define output base directory and prepare unsupported log
    OSM_output_dir = os.path.join(output_dir, "OSM_Infrastructure")
    unsupported_summary = {}
    unsupported_geometries_summary_path = os.path.join(OSM_output_dir, "unsupported_geometries_summary.json")

    # Loop through regions and features
    for feature_key in selected_osm_features_dict:

        # skip if we’ve already got this GeoPackage
        gpkg_path = os.path.join(OSM_output_dir, f"overpass_{feature_key}.gpkg")

        if os.path.exists(gpkg_path) and not config['force_osm_download']:
            print(f"⏭️  Skipping '{feature_key}' for {region_name_clean}: '{rel_path(gpkg_path)}' already exists.")

        else:
            print(f"\n🔍 Processing {feature_key} in {region_name_clean}")
            #the function returns a dictionary with unsupported geometries to check if the features dictionary is correct
            unsupported = osm_to_gpkg(
                region_name=region_name_clean,
                polygon=polygon,
                feature_key=feature_key,
                features_dict=selected_osm_features_dict,
                timeout=500,
                # Optional override for geometry types per feature::
                # relevant_geometries_override={"substation": ["node"]},
                output_dir=OSM_output_dir
            )

            # Save unsupported counts if any were found
            if unsupported:         
                unsupported_summary[f"{region_name_clean}_{feature_key}"] = unsupported

        # Save summary of unsupported geometries to JSON file
        # the unsupported_summary dictionary contains the counts of unsupported geometries for each feature. 
        # Unsupportd geometries are geometries not expected for the feature, e.g. a "node" for a transmission line. 
        # Usually there are few unsupported geometries. 
        
        with open(unsupported_geometries_summary_path, "w", encoding="utf-8") as f:
            json.dump(unsupported_summary, f, indent=2, ensure_ascii=False)

    print(f"\nUnsupported geometry summary saved to {rel_path(OSM_output_dir)}")

# create proximity raster for substations if data exists and calculation is enabled
if compute_substation_proximity:
    print('\ncomputing proximity distance for substations')
    substation_filename = OSM_source + "_substations.gpkg" #OSM substations are saved in a file with the name of the OSM source
    substations_path = os.path.join(OSM_output_dir, substation_filename)
    if os.path.exists(substations_path):
        substations_gdf = gpd.read_file(substations_path)
        if not substations_gdf.empty:
            proximity_dir = os.path.join(output_dir, "proximity")
            os.makedirs(proximity_dir, exist_ok=True)
            proximity_out = os.path.join(proximity_dir, "substation_distance.tif")
            if os.path.exists(proximity_out):
                print(f"Proximity raster already exists at {rel_path(proximity_out)}. Skipping generation.")
            else:
                generate_distance_raster(
                    shapefile_path=substations_path,
                    region_gdf=region,
                    output_path=proximity_out,
                )
        else:
            print("Proximity distance cannot be calculated as the substation is not provided.")
    else:
        print("Proximity distance cannot be calculated as the substation is not provided.")

# create proximity raster for roads if data exists and calculation is enabled
if compute_road_proximity:
    print('\ncomputing proximity distance for roads')
    roads_filename=  OSM_source + "_roads.gpkg" #OSM roads are saved in a file with the name of the OSM source
    roads_path = os.path.join(OSM_output_dir, roads_filename)
    if os.path.exists(roads_path):
        roads_gdf = gpd.read_file(roads_path) 
        if not roads_gdf.empty:
            proximity_dir = os.path.join(output_dir, "proximity")
            os.makedirs(proximity_dir, exist_ok=True)
            proximity_out = os.path.join(proximity_dir, "road_distance.tif")
            if os.path.exists(proximity_out):
                print(f"Proximity raster already exists at {rel_path(proximity_out)}. Skipping generation.")
            else:
                generate_distance_raster(
                    shapefile_path=roads_path,
                    region_gdf=region,
                    output_path=proximity_out,
                )
        else:
            print("Proximity distance cannot be calculated as the roads are not provided.")
    else:
        print("Proximity distance cannot be calculated as the roads are not provided.")

#clip and reproject additional exclusion polygons
if consider_additional_exclusion_polygons:
    print('\nprocessing additional exclusion polygons')
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
    print('\nprocessing additional exclusion rasters')
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



if config['landcover_source'] == 'openeo':
    print('\nprocessing landcover')
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
        
        # change resolution if wanted (projection also possible, see documentation)
        if config['resolution_landcover']:
            landcover = landcover.resample_spatial(resolution=config['resolution_landcover']) #resolution=0 does not change resolution
        
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
        landcover_information(landcover_openeo_local_CRS, output_dir, region_name_clean, local_crs_tag)


    elif os.path.exists(openeo_landcover_filePath):
        logging.info('Landcover not downloaded from openeo. There is already a clipped landcover file in the output folder.')

    processed_landcover_filePath = openeo_landcover_filePath

if config['landcover_source'] == 'file':
    print('processing landcover')
    try:
        landcover_filename = config['landcover_filename']
        landcoverRasterPath = os.path.join(data_path, 'landcover', landcover_filename)
        local_landcover_filePath = os.path.join(output_dir, f'landcover_local_{region_name_clean}_{global_crs_tag}.tif')
        if not os.path.exists(local_landcover_filePath): #process data if file not exists in output folder
            print('processing landcover')
            logging.info('using local file to get landcover')
            clip_reproject_raster(landcoverRasterPath, region_name_clean, region, 'landcover_local', local_crs_obj, 'nearest', 'int16', output_dir)
            landcover_information(local_landcover_filePath, output_dir, region_name_clean, local_crs_tag)
        else:
            print(f"Local landcover already processed to region.")
        processed_landcover_filePath = os.path.join(output_dir, f'landcover_local_{region_name_clean}_{local_crs_tag}.tif')
    except Exception as e:
        logging.error(f"Exception occurred: {e}")
        print(f"Exception occurred: {e}")


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

    #------------- Terrain Ruggedness Index -----------------
    if compute_terrain_ruggedness:
        print('\nprocessing Terrain Ruggedness Index')
        tri_FilePath = os.path.join(output_dir, f'TerrainRuggednessIndex_{region_name_clean}_EPSG{EPSG}.tif')
        if os.path.exists(tri_FilePath):
            print(f"Terrain Ruggedness Index already exists at {rel_path(tri_FilePath)}. Skipping calculation.")
        else:
            dem = xdem.DEM(dem_localCRS_Path)
            tri = dem.terrain_ruggedness_index(window_size=9)
            tri_array = tri.data
            tri.save(tri_FilePath)
    

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
    print('\nprocessing protected areas')
    protected_areas_filePath = os.path.join(output_dir, f'protected_areas_{consider_protected_areas}_{region_name_clean}_{global_crs_tag}.gpkg')
    if not os.path.exists(protected_areas_filePath): #process data if file not exists in output folder

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
    print('\nprocessing global wind atlas')
    wind_raster_filePath = os.path.join(wind_solar_atlas_folder, f'{country_code}_wind_speed_100.tif')

    if not os.path.exists(wind_raster_filePath):
        download_global_wind_atlas(country_code=country_code, height=100, data_path=data_path) #global wind atlas apparently uses 3 letter ISO code
    else:
        print(f"Global wind atlas data already downloaded: {rel_path(wind_raster_filePath)}")
        
    #clip and reproject to local CRS (also saves file which is only clipped but not reprojected)
    clip_reproject_raster(wind_raster_filePath, region_name_clean, region, 'wind', local_crs_obj, 'nearest', 'float32', output_dir)
    #co-register raster to land cover
    wind_raster_clipped_reprojected_filePath = os.path.join(output_dir, f'wind_{region_name_clean}_{local_crs_tag}.tif')
    wind_raster_co_registered_filePath = os.path.join(output_dir, f'wind_{region_name_clean}_{local_crs_tag}_resampled.tif')
    co_register(wind_raster_clipped_reprojected_filePath, processed_landcover_filePath, 'nearest', wind_raster_co_registered_filePath, dtype='float32')



#global solar atlas (no check whether file already exists)
if consider_solar_atlas == 1:
    print('\nprocessing global solar atlas')
    country_name_solar_atlas = config['country_name_solar_atlas']
    solar_atlas_folder_path = os.path.join(wind_solar_atlas_folder, f'{country_name_solar_atlas}_solar_atlas')

    if not os.path.exists(solar_atlas_folder_path):
        solar_atlas_measure = config['measure']  
        solar_atlas_folder_name = download_global_solar_atlas(country_name=country_name_solar_atlas, data_path=data_path, measure = solar_atlas_measure)
    else:
        print(f"Global solar atlas data already downloaded: {rel_path(solar_atlas_folder_path)}")
    
    solar_raster_filePath = os.path.join(wind_solar_atlas_folder, solar_atlas_folder_path, os.listdir(solar_atlas_folder_path)[0], 'GHI.tif')
    #clip and reproject to local CRS (also saves file which is only clipped but not reprojected)
    clip_reproject_raster(solar_raster_filePath, region_name_clean, region, 'solar', local_crs_obj, 'nearest', 'float32', output_dir)
    #co-register raster to land cover
    solar_raster_clipped_reprojected_filePath = os.path.join(output_dir, f'solar_{region_name_clean}_{local_crs_tag}.tif')
    solar_raster_co_registered_filePath = os.path.join(output_dir, f'solar_{region_name_clean}_{local_crs_tag}_resampled.tif')
    co_register(solar_raster_clipped_reprojected_filePath, processed_landcover_filePath, 'nearest', solar_raster_co_registered_filePath, dtype='float32')



print("\nDone!")

elapsed = time.time() - start_time
logging.info(f'elapsed seconds: {round(elapsed)}')
print(elapsed)
