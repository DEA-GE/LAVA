import os
import time
import fiona
from fiona.crs import from_epsg
from OSMPythonTools.nominatim import Nominatim
from OSMPythonTools.overpass import overpassQueryBuilder, Overpass

def fetch_osm_feature_from_dict(
    region_name: str,
    feature_key: str,
    features_dict: dict,
    output_dir: str = "Raw_Spatial_Data/OSM_Infrastructure",
    relevant_geometries_override: dict = None,
):
    """
    Fetch OSM infrastructure data for a given region and feature key.

    Args:
        region_name (str): Name of the region to query (e.g., "inner mongolia").
        feature_key (str): Key in the features_dict (e.g., "substation_way").
        features_dict (dict): A dictionary mapping keys to [category, category_element, element_type].
        output_dir (str): Directory where shapefiles will be saved.
        relevant_geometries_override (dict): Optional dict mapping feature_key to list of geometries.
    """
    if feature_key not in features_dict:
        raise ValueError(f"'{feature_key}' not found in features_dict.")

    category, category_element, element_type = features_dict[feature_key]
    selector = [f'"{category}"' if category_element == '*' else f'"{category}"="{category_element}"']

    start_time = time.time()
    os.makedirs(output_dir, exist_ok=True)

    nominatim = Nominatim()
    location = nominatim.query(region_name)
    if not location:
        print(f"Region '{region_name}' not found.")
        return

    area_id = location.areaId()
    print(f"Fetching data for: {location.displayName()} (Area ID: {area_id})")

    overpass = Overpass()
    query = overpassQueryBuilder(
        area=area_id,
        elementType=[element_type],
        selector=selector,
        includeGeometry=True
    )
    result = overpass.query(query, timeout=200)

    # Default relevant geometries by feature_key
    default_geometries = {
        "substation_way": ["Polygon"],
        "generator_node": ["Point"],
        "road_way": ["LineString"],
        "railway_way": ["LineString"],
        "airport_way": ["Polygon"],
        "waterbody_way": ["Polygon"],
        "military_area": ["Polygon"],
    }

    # Decide which geometries to include
    if relevant_geometries_override and feature_key in relevant_geometries_override:
        relevant_geometries = relevant_geometries_override[feature_key]
    else:
        relevant_geometries = default_geometries.get(feature_key, ["Point", "LineString", "Polygon"])

    schemas = {
        g: {
            'geometry': g,
            'properties': {'Name': 'str:80', 'Type': 'str:40', 'id': 'str:40'}
        } for g in relevant_geometries
    }
    # Create a tag slug for the shapefile names
    tag_slug = f"{category}_{category_element}_{element_type}".replace(' ', '_')
    shapefile_paths = {
        g: os.path.join(output_dir, f"{region_name.replace(' ', '_')}_{tag_slug}_{g.lower()}s.shp")
        for g in relevant_geometries
    }

    outputs = {
        g: fiona.open(shapefile_paths[g], 'w',
                       crs=from_epsg(4326), 
                       driver='ESRI Shapefile',
                         schema=schemas[g],
                         encoding='UTF-8')
        for g in relevant_geometries
    }

    for element in result.elements():
        geometry = element.geometry()
        geometry_type = geometry.get('type')
        if geometry_type in outputs:
            try:
                properties = {
                    'Name': element.tag('name') or 'Unknown',
                    'id': str(element.id()),
                    'Type': element.type()
                }
                outputs[geometry_type].write({'geometry': geometry, 'properties': properties})
            except Exception as e:
                print(f"Error writing element {element.id()}: {e}")
        else:
            print(f"Unsupported geometry type: {geometry_type}")

    for output in outputs.values():
        output.close()

    print(f"\nSaved {element_type.upper()} data for '{category}={category_element}' to:")
    for g, path in shapefile_paths.items():
        print(f"  - {g}: {path}")
    print(f"Elapsed time: {time.time() - start_time:.2f} seconds")

#"line_relation": ['power', 'line', 'relation'],
#"plant_node": ['power', 'plant', 'way'],


features_dict = {
    "substation_way": ['power', 'substation', 'way'],
    "generator_node": ['power', 'generator', 'node'],
        "road_way": ['highway', 'primary', 'way'],              
    "railway_way": ['railway', 'railways', 'way'],           
    "airport_way": ['aeroway', 'aerodrome', 'way'],   # airports as aerodromes
    "waterbody_way": ['natural', 'water', 'way'],     # lakes, rivers, etc.
       "military_area_2": ['military', 'yes', 'way']

}

regions = ["Anhui",
    "Beijing"]

#    "Chongqing",
#    "Fujian",
#    "Gansu",
#    "Guangdong",
#    "Guangxi",
#    "Guizhou",
#    "Hainan",
#    "Hebei",]

output_base = "Input_data/OSM_Infrastructure"

''' Args:
        region_name (str): Name of the region to query (e.g., "inner mongolia").
        feature_key (str): Key in the features_dict (e.g., "substation_way").
        features_dict (dict): A dictionary mapping keys to [category, category_element, element_type].
        output_dir (str): Directory where shapefiles will be saved.
        relevant_geometries_override (dict): Optional dict mapping feature_key to list of geometries.
'''


for region in regions:
    region_dir = os.path.join(output_base, region.replace(" ", "_"))
    for feature_key in features_dict:
        print(f"\nProcessing {feature_key} in {region}")
        fetch_osm_feature_from_dict(
            region_name=region,
            feature_key=feature_key,
            features_dict=features_dict,
            #relevant_geometries_override={"substation_node": ["Point"]},
            output_dir=region_dir
        )