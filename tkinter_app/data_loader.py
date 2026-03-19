"""
Utility helpers to load initial configuration sections and sample result data.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIGS_PATH = ROOT_DIR / "configs"
CONFIG_PATH = CONFIGS_PATH / "config.yaml"
ONSHORE_PATH = CONFIGS_PATH / "onshorewind.yaml"
SOLAR_PATH = CONFIGS_PATH / "solar.yaml"
CONFIG_SNAKEMAKE_PATH = CONFIGS_PATH / "config_snakemake.yaml"
SAMPLE_RESULTS_PATH = ROOT_DIR / "src" / "sample-results.json"

FALLBACK_SECTIONS = [
    {
        "name": "general",
        "displayName": "General",
        "description": "Basic metadata about the study region.",
        "parameters": [
            {"key": "study_region_name", "value": "Sample Region", "type": "string"},
            {"key": "country_code", "value": "AAA", "type": "string"},
            {"key": "scenario", "value": "ref", "type": "string"},
            {"key": "tech_derate", "value": 0.95, "type": "number"},
            {"key": "force_osm_download", "value": 0, "type": "boolean"},
        ],
    }
]

DEFAULT_RESULTS_DATA: Dict[str, Any] = {
    "summary": [
        {"metric": "Total Records Processed", "value": "12,458", "change": "+15%"},
        {"metric": "Success Rate", "value": "98.5%", "change": "+2.3%"},
        {"metric": "Average Processing Time", "value": "0.45s", "change": "-12%"},
        {"metric": "Errors Encountered", "value": "23", "change": "-8%"},
    ],
    "chartData": [
        {"name": "Batch 1", "processed": 4000, "errors": 5, "time": 2.4},
        {"name": "Batch 2", "processed": 3800, "errors": 8, "time": 2.1},
        {"name": "Batch 3", "processed": 4200, "errors": 4, "time": 2.3},
        {"name": "Batch 4", "processed": 4658, "errors": 6, "time": 2.5},
    ],
    "detailedResults": [
        {
            "id": 1,
            "batch": "Batch 1",
            "records": 4000,
            "success": 3995,
            "failed": 5,
            "duration": "2.4s",
            "status": "Success",
        },
        {
            "id": 2,
            "batch": "Batch 2",
            "records": 3800,
            "success": 3792,
            "failed": 8,
            "duration": "2.1s",
            "status": "Success",
        },
        {
            "id": 3,
            "batch": "Batch 3",
            "records": 4200,
            "success": 4196,
            "failed": 4,
            "duration": "2.3s",
            "status": "Success",
        },
        {
            "id": 4,
            "batch": "Batch 4",
            "records": 4658,
            "success": 4652,
            "failed": 6,
            "duration": "2.5s",
            "status": "Success",
        },
    ],
    "detailedResultsColumns": [
        "batch",
        "records",
        "success",
        "failed",
        "duration",
        "status",
    ],
    "outputFiles": [
        {
            "name": "processed_data.csv",
            "size": "2.4 MB",
            "records": 12458,
            "created": "2025-10-10 14:30",
        },
        {
            "name": "error_log.txt",
            "size": "4.2 KB",
            "records": 23,
            "created": "2025-10-10 14:30",
        },
        {
            "name": "summary_report.json",
            "size": "12.8 KB",
            "records": 1,
            "created": "2025-10-10 14:30",
        },
        {
            "name": "metadata.json",
            "size": "3.1 KB",
            "records": 1,
            "created": "2025-10-10 14:30",
        },
    ],
    "customGraphs": [
        {
            "type": "area",
            "title": "Processing Throughput Over Time",
            "data": [
                {"hour": "00:00", "throughput": 120},
                {"hour": "04:00", "throughput": 180},
                {"hour": "08:00", "throughput": 350},
                {"hour": "12:00", "throughput": 420},
                {"hour": "16:00", "throughput": 380},
                {"hour": "20:00", "throughput": 250},
            ],
            "xKey": "hour",
            "yKeys": ["throughput"],
        }
    ],
}

CONFIG_SECTION_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "general",
        "displayName": "General",
        "description": "Core scenario metadata.",
        "parameters": [
            {
                "key": "study_region_name",
                "type": "string",
                "description": "Name used for outputs.",
            },
            {
                "key": "country_code",
                "type": "string",
                "description": "Three-letter ISO code.",
            },
            {
                "key": "scenario",
                "type": "string",
                "description": "Scenario tag for filenames.",
            },
            {
                "key": "technology",
                "type": "string",
                "description": "Technology label for filenames.",
            },
            {"key": "tech", "type": "string", "description": "Technology dataset key."},
            {
                "key": "tech_derate",
                "type": "number",
                "description": "Technology derate factor.",
            },
            {
                "key": "model_areas_filename",
                "type": "string",
                "description": "Model areas filename.",
            },
        ],
    },
    {
        "name": "region_definition",
        "displayName": "Region Definition",
        "description": "Administrative or custom study area inputs.",
        "parameters": [
            {
                "key": "GADM_region_name",
                "type": "string",
                "description": "Exact GADM name (NAME_level).",
            },
            {"key": "GADM_level", "type": "string", "description": "GADM admin level."},
            {
                "key": "custom_study_area_filename",
                "type": "string",
                "description": "Custom study area filename template.",
            },
        ],
    },
    {
        "name": "data_landcover_dem",
        "displayName": "Landcover & DEM",
        "description": "Raster sources and resolution settings.",
        "parameters": [
            {
                "key": "landcover_source",
                "type": "string",
                "description": "Landcover source ('file' or 'openeo').",
            },
            {
                "key": "resolution_landcover",
                "type": "number",
                "description": "OpenEO download resolution (deg).",
            },
            {
                "key": "landcover_filename",
                "type": "string",
                "description": "Landcover filename with extension.",
            },
            {
                "key": "DEM_filename",
                "type": "string",
                "description": "DEM raster filename.",
            },
        ],
    },
    {
        "name": "osm_data",
        "displayName": "OSM Data",
        "description": "OpenStreetMap sources and layer toggles.",
        "parameters": [
            {
                "key": "OSM_source",
                "type": "string",
                "description": "OSM source ('geofabrik' or 'overpass').",
            },
            {
                "key": "OSM_folder_name",
                "type": "string",
                "description": "Geofabrik OSM folder name.",
            },
            {
                "key": "railways",
                "type": "boolean",
                "description": "Toggle railways OSM feature.",
            },
            {
                "key": "roads",
                "type": "boolean",
                "description": "Toggle roads OSM feature.",
            },
            {
                "key": "airports",
                "type": "boolean",
                "description": "Toggle airports OSM feature.",
            },
            {
                "key": "waterbodies",
                "type": "boolean",
                "description": "Toggle waterbodies OSM feature.",
            },
            {
                "key": "military",
                "type": "boolean",
                "description": "Toggle military OSM feature.",
            },
            {
                "key": "substations",
                "type": "boolean",
                "description": "Toggle substations OSM feature.",
            },
            {
                "key": "transmission_lines",
                "type": "boolean",
                "description": "Toggle transmission lines OSM feature.",
            },
            {
                "key": "generators",
                "type": "boolean",
                "description": "Toggle generators OSM feature.",
            },
            {
                "key": "plants",
                "type": "boolean",
                "description": "Toggle plants OSM feature.",
            },
            {
                "key": "coastlines",
                "type": "boolean",
                "description": "Toggle coastlines OSM feature.",
            },
            {
                "key": "force_osm_download",
                "type": "boolean",
                "description": "Force fresh OSM download.",
            },
        ],
    },
    {
        "name": "resources",
        "displayName": "Wind & Solar Resources",
        "description": "External resource availability datasets.",
        "parameters": [
            {
                "key": "wind_atlas",
                "type": "boolean",
                "description": "Download Global Wind Atlas.",
            },
            {
                "key": "solar_atlas",
                "type": "boolean",
                "description": "Download Global Solar Atlas.",
            },
            {
                "key": "country_name_solar_atlas",
                "type": "string",
                "description": "Country name for Solar Atlas.",
            },
            {
                "key": "solar_atlas_measure",
                "type": "string",
                "description": "Solar Atlas measure id.",
            },
        ],
    },
    {
        "name": "protected_areas",
        "displayName": "Protected Areas",
        "description": "Protected area inputs and sources.",
        "parameters": [
            {
                "key": "protected_areas_source",
                "type": "string",
                "description": "Protected areas source (WDPA/file/0).",
            },
            {"key": "wdpa_url", "type": "string"},
            {
                "key": "protected_areas_filename",
                "type": "string",
                "description": "Protected areas filename (EPSG:4326).",
            },
        ],
    },
    {
        "name": "forest_density",
        "displayName": "Forest Density",
        "description": "Optional forest density exclusion layer.",
        "parameters": [
            {
                "key": "forest_density",
                "type": "boolean",
                "description": "Enable forest density exclusions.",
            },
            {
                "key": "forest_density_filename",
                "type": "string",
                "description": "Forest density raster filename.",
            },
        ],
    },
    {
        "name": "compute_options",
        "displayName": "Compute Options",
        "description": "Pipeline step toggles.",
        "parameters": [
            {
                "key": "compute_substation_proximity",
                "type": "boolean",
                "description": "Compute substation proximity layer.",
            },
            {
                "key": "compute_road_proximity",
                "type": "boolean",
                "description": "Compute road proximity layer.",
            },
            {
                "key": "compute_terrain_ruggedness",
                "type": "boolean",
                "description": "Compute terrain ruggedness layer.",
            },
        ],
    },
    {
        "name": "crs_and_weather",
        "displayName": "CRS & Weather",
        "description": "Coordinate system overrides and weather data.",
        "parameters": [
            {
                "key": "CRS_manual",
                "type": "string",
                "description": "Manual CRS override.",
            },
            {
                "key": "weather_data_path",
                "type": "string",
                "description": "Weather data directory.",
            },
            {
                "key": "weather_year",
                "type": "number",
                "description": "Weather dataset year.",
            },
        ],
    },
    {
        "name": "additional_data",
        "displayName": "Additional Data",
        "description": "Custom exclusion dataset locations.",
        "parameters": [
            {
                "key": "additional_exclusion_polygons_folder_name",
                "type": "string",
                "description": "Folder for extra exclusion polygons.",
            },
            {
                "key": "additional_exclusion_rasters_folder_name",
                "type": "string",
                "description": "Folder for extra exclusion rasters.",
            },
        ],
    },
    {
        "name": "geometry_generalization",
        "displayName": "Geometry Generalization",
        "description": "Simplification tolerances for study areas and overpass data.",
        "parameters": [
            {
                "key": "study_area",
                "type": "array",
                "description": "Study area simplification settings.",
            },
            {
                "key": "target_vertices",
                "type": "number",
                "description": "Target vertices for overpass simplification.",
            },
            {
                "key": "tolerance_min",
                "type": "number",
                "description": "Minimum simplification tolerance.",
            },
            {
                "key": "tolerance_max",
                "type": "number",
                "description": "Maximum simplification tolerance.",
            },
        ],
    },
    {
        "name": "overpass_features",
        "displayName": "Overpass & Feature Config",
        "description": "Feature filters and tagging rules.",
        "parameters": [
            {
                "key": "fclass",
                "type": "array",
                "description": "Geofabrik feature class filters.",
            },
            {
                "key": "overpass_features",
                "type": "array",
                "description": "Overpass feature tag lists.",
            },
            {"key": "osm_features_config", "type": "array"},
        ],
    },
    {
        "name": "aspect_weights",
        "displayName": "Aspect & Exclusions",
        "description": "Slope, aspect and WDPA status filters.",
        "parameters": [
            {
                "key": "north_facing_pixels",
                "type": "string",
                "description": "Exclude north-facing pixels.",
            },
            {
                "key": "X",
                "type": "number",
                "description": "Slope threshold for exclusion.",
            },
            {"key": "Y", "type": "number", "description": "Start aspect angle."},
            {"key": "Z", "type": "number", "description": "End aspect angle."},
            {
                "key": "wdpa_consider_status",
                "type": "array",
                "description": "WDPA status values to include.",
            },
        ],
    },
    {
        "name": "heat_demand",
        "displayName": "Heat Demand",
        "description": "Heating demand profile assumptions.",
        "parameters": [
            {
                "key": "heat_demand_start_day",
                "type": "string",
                "description": "Heat demand start day (DD-MM).",
            },
            {
                "key": "heat_demand_end_day",
                "type": "string",
                "description": "Heat demand end day (DD-MM).",
            },
            {
                "key": "heat_demand_hour_shift",
                "type": "number",
                "description": "Hourly shift for demand profile.",
            },
            {
                "key": "heat_demand_constant",
                "type": "boolean",
                "description": "Temperature-independent demand share.",
            },
            {
                "key": "heat_demand_threshold",
                "type": "number",
                "description": "Temperature threshold (C).",
            },
        ],
    },
    {
        "name": "analysis_parameters",
        "displayName": "Analysis Parameters",
        "description": "Available area and cost tier settings.",
        "parameters": [
            {
                "key": "min_area_rg",
                "type": "number",
                "description": "Minimum area share per grade.",
            },
            {"key": "tiers", "type": "array", "description": "Cost tier breakpoints."},
            {
                "key": "average_sub_dist",
                "type": "array",
                "description": "Average substation distance (m).",
            },
        ],
    },
    {
        "name": "modifiers",
        "displayName": "Cost Modifiers",
        "description": "Terrain, landcover, region, and weight modifiers.",
        "parameters": [
            {
                "key": "terrain_modifier",
                "type": "array",
                "description": "Terrain cost modifiers.",
            },
            {"key": "landcover_modifier", "type": "array"},
            {
                "key": "region_modifier",
                "type": "array",
                "description": "Regional cost modifiers.",
            },
            {
                "key": "modifier_weights",
                "type": "array",
                "description": "Weights for suitability modifiers.",
            },
        ],
    },
]

ONSHORE_SECTION_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "deployment",
        "displayName": "Deployment Settings",
        "description": "Density and raster resolution for exclusion evaluation.",
        "parameters": [
            {
                "key": "deployment_density",
                "type": "number",
                "description": "Target deployment density (MW/km2).",
            },
            {
                "key": "resolution_manual",
                "type": "number",
                "description": "Manual exclusion grid resolution.",
            },
        ],
    },
    {
        "name": "landcover_buffers",
        "displayName": "Landcover Buffers",
        "description": "Buffer distances per landcover class (meters).",
        "parameters": [
            {
                "key": "landcover_codes",
                "type": "array",
                "description": "Landcover buffers by code (m).",
            },
        ],
    },
    {
        "name": "dem_thresholds",
        "displayName": "DEM Thresholds",
        "description": "Elevation, slope and ruggedness limits.",
        "parameters": [
            {
                "key": "max_elevation",
                "type": "number",
                "description": "Maximum elevation allowed (m).",
            },
            {
                "key": "max_slope",
                "type": "number",
                "description": "Maximum slope allowed (degrees).",
            },
            {
                "key": "max_terrain_ruggedness",
                "type": "number",
                "description": "Maximum terrain ruggedness index.",
            },
            {
                "key": "max_forest_density",
                "type": "number",
                "description": "Maximum forest density percent.",
            },
        ],
    },
    {
        "name": "spatial_buffers",
        "displayName": "Spatial Buffers",
        "description": "Buffer distances around spatial features (meters).",
        "parameters": [
            {
                "key": "railways_buffer",
                "type": "number",
                "description": "Railway buffer distance (m).",
            },
            {
                "key": "roads_buffer",
                "type": "number",
                "description": "Road buffer distance (m).",
            },
            {
                "key": "airports_buffer",
                "type": "number",
                "description": "Airport buffer distance (m).",
            },
            {
                "key": "waterbodies_buffer",
                "type": "number",
                "description": "Waterbody buffer distance (m).",
            },
            {
                "key": "military_buffer",
                "type": "number",
                "description": "Military buffer distance (m).",
            },
            {
                "key": "coastlines_buffer",
                "type": "number",
                "description": "Coastline buffer distance (m).",
            },
            {
                "key": "protectedAreas_buffer",
                "type": "number",
                "description": "Protected area buffer distance (m).",
            },
            {
                "key": "transmission_lines_buffer",
                "type": "number",
                "description": "Transmission line buffer distance (m).",
            },
            {
                "key": "generators_buffer",
                "type": "number",
                "description": "Generator buffer distance (m).",
            },
            {
                "key": "plants_buffer",
                "type": "number",
                "description": "Plant buffer distance (m).",
            },
        ],
    },
    {
        "name": "additional_exclusions",
        "displayName": "Additional Exclusions",
        "description": "Custom exclusion polygon buffers.",
        "parameters": [
            {
                "key": "additional_exclusion_polygons_buffer",
                "type": "array",
                "description": "Buffers per additional exclusion polygon.",
            },
        ],
    },
    {
        "name": "wind_resource",
        "displayName": "Wind Resource Filters",
        "description": "Limits for wind speed inclusion.",
        "parameters": [
            {
                "key": "min_wind_speed",
                "type": "number",
                "description": "Minimum wind speed (m/s).",
            },
            {
                "key": "max_wind_speed",
                "type": "number",
                "description": "Maximum wind speed (m/s).",
            },
        ],
    },
    {
        "name": "inclusion_filters",
        "displayName": "Inclusion Filters",
        "description": "Buffers to include areas near infrastructure (meters).",
        "parameters": [
            {
                "key": "substations_inclusion_buffer",
                "type": "number",
                "description": "Inclusion buffer around substations (m).",
            },
            {
                "key": "transmission_inclusion_buffer",
                "type": "number",
                "description": "Inclusion buffer around transmission lines (m).",
            },
            {
                "key": "roads_inclusion_buffer",
                "type": "number",
                "description": "Inclusion buffer around roads (m).",
            },
        ],
    },
    {
        "name": "area_filters",
        "displayName": "Area Filters",
        "description": "Minimum connected pixel thresholds.",
        "parameters": [
            {
                "key": "min_pixels_connected",
                "type": "number",
                "description": "Minimum connected pixels threshold.",
            },
            {
                "key": "min_pixels_x",
                "type": "number",
                "description": "Deprecated; use min_pixels_connected.",
            },
            {
                "key": "min_pixels_y",
                "type": "number",
                "description": "Deprecated; use min_pixels_connected.",
            },
        ],
    },
    {
        "name": "technology",
        "displayName": "Technology Parameters",
        "description": "Turbine configuration and derating factors.",
        "parameters": [
            {
                "key": "turbine",
                "type": "string",
                "description": "Turbine configuration filename.",
            },
            {
                "key": "tech_derate",
                "type": "number",
                "description": "Technology derate factor.",
            },
        ],
    },
    {
        "name": "wind_groups",
        "displayName": "Wind Resource Groups",
        "description": "Wind speed thresholds per resource group.",
        "parameters": [
            {
                "key": "wg_thr",
                "type": "array",
                "description": "Wind resource group thresholds (m/s).",
            },
        ],
    },
]

SOLAR_SECTION_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "deployment",
        "displayName": "Deployment Settings",
        "description": "Density and raster resolution for exclusion evaluation.",
        "parameters": [
            {
                "key": "deployment_density",
                "type": "number",
                "description": "Target deployment density (MW/km2).",
            },
            {
                "key": "resolution_manual",
                "type": "number",
                "description": "Manual exclusion grid resolution.",
            },
        ],
    },
    {
        "name": "landcover_buffers",
        "displayName": "Landcover Buffers",
        "description": "Buffer distances per landcover class (meters).",
        "parameters": [
            {
                "key": "landcover_codes",
                "type": "array",
                "description": "Landcover buffers by code (m).",
            },
        ],
    },
    {
        "name": "dem_thresholds",
        "displayName": "DEM Thresholds",
        "description": "Elevation, slope and ruggedness limits.",
        "parameters": [
            {
                "key": "max_elevation",
                "type": "number",
                "description": "Maximum elevation allowed (m).",
            },
            {
                "key": "max_slope",
                "type": "number",
                "description": "Maximum slope allowed (degrees).",
            },
            {
                "key": "max_terrain_ruggedness",
                "type": "number",
                "description": "Maximum terrain ruggedness index.",
            },
            {
                "key": "max_forest_density",
                "type": "number",
                "description": "Maximum forest density percent.",
            },
        ],
    },
    {
        "name": "spatial_buffers",
        "displayName": "Spatial Buffers",
        "description": "Buffer distances around spatial features (meters).",
        "parameters": [
            {
                "key": "railways_buffer",
                "type": "number",
                "description": "Railway buffer distance (m).",
            },
            {
                "key": "roads_buffer",
                "type": "number",
                "description": "Road buffer distance (m).",
            },
            {
                "key": "airports_buffer",
                "type": "number",
                "description": "Airport buffer distance (m).",
            },
            {
                "key": "waterbodies_buffer",
                "type": "number",
                "description": "Waterbody buffer distance (m).",
            },
            {
                "key": "military_buffer",
                "type": "number",
                "description": "Military buffer distance (m).",
            },
            {
                "key": "coastlines_buffer",
                "type": "number",
                "description": "Coastline buffer distance (m).",
            },
            {
                "key": "protectedAreas_buffer",
                "type": "number",
                "description": "Protected area buffer distance (m).",
            },
            {
                "key": "transmission_lines_buffer",
                "type": "number",
                "description": "Transmission line buffer distance (m).",
            },
            {
                "key": "generators_buffer",
                "type": "number",
                "description": "Generator buffer distance (m).",
            },
            {
                "key": "plants_buffer",
                "type": "number",
                "description": "Plant buffer distance (m).",
            },
        ],
    },
    {
        "name": "additional_exclusions",
        "displayName": "Additional Exclusions",
        "description": "Custom exclusion polygon buffers.",
        "parameters": [
            {
                "key": "additional_exclusion_polygons_buffer",
                "type": "array",
                "description": "Buffers per additional exclusion polygon.",
            },
        ],
    },
    {
        "name": "solar_resource",
        "displayName": "Solar Resource Filters",
        "description": "Limits for solar production inclusion.",
        "parameters": [
            {
                "key": "min_solar_production",
                "type": "number",
                "description": "Minimum solar production (kWh/kW/yr).",
            },
            {
                "key": "max_solar_production",
                "type": "number",
                "description": "Maximum solar production (kWh/kW/yr).",
            },
        ],
    },
    {
        "name": "inclusion_filters",
        "displayName": "Inclusion Filters",
        "description": "Buffers to include areas near infrastructure (meters).",
        "parameters": [
            {
                "key": "substations_inclusion_buffer",
                "type": "number",
                "description": "Inclusion buffer around substations (m).",
            },
            {
                "key": "transmission_inclusion_buffer",
                "type": "number",
                "description": "Inclusion buffer around transmission lines (m).",
            },
            {
                "key": "roads_inclusion_buffer",
                "type": "number",
                "description": "Inclusion buffer around roads (m).",
            },
        ],
    },
    {
        "name": "area_filters",
        "displayName": "Area Filters",
        "description": "Minimum connected pixel thresholds.",
        "parameters": [
            {
                "key": "min_pixels_connected",
                "type": "number",
                "description": "Minimum connected pixels threshold.",
            },
            {
                "key": "min_pixels_x",
                "type": "number",
                "description": "Deprecated; use min_pixels_connected.",
            },
            {
                "key": "min_pixels_y",
                "type": "number",
                "description": "Deprecated; use min_pixels_connected.",
            },
        ],
    },
    {
        "name": "technology",
        "displayName": "Technology Parameters",
        "description": "Panel configuration and derating factors.",
        "parameters": [
            {
                "key": "panel",
                "type": "string",
                "description": "Panel configuration filename.",
            },
            {
                "key": "tech_derate",
                "type": "number",
                "description": "Technology derate factor.",
            },
        ],
    },
    {
        "name": "solar_groups",
        "displayName": "Solar Resource Groups",
        "description": "Solar production thresholds per resource group.",
        "parameters": [
            {
                "key": "sg_thr",
                "type": "array",
                "description": "Solar resource group thresholds (kWh/m2/yr).",
            },
        ],
    },
]

CONFIG_SNAKEMAKE_SECTION_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "snakemake_parameters",
        "displayName": "Snakemake Parameters",
        "description": "Core Snakemake execution settings.",
        "parameters": [
            {
                "key": "cores",
                "type": "number",
                "description": "Number of Snakemake cores.",
            },
            {
                "key": "snakefile",
                "type": "string",
                "description": "Path to the Snakemake file.",
            },
        ],
    },
    {
        "name": "general_parameters",
        "displayName": "General Parameters",
        "description": "Region and scenario configuration for Snakemake runs.",
        "parameters": [
            {
                "key": "study_region_name",
                "type": "string",
                "description": "Region name for the run.",
            },
            {
                "key": "scenario",
                "type": "string",
                "description": "Scenario name for the run.",
            },
            {
                "key": "technologies",
                "type": "array",
                "description": "Technologies to process.",
            },
        ],
    },
]


try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore


def _format_array_value(value: Any) -> str:
    if value is None or value == "":
        return "[]"
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return value
        else:
            return json.dumps(parsed, ensure_ascii=False, indent=2)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _format_value_for_editor(value: Any, param_type: str) -> Any:
    if param_type == "number" and value is None:
        return 0
    if param_type == "boolean":
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes"}
        if value is None:
            return False
        return bool(value)
    if param_type == "number":
        if isinstance(value, (int, float)):
            return value
        if value is None or value == "":
            return 0
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0
        return int(numeric) if numeric.is_integer() else numeric
    if param_type == "array":
        if isinstance(value, (list, dict)):
            return value
        return _format_array_value(value)
    # treat as string by default
    if value is None:
        return ""
    return str(value)


def _infer_param_type(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _build_sections_from_data(
    data: Dict[str, Any],
    definitions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    used_keys = set()

    for section_def in definitions:
        params = []
        for param_def in section_def["parameters"]:
            key = param_def["key"]
            param_type = param_def.get("type", "string")
            raw_value = data.get(key)
            params.append(
                {
                    "key": key,
                    "value": _format_value_for_editor(raw_value, param_type),
                    "type": param_type,
                    "description": param_def.get("description", ""),
                }
            )
            used_keys.add(key)

        sections.append(
            {
                "name": section_def["name"],
                "displayName": section_def.get(
                    "displayName", section_def["name"].replace("_", " ").title()
                ),
                "description": section_def.get("description", ""),
                "parameters": params,
            }
        )

    leftovers = [key for key in data.keys() if key not in used_keys]
    if leftovers:
        extra_params = []
        for key in leftovers:
            raw_value = data[key]
            inferred_type = _infer_param_type(raw_value)
            extra_params.append(
                {
                    "key": key,
                    "value": _format_value_for_editor(raw_value, inferred_type),
                    "type": inferred_type,
                    "description": "",
                }
            )
    return sections


def _load_sections_from_yaml(
    path: Path,
    definitions: List[Dict[str, Any]],
    fallback: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if yaml is None or not path.exists():
        return deepcopy(fallback)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("Unexpected YAML structure")
    except Exception:
        return deepcopy(fallback)

    return _build_sections_from_data(data, definitions)


def load_initial_sections() -> List[Dict[str, Any]]:
    """
    Load configuration sections from config.yaml, falling back to a minimal default.
    """
    return _load_sections_from_yaml(
        CONFIG_PATH, CONFIG_SECTION_DEFINITIONS, FALLBACK_SECTIONS
    )


def load_onshore_sections() -> List[Dict[str, Any]]:
    fallback = _build_sections_from_data(
        {},
        ONSHORE_SECTION_DEFINITIONS,
    )
    return _load_sections_from_yaml(ONSHORE_PATH, ONSHORE_SECTION_DEFINITIONS, fallback)


def load_solar_sections() -> List[Dict[str, Any]]:
    fallback = _build_sections_from_data(
        {},
        SOLAR_SECTION_DEFINITIONS,
    )
    return _load_sections_from_yaml(SOLAR_PATH, SOLAR_SECTION_DEFINITIONS, fallback)


def load_config_snakemake_sections() -> List[Dict[str, Any]]:
    fallback = _build_sections_from_data(
        {  # dummy data, user must specify
            "snakefile": "snakefile_dummy",
            "cores": "4",
            "study_region_name": "dummy_region",
            "scenario": "dummy",
            "technologies": ["dummy1", "dumm2"],
        },
        CONFIG_SNAKEMAKE_SECTION_DEFINITIONS,
    )
    return _load_sections_from_yaml(
        CONFIG_SNAKEMAKE_PATH, CONFIG_SNAKEMAKE_SECTION_DEFINITIONS, fallback
    )


def load_sample_results() -> Dict[str, Any]:
    """
    Load sample result data from the existing JSON file or use defaults.
    """
    if SAMPLE_RESULTS_PATH.exists():
        try:
            return json.loads(SAMPLE_RESULTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return deepcopy(DEFAULT_RESULTS_DATA)
