import json
import logging
import os
import time
from typing import Optional

import geopandas as gpd
from OSMPythonTools import logger as osm_logger
from OSMPythonTools.nominatim import Nominatim
from OSMPythonTools.overpass import Overpass, overpassQueryBuilder
from pyproj import CRS
from shapely.geometry import shape

from lava.utils.study_area import StudyArea
from lava.utils.common import rel_path
from lava.utils.vector import generate_overpass_polygon

osm_logger.setLevel(logging.CRITICAL)
logging.getLogger("pyogrio").setLevel(logging.WARNING)


def prepare_osm_geofabrik(study_area: StudyArea, config_advanced, osm_data_path):
    """Process local Geofabrik OSM shapefiles."""
    try:
        OSM_output_dir = os.path.join(study_area.output_dir, "OSM_Infrastructure")
        os.makedirs(OSM_output_dir, exist_ok=True)
        process_all_local_osm_layer(
            config_advanced,
            study_area.boundary_4326,
            study_area.name,
            OSM_output_dir,
            osm_data_path,
            target_crs=None,
        )
    except Exception as e:
        logging.error(f"local OSM shapefiles failed: {e}")


def prepare_osm_overpass(
    study_area: StudyArea, selected_osm_features_dict, force_osm_download
):
    """Download the selected OSM features via Overpass."""
    print("\nprocessing OSM data")
    region_name_clean = study_area.name

    print("Prepare polygon for overpass query")
    # Use the GDAM polygon to fetch OSM data, first simplify the polygon to avoid too many vertices
    polygon = generate_overpass_polygon(study_area.boundary_4326)

    # Define output base directory and prepare unsupported log
    OSM_output_dir = os.path.join(study_area.output_dir, "OSM_Infrastructure")
    unsupported_summary = {}
    unsupported_geometries_summary_path = os.path.join(
        OSM_output_dir, "unsupported_geometries_summary.json"
    )

    # Loop through regions and features
    for feature_key in selected_osm_features_dict:
        # skip if we’ve already got this GeoPackage
        gpkg_path = os.path.join(OSM_output_dir, f"{feature_key}.gpkg")

        if os.path.exists(gpkg_path) and not force_osm_download:
            print(
                f">>  Skipping '{feature_key}' for {region_name_clean}: '{rel_path(gpkg_path)}' already exists."
            )

        else:
            print(f"\nProcessing {feature_key} in {region_name_clean}")
            # the function returns a dictionary with unsupported geometries to check if the features dictionary is correct
            unsupported = osm_to_gpkg(
                region_name=region_name_clean,
                polygon=polygon,
                feature_key=feature_key,
                features_dict=selected_osm_features_dict,
                timeout=500,
                # Optional override for geometry types per feature::
                # relevant_geometries_override={"substation": ["node"]},
                output_dir=OSM_output_dir,
            )

            # Save unsupported counts if any were found
            if unsupported:
                unsupported_summary[f"{region_name_clean}_{feature_key}"] = unsupported

        # Save summary of unsupported geometries to JSON file
        # Unsupported geometries are geometries not expected for the feature, e.g. a "node" for a transmission line.
        # Usually there are few unsupported geometries.
        with open(unsupported_geometries_summary_path, "w", encoding="utf-8") as f:
            json.dump(unsupported_summary, f, indent=2, ensure_ascii=False)

    print(f"\nUnsupported geometry summary saved to {rel_path(OSM_output_dir)}")


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

    max_retries = 5
    retry_delay = 5  # seconds between retries

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
        for attempt in range(1, max_retries + 1):
            try:
                result = overpass.query(query, timeout=timeout)
                break
            except Exception as e:
                if attempt < max_retries:
                    print(
                        f"Overpass query failed for '{feature_key}' "
                        f"(attempt {attempt}/{max_retries}): {e}, retrying in {retry_delay}s"
                    )
                    time.sleep(retry_delay)
                else:
                    print(
                        f"Overpass query failed for '{feature_key}' "
                        f"after {max_retries} attempts: {e}. Skipping."
                    )
        else:
            # Loop completed without break — all retries exhausted, skip this query spec
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


def process_single_local_osm_layer(
    config,
    layer_name,
    input_shp_filename,
    clip_region=None,
    region_name="",
    output_dir="",
    target_crs=None,
    OSM_data_path="",
):
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
    if config.get(f"{layer_name}") != 1:
        return

    # Read fclass list from config if available
    layer_fclasses = config.get("fclass", {}).get(layer_name)

    # Determine CRS tag for filename
    crs_tag = "EPSG4326"  # default CRS string if no reprojection  # noqa: F841
    if target_crs:
        crs = CRS.from_user_input(target_crs)
        authority = crs.to_authority()
        crs_tag = f"{authority[0]}{authority[1]}" if authority else "customCRS"  # noqa: F841

    output_filename = f"{layer_name}.gpkg"  # _{region_name}_{crs_tag}
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
            filtered_data = clipped_data[clipped_data["fclass"].isin(layer_fclasses)]
        else:
            filtered_data = clipped_data

        if target_crs:
            filtered_data = filtered_data.to_crs(crs)

        if not filtered_data.empty:
            filtered_data.to_file(output_filepath, driver="GPKG", encoding="utf-8")
        else:
            logging.info(f"No {layer_name} found in the region. File not saved.")
    except Exception as e:
        logging.error(f"Error processing {layer_name}: {e}")


def process_all_local_osm_layer(
    config, region, region_name_clean, output_dir, OSM_data_path, target_crs=None
):

    process_single_local_osm_layer(
        config,
        layer_name="railways",
        input_shp_filename="gis_osm_railways_free_1.shp",
        clip_region=region,
        region_name=region_name_clean,
        output_dir=output_dir,
        target_crs=target_crs,
        OSM_data_path=OSM_data_path,
    )

    process_single_local_osm_layer(
        config,
        layer_name="roads",
        input_shp_filename="gis_osm_roads_free_1.shp",
        clip_region=region,
        region_name=region_name_clean,
        output_dir=output_dir,
        target_crs=target_crs,
        OSM_data_path=OSM_data_path,
    )

    process_single_local_osm_layer(
        config,
        layer_name="airports",
        input_shp_filename="gis_osm_transport_a_free_1.shp",
        clip_region=region,
        region_name=region_name_clean,
        output_dir=output_dir,
        target_crs=target_crs,
        OSM_data_path=OSM_data_path,
    )

    process_single_local_osm_layer(
        config,
        layer_name="waterbodies",
        input_shp_filename="gis_osm_water_a_free_1.shp",
        clip_region=region,
        region_name=region_name_clean,
        output_dir=output_dir,
        target_crs=target_crs,
        OSM_data_path=OSM_data_path,
    )

    process_single_local_osm_layer(
        config,
        layer_name="military",
        input_shp_filename="gis_osm_landuse_a_free_1.shp",
        clip_region=region,
        region_name=region_name_clean,
        output_dir=output_dir,
        target_crs=target_crs,
        OSM_data_path=OSM_data_path,
    )
