import os
import geopandas as gpd
from pyproj import CRS

import logging



def process_single_local_osm_layer(config,
                             layer_name,
                             input_shp_filename, 
                             clip_region=None, 
                             region_name='', 
                             output_dir='',
                             target_crs=None,
                             OSM_data_path=''):
    """
    Generic function to process and filter OSM layers based on configuration.
    Processes only if config['consider_<layer_name>'] == 1.

    Reads fclass list from config['fclass'][layer_name], if present.

    Parameters:
        config (dict): Configuration dictionary.
        layer_name (str): Name of the layer, e.g., 'roads', 'airports'.
        input_shp_filename (str): Input shapefile name for this layer.
        clip_region (GeoDataFrame or geometry): Region to clip data to.
        region_name (str): Clean name of the region, used in output filename.
        output_dir (str): Directory to save processed output.
        target_crs (str or pyproj.CRS, optional): Output CRS for reprojection (e.g., 'EPSG:3857').
        OSM_data_path (str): Directory containing the raw OSM shapefiles.
    """
    if config.get(f'{layer_name}') != 1:
        return

    # Read fclass list from config if available
    layer_fclasses = config.get('fclass', {}).get(layer_name)

    # Determine CRS tag for filename
    crs_tag = 'EPSG4326'  # default CRS string if no reprojection
    if target_crs:
        crs = CRS.from_user_input(target_crs)
        authority = crs.to_authority()
        crs_tag = f"{authority[0]}{authority[1]}" if authority else 'customCRS'

    output_filename = f'OSM_{layer_name}_{region_name}_{crs_tag}.gpkg'
    output_filepath = os.path.join(output_dir, output_filename)

    if os.path.exists(output_filepath):
        print(f"OSM {layer_name} data already exists for region")
        return

    print(f"Processing {layer_name}...")
    input_filepath = os.path.join(OSM_data_path, input_shp_filename)

    try:
        OSM_file = gpd.read_file(input_filepath)
        clipped_data = gpd.clip(OSM_file, clip_region)

        if layer_fclasses is not None:
            filtered_data = clipped_data[clipped_data['fclass'].isin(layer_fclasses)]
        else:
            filtered_data = clipped_data

        if target_crs:
            filtered_data = filtered_data.to_crs(crs)

        if not filtered_data.empty:
            filtered_data.to_file(output_filepath, driver='GPKG', encoding='utf-8')
        else:
            logging.info(f"No {layer_name} found in the region. File not saved.")
    except Exception as e:
        logging.error(f"Error processing {layer_name}: {e}")





def process_all_local_osm_layer(config, region, region_name_clean, output_dir, OSM_data_path, target_crs=None):

    process_single_local_osm_layer(
    config,
    layer_name='railways',
    input_shp_filename='gis_osm_railways_free_1.shp',
    clip_region=region,
    region_name=region_name_clean,
    output_dir=output_dir,
    target_crs=target_crs,
    OSM_data_path = OSM_data_path
    )

    process_single_local_osm_layer(
    config,
    layer_name='roads',
    input_shp_filename='gis_osm_roads_free_1.shp',
    clip_region=region,
    region_name=region_name_clean,
    output_dir=output_dir,
    target_crs=target_crs,
    OSM_data_path = OSM_data_path
    )
    
    process_single_local_osm_layer(
    config,
    layer_name='airports',
    input_shp_filename='gis_osm_transport_a_free_1.shp',
    clip_region=region,
    region_name=region_name_clean,
    output_dir=output_dir,
    target_crs=target_crs,
    OSM_data_path = OSM_data_path
    )

    process_single_local_osm_layer(
    config,
    layer_name='waterbodies',
    input_shp_filename='gis_osm_water_a_free_1.shp',
    clip_region=region,
    region_name=region_name_clean,
    output_dir=output_dir,
    target_crs=target_crs,
    OSM_data_path = OSM_data_path
    )

    process_single_local_osm_layer(
    config,
    layer_name='military',
    input_shp_filename='gis_osm_landuse_a_free_1.shp',
    clip_region=region,
    region_name=region_name_clean,
    output_dir=output_dir,
    target_crs=target_crs,
    OSM_data_path = OSM_data_path
    )