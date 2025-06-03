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

def osm_to_gpkg(
    region_name: str,
    polygon: str,
    feature_key: str,
    features_dict: dict,
    EPSG: int = 4326,
    output_dir: str = "OSM_Infrastructure",
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
    selector = [f'"{category}"="{category_element}"']

    start_time = time.time()
    os.makedirs(output_dir, exist_ok=True)

    nominatim = Nominatim()
    location = nominatim.query(region_name)
    if not location:
        print(f"Region '{region_name}' not found.")
        return {}

    area_id = location.areaId()
    print(f"Fetching data for: {location.displayName()} (Area ID: {area_id})")

    overpass = Overpass()
    query = overpassQueryBuilder(
        polygon=polygon
        elementType=[element_type],
        selector=selector,
        includeGeometry=True
        )
    result = overpass.query(query, timeout=timeout)

    if not result.elements():
        print(f"No elements found for {feature_key} in {region_name}")
        return {}

    # Expected geometries
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

    geoms_dict = {g: [] for g in relevant_geometries}
    unsupported_counts = {}

    for element in result.elements():
        geometry = element.geometry()
        geometry_type = geometry.get('type')
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
            unsupported_counts[geometry_type] = unsupported_counts.get(geometry_type, 0) + 1

    # Save each geometry type to its own GeoPackage file
    for geom_type, features in geoms_dict.items():
        if not features:
            continue
        gdf = gpd.GeoDataFrame(features, crs=f"EPSG:{EPSG}")
        gpkg_path = os.path.join(
            output_dir, f"{feature_key}.gpkg"
        )
        gdf.to_file(gpkg_path, driver="GPKG")
        print(f"  ✔ Saved {len(gdf)} {geom_type}(s) to {gpkg_path}")

    print(f"✅ Finished '{feature_key}' for {region_name} in {time.time() - start_time:.2f} seconds.")
    return unsupported_counts


# --------------------- MAIN EXECUTION ---------------------

"""
import yaml

# Load config file
with open("configs/config.yaml", 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# Load all possible OSM features directly from config
osm_features_config = config.get("osm_features_config", {})

polygon= "39.3657 110.4954 39.313 110.3841 39.4612 110.1431 39.2837 110.2113 39.0656 109.7136 38.8127 109.5665 38.8036 109.421 38.6182 109.3409 38.5551 109.148 38.1962 108.9313 38.0261 109.0485 37.9213 108.9378 38.0191 108.7896 37.6869 108.7838 37.6166 108.1429 37.6659 108.0144 37.7919 107.9662 37.9487 107.4089 38.0952 107.3204 38.1579 106.81 38.2964 106.5117 38.7237 106.6973 39.0331 106.9704 39.0927 106.8424 39.3755 106.7675 39.2728 106.2864 39.1474 106.282 39.149 106.1384 38.6452 105.851 38.2689 105.8591 38.134 105.7637 38.0036 105.836 37.7994 105.7565 37.5444 104.9853 37.5156 104.4094 37.4082 104.1782 37.7858 103.669 37.8474 103.4102 38.0907 103.3623 38.1553 103.5444 38.4075 103.4123 38.6451 103.8763 38.8912 104.0319 38.9415 104.1742 39.0929 104.2057 39.2975 104.0525 39.4178 104.0911 39.4588 103.8375 39.3461 103.3614 39.1022 103.0019 39.254 102.4558 39.1021 101.8152 38.8969 102.0805 38.6648 101.7768 38.7828 101.3275 38.9547 101.1759 39.0239 101.2199 38.9572 101.0158 39.0469 100.9401 39.009 100.857 39.3992 100.845 39.3984 100.4996 39.4798 100.5014 39.5183 100.3204 39.6875 100.2506 39.886 99.7649 39.8761 99.4532 40.2121 99.9069 40.6007 100.2399 40.8831 100.0941 40.9328 99.6776 40.8488 99.5683 40.8647 99.1794 40.753 98.8689 40.5419 98.6479 40.5251 98.2559 40.8824 98.3524 41.0961 97.9731 41.4584 97.612 41.659 97.8399 42.7717 97.1847 42.5701 99.4963 42.6833 100.3265 42.6453 100.9116 42.4736 101.8168 42.2187 102.0633 42.1342 102.739 41.9075 103.3221 41.8079 103.8624 41.8838 104.5437 41.6626 104.534 41.6453 104.9449 41.5677 105.0345 41.9576 105.8019 42.4619 107.4528 42.3873 108.8115 42.6379 110.1536 42.93 110.622 43.3435 111.0471 43.4895 111.5745 43.6907 111.7539 43.7706 112.0054 43.9928 111.8522 44.0635 111.6317 44.3475 111.3868 44.7231 111.5599 45.0649 111.8645 45.0615 112.4155 44.8747 112.7419 44.744 113.6238 45.1653 114.3793 45.4309 114.6435 45.3652 115.0001 45.4384 115.7212 45.6118 115.9343 45.7038 116.2234 45.9503 116.2621 46.2871 116.5851 46.3811 116.8615 46.3487 117.3657 46.5796 117.4389 46.5188 117.8171 46.7876 118.2701 46.8182 118.9783 46.6336 119.4037 46.5605 119.4585 46.4753 119.3895 46.4195 119.5133 46.7435 119.9207 46.9233 119.8039 47.1221 119.8414 47.1931 119.7015 47.1616 119.8717 47.2791 119.8105 47.3362 119.4751 47.4327 119.3222 47.5461 119.3169 47.5395 119.1517 47.7033 119.1241 48.0001 118.4787 48.0254 117.8419 47.6381 117.3745 47.9001 116.8039 47.8659 116.2123 47.6755 115.9354 47.9951 115.4565 48.0001 115.5498 48.1803 115.51 48.2705 115.8261 48.5317 115.8215 48.7928 116.111 48.8835 116.0557 49.8399 116.7003 49.5054 117.8546 49.9257 118.5626 50.0087 119.1868 50.1046 119.3219 50.3398 119.3524 50.3848 119.1163 50.7395 119.4803 50.9066 119.5144 51.0903 119.745 51.6772 120.0925 51.9282 120.6464 52.1584 120.7782 52.3447 120.6102 52.5431 120.721 52.6413 120.4525 52.5841 120.0612 52.7681 120.0243 53.2693 120.8234 53.3885 121.6924 53.3312 121.4894 53.0641 121.8092 52.8347 121.5944 52.5944 121.1843 52.4413 121.6409 52.2825 121.8281 52.5134 122.1589 52.3924 122.4399 52.2948 122.471 52.2513 122.7801 52.0657 122.6175 51.9774 122.7191 51.4763 122.8477 51.3115 122.9942 51.2494 123.2828 51.3177 123.6545 51.3977 123.7109 51.2993 123.9188 51.3483 124.2171 51.2703 124.3987 51.3788 124.4826 51.3254 124.6248 51.3819 124.8693 51.6591 125.1128 51.6222 125.3435 51.2295 125.7453 51.1204 125.992 50.962 126.0738 50.7502 125.7489 50.5468 125.8191 50.4061 125.5007 50.2267 125.4569 50.1255 125.2719 50.057 125.328 49.9567 125.172 49.8705 125.2379 49.8297 125.1687 49.6669 125.2128 49.6444 125.1203 49.5912 125.226 49.4513 125.2605 49.187 125.2134 49.1113 124.7973 48.5483 124.5128 48.2981 124.573 48.1241 124.5023 48.0865 124.4185 48.1642 124.4742 48.5297 124.2668 48.0417 123.5742 47.9591 123.2989 47.8002 123.1774 47.5444 122.5834 47.3441 122.3879 47.1225 122.6047 47.0528 122.842 46.9756 122.7659 46.9578 122.8867 46.8157 122.889 46.7173 123.0072 46.8649 123.3575 47.0062 123.3128 46.9538 123.5245 46.8217 123.4971 46.8858 123.5971 46.6936 123.5974 46.5695 122.9982 46.4189 123.012 46.2373 123.1732 46.0972 123.0383 46.0675 122.7799 45.872 122.8199 45.6893 122.711 45.9101 122.4147 45.8031 122.2461 46.0231 121.8381 45.7914 121.744 45.7593 121.6267 45.6849 121.7229 45.6933 121.9664 45.56 121.9643 45.4359 122.1569 45.2998 122.1403 45.2652 122.2335 44.896 122.0278 44.7745 122.1622 44.7452 122.0784 44.5764 122.1133 44.4653 122.2889 44.2613 122.2625 44.2336 122.4793 44.5171 123.137 44.3631 123.1287 44.1581 123.3801 44.0678 123.3224 43.6294 123.5369 43.4955 123.317 43.3553 123.7119 42.9977 123.5778 42.9932 123.2498 42.9199 123.1761 42.8293 123.2314 42.7235 122.8528 42.8481 122.3963 42.7807 122.3545 42.7535 122.4468 42.6777 122.3811 42.6964 121.9573 42.4428 121.7021 42.5154 121.5862 42.4829 121.4002 42.2503 121.0338 42.1136 120.4763 42.0198 120.4688 41.9442 120.284 41.6947 120.0901 42.098 119.8376 42.2078 119.847 42.2555 119.6001 42.3868 119.4948 42.2029 119.2286 42.0897 119.374 41.7842 119.2817 41.5829 119.4051 41.3273 119.3199 41.2803 119.1943 41.2989 118.8847 41.3726 118.8376 41.32 118.3588 41.4734 118.2634 41.5644 118.3057 41.74 118.1239 41.8432 118.3288 42.0387 118.2805 42.0349 118.1098 42.1697 118.0995 42.2401 117.9623 42.296 118.0532 42.393 118.0127 42.6169 117.7861 42.5919 117.4782 42.4605 117.3704 42.4818 117.0865 42.4043 116.9153 42.1951 116.908 42.195 116.7792 42.0165 116.8734 41.9323 116.7242 42.0035 116.3208 41.7706 116.0468 41.9405 115.9145 41.935 115.8225 41.7068 115.3293 41.6157 115.3626 41.5761 115.237 41.5897 114.8574 41.7968 114.8681 41.8239 114.9413 42.0519 114.8155 42.1221 114.8648 42.1305 114.5539 41.9646 114.4896 41.7976 114.2051 41.5059 114.2427 41.4366 113.8636 41.2302 114.0094 41.0959 113.8125 40.7358 114.1279 40.7083 114.0574 40.5274 114.0551 40.4554 113.8568 40.5167 113.788 40.3343 113.4997 40.3175 113.3163 40.4122 113.2443 40.3503 112.961 40.1669 112.7439 40.2939 112.4111 40.1656 112.2189 39.6144 111.9296 39.6448 111.4367 39.4287 111.348 39.363 111.0984 39.4282 111.0561 39.5676 111.1471 39.5654 111.0238 39.2488 110.6153 39.3657 110.4954"


region = "Ciao"

output_base = "data"
unsupported_summary = {}


region_dir = os.path.join(output_base, region.replace(" ", "_"), "OSM_Infrastructure")




for feature_key in osm_features_config:

    # skip if we’ve already got this GeoPackage
    gpkg_path = os.path.join(region_dir, f"{feature_key}.gpkg")
    if os.path.exists(gpkg_path):
        print(f"⏭️  Skipping '{feature_key}' for {region}: '{gpkg_path}' already exists.")

    
    else: 
        print(f"\n🔍 Processing {feature_key} in {region}")
        unsupported = osm_to_gpkg(
            region_name=region,
            polygon=polygon,
            feature_key=feature_key,
            features_dict=osm_features_config,
            EPSG=4326,
            output_dir=region_dir
        )

        if unsupported:
            unsupported_summary[f"{region}_{feature_key}"] = unsupported

# Save unsupported geometry summary
summary_path = os.path.join(region_dir, "unsupported_summary.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(unsupported_summary, f, indent=2, ensure_ascii=False)

print(f"📄 Unsupported geometry summary saved to {region_dir}")

"""