"""
Script to fetch OpenStreetMap (OSM) features using the Overpass API and save them into a 
single GeoPackage (.gpkg) file per region. Each feature is stored in a separate layer by 
geometry type (Point, LineString, Polygon).

The script also tracks any unsupported geometry types encountered during fetching (i.e., 
geometries not included in the expected types) and saves a JSON summary of their counts 
per region and feature.

Main features:
- Uses OSMPythonTools for region and data querying.
- Uses GeoPandas to write outputs into .gpkg format with layer-per-feature-per-geometry.
- Stores a summary of unsupported geometries in `unsupported_geometries_summary.json`.

Usage:
- Customize `regions` and `features_dict` as needed.
- Run the script in a Python environment with required libraries installed.
"""


import os, time, json
from typing import Optional
from shapely.geometry import shape
import geopandas as gpd
from OSMPythonTools.nominatim import Nominatim
from OSMPythonTools.overpass import overpassQueryBuilder, Overpass

def fetch_osm_feature_to_gpkg(
    region_name: str,
    feature_key: str,
    features_dict: dict,
    output_dir: str = "Raw_Spatial_Data/OSM_Infrastructure",
    relevant_geometries_override: Optional[dict] = None,
):
    """
    Fetch OSM infrastructure data for a given region and feature key and save to a GeoPackage.

    Args:
        region_name (str): Name of the region to query (e.g., "Inner Mongolia").
        feature_key (str): Key in the features_dict (e.g., "substation_way").
        features_dict (dict): A dictionary mapping keys to [category, category_element, element_type].
        output_dir (str): Directory where the GeoPackage will be saved.
        relevant_geometries_override (dict): Optional dict mapping feature_key to list of geometries.

    Returns:
        dict: A dictionary of unsupported geometry types and their counts.
    """
    # Check that feature_key exists
    if feature_key not in features_dict:
        raise ValueError(f"'{feature_key}' not found in features_dict.")

    # Get the OSM tag setup (e.g., 'power', 'substation', 'way')
    category, category_element, element_type = features_dict[feature_key]
    selector = [f'"{category}"="{category_element}"']

    # Start timer and ensure output folder exists
    start_time = time.time()
    os.makedirs(output_dir, exist_ok=True)

    # Get the region’s OSM area ID using Nominatim
    nominatim = Nominatim()
    location = nominatim.query(region_name)
    if not location:
        print(f"Region '{region_name}' not found.")
        return {}

    area_id = location.areaId()
    print(f"Fetching data for: {location.displayName()} (Area ID: {area_id})")

    # Build and run Overpass query
    overpass = Overpass()
    query = overpassQueryBuilder(
        area=area_id,
        elementType=[element_type],
        selector=selector,
        includeGeometry=True
    )
    result = overpass.query(query, timeout=200)

    # Skip if no data returned
    if not result.elements():
        print(f"No elements found for {feature_key} in {region_name}")
        return {}

    # Default mapping of expected geometries
    default_geometries = {
        "substation_way": ["Polygon"],
        "generator_node": ["Point"],
        "road_way": ["LineString"],
        "railway_way": ["LineString"],
        "airport_way": ["Polygon"],
        "waterbody_way": ["Polygon"],
        "military_area": ["Polygon"],
    }

    # Use overrides if given
    relevant_geometries = (
        relevant_geometries_override[feature_key]
        if relevant_geometries_override and feature_key in relevant_geometries_override
        else default_geometries.get(feature_key, ["Point", "LineString", "Polygon"])
    )

    # Initialize storage for valid geometries and unsupported types
    geoms_dict = {g: [] for g in relevant_geometries}
    unsupported_counts = {}

    # Loop through all OSM elements returned
    for element in result.elements():
        geometry = element.geometry()
        geometry_type = geometry.get('type')

        # If geometry type is expected, store it with basic metadata
        if geometry_type in geoms_dict:
            try:
                props = {
                    'Name': element.tag('name') or 'Unknown',
                    'id': str(element.id()),
                    'Type': element.type()
                }
                geom = shape(geometry)
                geoms_dict[geometry_type].append({**props, 'geometry': geom})
            except Exception as e:
                print(f"Error parsing element {element.id()}: {e}")
        else:
            # Otherwise, track it as unsupported
            unsupported_counts[geometry_type] = unsupported_counts.get(geometry_type, 0) + 1

    # Build output GeoPackage path
    gpkg_path = os.path.join(output_dir, f"{region_name.replace(' ', '_')}.gpkg")

    # Save each geometry type to a separate layer in the GPKG
    layer_count = 0
    for geom_type, features in geoms_dict.items():
        if not features:
            continue
        gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
        gdf.to_file(
            gpkg_path,
            layer=f"{feature_key}_{geom_type}",  # e.g., "road_way_LineString"
            driver="GPKG",
            mode='w' if layer_count == 0 else 'a'  # overwrite first, append others
        )
        layer_count += 1

    # Final log for this feature/region
    print(f"\nSaved {element_type.upper()} data for '{category}={category_element}' to {gpkg_path}")
    print(f"Elapsed time: {time.time() - start_time:.2f} seconds")

    # Return summary of unsupported geometries
    return unsupported_counts


# --------------------- MAIN EXECUTION ---------------------

# Define OSM features to fetch
features_dict = {
    "substation_way": ['power', 'substation', 'way'],
    "generator_node": ['power', 'generator', 'node'],
    "road_way": ['highway', 'primary', 'way'],
    "railway_way": ['railway', 'railways', 'way'],
    "airport_way": ['aeroway', 'aerodrome', 'way'],
    "waterbody_way": ['natural', 'water', 'way'],
    "military_area": ['military', 'yes', 'way']
}

# Define regions to process
regions = [
    "Anhui",
    "Beijing"
]

# Define output base directory and prepare unsupported log
output_base = "Input_data/OSM_Infrastructure"
unsupported_summary = {}

# Loop through regions and features
for region in regions:
    region_dir = os.path.join(output_base, region.replace(" ", "_"))

    for feature_key in features_dict:
        print(f"\nProcessing {feature_key} in {region}")
        unsupported = fetch_osm_feature_to_gpkg(
            region_name=region,
            feature_key=feature_key,
            features_dict=features_dict,
            output_dir=region_dir
        )

        # Save unsupported counts if any were found
        if unsupported:
            unsupported_summary[f"{region}_{feature_key}"] = unsupported

# Save summary of unsupported geometries to JSON file
with open(region_dir, "w", encoding="utf-8") as f:
    json.dump(unsupported_summary, f, indent=2, ensure_ascii=False)

print(f"\nUnsupported geometry summary saved to {region_dir}")