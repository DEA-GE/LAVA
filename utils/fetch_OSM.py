"""
@author: Matteo D'Andrea
@date: 23-05-2025

@description:
Script to fetch OpenStreetMap (OSM) features using the Overpass API and save them into
separate GeoPackage (.gpkg) files per region and feature. Each geometry type is saved
in its own file, named as <region>_<feature>_<geometry>.gpkg.

The script also tracks unsupported geometry types and saves a JSON summary per feature/region.
"""

import os
import time
import json
from typing import Optional
from shapely.geometry import shape
import geopandas as gpd
from OSMPythonTools.nominatim import Nominatim
from OSMPythonTools.overpass import overpassQueryBuilder, Overpass
from utils.data_preprocessing import rel_path
import yaml

import logging
from OSMPythonTools import logger as osm_logger

# Suppress OSMPythonTools errors (especially geometry building errors)
osm_logger.setLevel(logging.CRITICAL)

# Suppress pyogrio INFO logs
logging.getLogger("pyogrio").setLevel(logging.WARNING)


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

    feature_spec = features_dict[feature_key]

    # Check if this is a multi-query feature (list of queries)
    # e.g., [["waterway", "river", ["way", "relation"]], ["water", "lake", ["way", "relation"]]]
    if isinstance(feature_spec[0], list):
        query_specs = feature_spec
    else:
        # Single query spec: [category, category_element, element_type]
        query_specs = [feature_spec]

    start_time = time.time()  # noqa: F841
    os.makedirs(output_dir, exist_ok=True)

    nominatim = Nominatim()  # Geocode region to retrieve area identifier
    location = nominatim.query(region_name)  # Query Nominatim for the region
    if not location:
        print(f"Region '{region_name}' not found.")
        return {}

    area_id = location.areaId()  # noqa: F841
    # print(f"Fetching data for: {region_name} ")
    # print(f"Fetching data for: {location.displayName()} (Area ID: {area_id})")

    overpass = Overpass()
    all_elements = []

    max_retries = 3
    retry_delay = 3  # seconds between retries

    # Process each query specification
    for query_spec in query_specs:
        category, category_element, element_type = query_spec

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

        # some spatial elements like airports or waterbodies can be represented as both ways and relations
        element_types = (
            element_type if isinstance(element_type, list) else [element_type]
        )

        query = overpassQueryBuilder(
            polygon=polygon,
            elementType=element_types,
            selector=selector,
            includeGeometry=True,
        )  # Build Overpass query

        # Execute query with retry logic (up to max_retries attempts on failure)
        result = None
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                result = overpass.query(query, timeout=timeout)
                break
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    print(
                        f"Overpass query failed for '{feature_key}' "
                        f"(attempt {attempt}/{max_retries}): {e}, retrying in {retry_delay}s"
                    )
                    time.sleep(retry_delay)
                else:
                    print(
                        f"Overpass query failed for '{feature_key}' "
                        f"after {max_retries} attempts: {e}"
                    )

        if result is None:
            continue

        if result.elements():
            all_elements.extend(result.elements())

    if not all_elements:
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
        "waterbodies": [
            "LineString",
            "Polygon",
        ],  # LineString for rivers, Polygon for lakes
        "military": ["Polygon"],
    }

    relevant_geometries = (
        relevant_geometries_override[feature_key]
        if relevant_geometries_override and feature_key in relevant_geometries_override
        else default_geometries.get(feature_key, ["Point", "LineString", "Polygon"])
    )

    geoms_dict = {g: [] for g in relevant_geometries}  # Store features by geometry type
    unsupported_counts = {}  # Track unsupported geometry types
    seen_ids = set()  # Track seen element IDs to avoid duplicates across queries

    for element in all_elements:  # Iterate over all returned OSM elements
        # Skip duplicates (elements can appear in multiple queries)
        element_id = (element.type(), element.id())
        if element_id in seen_ids:
            continue
        seen_ids.add(element_id)

        # Try to get geometry, skip if it fails (e.g., malformed relations)
        try:
            geometry = element.geometry()
        except Exception:
            # print(f"Skipping element {element.type()}/{element.id()}: Cannot build geometry - {e}")
            continue

        geometry_type = geometry.get("type")
        if geometry_type in geoms_dict:
            try:
                # Extract all tags (metadata) from the element
                props = {"osm_id": str(element.id()), "osm_type": element.type()}
                # Add all tags from the element
                if hasattr(element, "tags") and callable(element.tags):
                    props.update(element.tags())

                geom = shape(geometry)  # Convert GeoJSON-like dict to Shapely geometry
                geoms_dict[geometry_type].append({**props, "geometry": geom})
            except Exception as e:
                print(f"Error parsing element {element.id()}: {e}")
        else:
            unsupported_counts[geometry_type] = (
                unsupported_counts.get(geometry_type, 0) + 1
            )

    # Combine all geometry types into a single GeoPackage
    gpkg_path = os.path.join(output_dir, f"{feature_key}.gpkg")

    # Collect all features from all geometry types
    all_features = []
    for geom_type, features in geoms_dict.items():
        if features:
            all_features.extend(features)

    if all_features:
        gdf = gpd.GeoDataFrame(all_features, crs=f"EPSG:{EPSG}")

        # Drop problematic columns that cause issues with GPKG driver
        problematic_cols = {"FIXME", "fixme"}
        cols_to_drop = [col for col in gdf.columns if col in problematic_cols]
        if cols_to_drop:
            gdf = gdf.drop(columns=cols_to_drop)

        # Write all features to a single layer
        gdf.to_file(gpkg_path, driver="GPKG", encoding="utf-8")

        # Count by geometry type for reporting
        geom_counts = gdf.geometry.geom_type.value_counts().to_dict()
        count_str = ", ".join(
            [f"{count} {geom_type}(s)" for geom_type, count in geom_counts.items()]
        )
        print(f"Saved {len(gdf)} features to {rel_path(gpkg_path)} ({count_str})")

    # print(f"✅ Finished '{feature_key}' for {region_name} in {time.time() - start_time:.2f} seconds.")
    return unsupported_counts


if __name__ == "__main__":
    # Load advanced data prep settings
    advanced_config_path = os.path.join(
        "configs", "advanced_settings", "advanced_data_prep_settings.yaml"
    )
    if not os.path.exists(advanced_config_path):
        advanced_config_path = os.path.join(
            "configs", "advanced_settings", "advanced_data_prep_settings_template.yaml"
        )
    with open(advanced_config_path, "r", encoding="utf-8") as f:
        config_advanced = yaml.load(f, Loader=yaml.FullLoader)

    osm_features_config = config_advanced.get("osm_features_config", {})

    polygon = [[48.3, 16.3], [48.3, 16.5], [48.2, 16.6], [48.1, 16.5], [48.1, 16.3]]
    region = "Example Region"
    output_base = "data"

    region_dir = os.path.join(
        output_base, region.replace(" ", "_"), "OSM_Infrastructure"
    )
    os.makedirs(region_dir, exist_ok=True)
    unsupported_summary = {}

    for feature_key in osm_features_config:
        gpkg_path = os.path.join(region_dir, f"{feature_key}.gpkg")
        if os.path.exists(gpkg_path):
            print(
                f">> Skipping '{feature_key}' for {region}: '{rel_path(gpkg_path)}' already exists."
            )
            continue

        print(f"\nProcessing {feature_key} in {region}")
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

    print(f"Unsupported geometry summary saved to {rel_path(summary_path)}")
