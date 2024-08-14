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
from utils.data_preprocessing import *

#https://www.earthenv.org/topography

#-------data config------- 
consider_OSM_railways = 0
consider_OSM_roads = 0
EPSG_manual = '' #if None use empty string
custom_polygon_filename = 'Aceh_single.geojson' #if None use empty string           'Aceh_single.geojson'
#----------------------------
############### Define study region ############### use geopackage from gadm.org to inspect in QGIS
country_code='AUT' #    #PRT  #Städteregion Aachen in level 2 #Porto in level 1 #Elbe-Elster in level 2
OSM_folder_name = 'BerlinBrandenburg' #usually same as country_code, only needed if OSM railways or roads are considered
gadm_level=2
region_name='Aceh'  #needs a name (if country is studied, then use country name)
##################################################


# Record the starting time
start_time = time.time()

# Get paths to data files
dirname = os.path.dirname(__file__)
data_path = os.path.join(dirname, 'Raw_Spatial_Data')
landcoverRasterPath = os.path.join(data_path, "PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif")
demRasterPath = os.path.join(data_path, 'gebco','gebco_cutout.tif')
if consider_OSM_railways == 1 or consider_OSM_roads == 1:
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
if custom_polygon_filename:
    custom_polygon_filepath = os.path.join('Raw_Spatial_Data','custom_polygon', custom_polygon_filename)
    region = gpd.read_file(custom_polygon_filepath)
elif gadm_level==0:
    gadm_data = pygadm.Items(admin=country_code)
    region = gadm_data
    region.set_crs('epsg:4326', inplace=True) #pygadm lib extracts information from the GADM dataset as GeoPandas GeoDataFrame. GADM.org provides files in coordinate reference system is longitude/latitude and the WGS84 datum.
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


print('landcover')
clip_reproject_raster(landcoverRasterPath, region_name_clean, region, 'landcover', EPSG, 'nearest', glaes_output_dir)


print('DEM')
try:
    clip_reproject_raster(demRasterPath, region_name_clean, region, 'DEM', EPSG, 'bilinear', glaes_output_dir)

    #reproject and match resolution of DEM to landcover data
    infile=os.path.join(glaes_output_dir, f'DEM_{region_name_clean}_EPSG{EPSG}.tif')
    match=os.path.join(glaes_output_dir, f'landcover_{region_name_clean}_EPSG{EPSG}.tif')
    outfile=os.path.join(glaes_output_dir, f'DEM_{region_name_clean}_EPSG{EPSG}_resampled.tif')
    reproj_match(infile, match, 'bilinear', outfile)

except:
    print('Input shapes do not overlap raster. DEM raster for study region is not correct')


print("Done!")

