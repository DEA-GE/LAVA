"""
@author: Matteo D'Andrea
@date: 23-05-2025

@description:
Script to fetch OpenStreetMap (OSM) features using the Overpass API and save them into 
separate GeoPackage (.gpkg) files per region and feature. Each geometry type is saved 
in its own file, named as <region>_<feature>_<geometry>.gpkg.

The script also tracks unsupported geometry types and saves a JSON summary per feature/region.
"""

import os, time, json
from typing import Optional
from shapely.geometry import shape
import geopandas as gpd
from OSMPythonTools.nominatim import Nominatim
from OSMPythonTools.overpass import overpassQueryBuilder, Overpass
from utils.data_preprocessing import rel_path

import logging
from OSMPythonTools import logger as osm_logger

# Only log ERROR or CRITICAL; ignore WARNING and below
osm_logger.setLevel(logging.ERROR)

def osm_to_gpkg(
    region_name: str,
    polygon: list,
    feature_key: str,
    features_dict: dict,
    output_dir: str = "OSM_Infrastructure",
    EPSG: Optional[int] = 4326,
    timeout: Optional[int] = 200,
    relevant_geometries_override: Optional[dict] = None,
):
    """
    Fetch OSM infrastructure data for a given region and feature key and save to individual GeoPackages.

    Args:
        region_name (str): Name of the region to query (e.g., "Inner Mongolia").
        feature_key (str): Key in the features_dict (e.g., "substation_way").
        features_dict (dict): A dictionary mapping keys to [category, category_element, element_type].
        EPSG (str): EPSG code for the coordinate reference system (default is "EPSG:4326").
        output_dir (str): Directory where the GeoPackage files will be saved.
        timeout (int): Optional timeout for the Overpass query (default is 200 seconds).
        relevant_geometries_override (dict): Optional dict mapping feature_key to list of geometries.

    Returns:
        dict: A dictionary of unsupported geometry types and their counts.
    """
    if feature_key not in features_dict:
        raise ValueError(f"'{feature_key}' not found in features_dict.")

    category, category_element, element_type = features_dict[feature_key]

    if category_element is None or category_element == "":
    # just require the key to exist
        selector = [f'"{category}"']
    elif isinstance(category_element, (list, tuple)):
    # build a regex that matches any of the values in the list
    # e.g. ["primary", "secondary"] → ^(primary|secondary)$
        joined = "|".join(category_element)
        selector = [f'"{category}"~"^({joined})$"']
    else:
    # single value → exact match
        selector = [f'"{category}"="{category_element}"']

    start_time = time.time()
    os.makedirs(output_dir, exist_ok=True)

    
    nominatim = Nominatim()  # Geocode region to retrieve area identifier
    location = nominatim.query(region_name)  # Query Nominatim for the region
    if not location:
        print(f"Region '{region_name}' not found.")
        return {}
    
    area_id = location.areaId()
    #print(f"Fetching data for: {region_name} ")
    #print(f"Fetching data for: {location.displayName()} (Area ID: {area_id})")
    

    # some spatial elements like airports or waterbodies can be represented as both ways and relations
    element_types = element_type if isinstance(element_type, list) else [element_type]

    overpass = Overpass()

    query = overpassQueryBuilder(
        polygon=polygon,
        elementType=element_types,
        selector=selector,
        includeGeometry=True
        ) # Build Overpass query
    result = overpass.query(query, timeout=timeout) # Execute query with timeout

    if not result.elements():
        print(f"No elements found for {feature_key} in {region_name}")
        return {}
    

    # Expected geometries for each supported feature
    default_geometries = {
        "substations": ["Polygon"],
        "plants": ["Polygon"],
        "generators": ["Point"],
        "transmission_lines": ["LineString"],
        "roads": ["LineString"],
        "railways": ["LineString"],
        "airports": ["Polygon"],
        "waterbodies": ["Polygon"],
        "military": ["Polygon"],
    }

    relevant_geometries = (
        relevant_geometries_override[feature_key]
        if relevant_geometries_override and feature_key in relevant_geometries_override
        else default_geometries.get(feature_key, ["Point", "LineString", "Polygon"])
    )

    geoms_dict = {g: [] for g in relevant_geometries}  # Store features by geometry type
    unsupported_counts = {}  # Track unsupported geometry types

    for element in result.elements():  # Iterate over all returned OSM elements
        geometry = element.geometry()
        geometry_type = geometry.get('type')
        if geometry_type in geoms_dict:
            try:
                props = {
                    'Name': element.tag('name') or 'Unknown',
                    'id': str(element.id()),
                    'Type': element.type()
                }
                geom = shape(geometry)  # Convert GeoJSON-like dict to Shapely geometry
                geoms_dict[geometry_type].append({**props, 'geometry': geom})
            except Exception as e:
                print(f"Error parsing element {element.id()}: {e}")
        else:
            unsupported_counts[geometry_type] = unsupported_counts.get(geometry_type, 0) + 1

    # Save each geometry type to its own GeoPackage file
    for geom_type, features in geoms_dict.items():
        if not features:
            continue
        gdf = gpd.GeoDataFrame(features, crs=f"EPSG:{EPSG}")  # Create GeoDataFrame for this geometry
        gpkg_path = os.path.join(
            output_dir, f"overpass_{feature_key}.gpkg"
        )
        # Write layer using UTF-8 to ensure cross-platform compatibility
        gdf.to_file(gpkg_path, driver="GPKG", encoding="utf-8")
        print(f"  ✔ Saved {len(gdf)} {geom_type}(s) to {rel_path(gpkg_path)}")

    #print(f"✅ Finished '{feature_key}' for {region_name} in {time.time() - start_time:.2f} seconds.")
    return unsupported_counts



if __name__ == "__main__":
    import yaml
    from utils.data_preprocessing import rel_path

    config_path = os.path.join("configs", "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join("configs", "config_template.yaml")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    osm_features_config = config.get("osm_features_config", {})

    polygon = [[48.3, 16.3], [48.3, 16.5], [48.2, 16.6], [48.1, 16.5], [48.1, 16.3]]
    region = "Example Region"
    output_base = "data"

    region_dir = os.path.join(output_base, region.replace(" ", "_"), "OSM_Infrastructure")
    os.makedirs(region_dir, exist_ok=True)
    unsupported_summary = {}

    for feature_key in osm_features_config:
        gpkg_path = os.path.join(region_dir, f"{feature_key}.gpkg")
        if os.path.exists(gpkg_path):
            print(f"⏭️  Skipping '{feature_key}' for {region}: '{rel_path(gpkg_path)}' already exists.")
            continue

        print(f"\n🔍 Processing {feature_key} in {region}")
        unsupported = osm_to_gpkg(
            region_name=region,
            polygon=polygon,
            feature_key=feature_key,
            features_dict=osm_features_config,
            EPSG=4326,
            output_dir=region_dir,
        )

        if unsupported:
            unsupported_summary[f"{region}_{feature_key}"] = unsupported

    summary_path = os.path.join(region_dir, "unsupported_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(unsupported_summary, f, indent=2, ensure_ascii=False)

    print(f"📄 Unsupported geometry summary saved to {rel_path(summary_path)}")

