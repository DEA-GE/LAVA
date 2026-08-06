"""
Utility helpers to load initial configuration sections and sample result data.
"""

from __future__ import annotations

import json
from copy import deepcopy
import ast
from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
except ImportError:  # pragma: no cover - optional dependency
    YAML = None  # type: ignore
    CommentedMap = dict  # type: ignore
    CommentedSeq = list  # type: ignore

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIGS_PATH = ROOT_DIR / "configs"
CONFIG_PATH = CONFIGS_PATH / "config.yaml"
ONSHORE_PATH = CONFIGS_PATH / "onshorewind.yaml"
SOLAR_PATH = CONFIGS_PATH / "solar.yaml"
OFFSHORE_PATH = CONFIGS_PATH / "offshorewind.yaml"
SUITABILITY_PATH = CONFIGS_PATH / "suitability.yaml"
SNAKEMAKE_PATH = CONFIGS_PATH / "snakemake.yaml"
SAMPLE_RESULTS_PATH = ROOT_DIR / "src" / "sample-results.json"

YAML_RT: Optional[YAML] = None  # type: ignore[assignment]
if YAML is not None:
    YAML_RT = YAML(typ="rt")
    YAML_RT.preserve_quotes = True
    YAML_RT.width = 4096
    YAML_RT.indent(mapping=2, sequence=4, offset=2)
    YAML_RT.default_flow_style = False

FALLBACK_SECTIONS = [
    {
        "name": "general",
        "displayName": "General",
        "description": "Basic metadata about the study region.",
        "parameters": [
            {"key": "study_region_name", "value": "Sample Region", "type": "string"},
            {"key": "country_code", "value": "AAA", "type": "string"},
            {"key": "scenario", "value": "ref", "type": "string"},
            {"key": "technology", "value": "solar", "type": "string"},
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
                "description": "Name used for output folder in /data .",
            },
            {
                "key": "country_code",
                "type": "string",
                "description": "Three-letter ISO code used by GADM and solar and wind atlases.",
            },
            {
                "key": "scenario",
                "type": "string",
                "description": "Scenario tag for filenames.",
            },
            {
                "key": "technology",
                "type": "string",
                "description": "Technology tag for filenames.",
            },
            {
                "key": "CRS_manual",
                "type": "string",
                "description": "Manual CRS override.",
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
                "description": "Exact GADM name given a specific administrative level. Found in column NAME_(level) - e.g. NAME_1 .",
            },
            {
                "key": "GADM_level",
                "type": "integer",
                "description": "GADM admin level.",
            },
            {
                "key": "custom_study_area_filename",
                "type": "string",
                "description": "Custom study area filename template. Use {region_name}.geojson when using snakemake to iterate over several areas.",
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
                "description": "OpenEO download resolution in degress (EPSG4326); 0.008999280057498208 degrees is ca. 1000m at equator.",
            },
            {
                "key": "landcover_filename",
                "type": "string",
                "description": "Landcover filename with extension; used instead of openeo.",
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
        "description": "OpenStreetMap sources and layer Download.",
        "parameters": [
            {
                "key": "OSM_source",
                "type": "string",
                "description": "OSM source (geofabrik or overpass).",
            },
            {
                "key": "OSM_folder_name",
                "type": "string",
                "description": "Geofabrik OSM folder name within /Raw_Spatial_Data/OSM with all raw OSM shapefiles; only needed if Geofabrik used as OSM source",
            },
            {
                "key": "railways",
                "type": "boolean",
                "description": "Download railways OSM feature.",
            },
            {
                "key": "roads",
                "type": "boolean",
                "description": "Download roads OSM feature.",
            },
            {
                "key": "airports",
                "type": "boolean",
                "description": "Download airports OSM feature.",
            },
            {
                "key": "waterbodies",
                "type": "boolean",
                "description": "Download waterbodies OSM feature.",
            },
            {
                "key": "military",
                "type": "boolean",
                "description": "Download military OSM feature.",
            },
            {
                "key": "substations",
                "type": "boolean",
                "description": "Download substations OSM feature.",
            },
            {
                "key": "transmission_lines",
                "type": "boolean",
                "description": "Download transmission lines OSM feature.",
            },
            {
                "key": "generators",
                "type": "boolean",
                "description": "Download generators OSM feature.",
            },
            {
                "key": "plants",
                "type": "boolean",
                "description": "Download plants OSM feature.",
            },
            {
                "key": "coastlines",
                "type": "boolean",
                "description": "Download coastlines OSM feature.",
            },
        ],
    },
    {
        "name": "population",
        "displayName": "Population",
        "description": "Population data source and reference year.",
        "parameters": [
            {
                "key": "population_source",
                "type": "string",
                "description": "Population source (worldpop, file, or 0).",
            },
            {
                "key": "population_year",
                "type": "integer",
                "description": "WorldPop reference year.",
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
                "description": "Protected areas source (WDPA or file).",
            },
            {
                "key": "protected_areas_filename",
                "type": "string",
                "description": "Protected areas filename. The file should be in (EPSG:4326).",
            },
        ],
    },
    {
        "name": "forest_density",
        "displayName": "Forest Density",
        "description": "Optional forest density exclusion layer.",
        "parameters": [
            {
                "key": "forest_density_source",
                "type": "source",
                "description": "Use 0 to disable or provide a forest-density source.",
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
        "description": "Additional calculations option. Used as criterias in exclusion script.",
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
        "name": "weather",
        "displayName": "Weather data",
        "description": "Weather data settings.",
        "parameters": [
            {
                "key": "weather_external_data_path",
                "type": "string",
                "description": "Optional external weather data directory.",
            },
            {
                "key": "input_area",
                "type": "string",
                "description": "Area used to create energy profiles.",
            },
            {
                "key": "weather_year",
                "type": "number",
                "description": "Weather dataset year.",
            },
            {
                "key": "weather_data_extend",
                "type": "string",
                "description": "Weather download extent mode.",
            },
            {
                "key": "weather_data_geo_bounds",
                "type": "mapping",
                "description": "Geographical bounds used when geo_bounds is selected.",
            },
            {
                "key": "weather_bias_correction",
                "type": "mapping",
                "description": "Bias-correction toggles by technology.",
            },
            {
                "key": "weather_bias_range",
                "type": "array",
                "description": "Minimum and maximum bias-correction factors.",
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
            {
                "key": "projection_manual",
                "type": "string",
                "description": "Optional manual projection override.",
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
                "type": "mapping",
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
                "key": "north_facing_pixels",
                "type": "number",
                "description": "Enable north-facing pixel exclusion.",
            },
            {
                "key": "max_population",
                "type": "number",
                "description": "Maximum population per pixel.",
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
                "description": "Technology derate factor (e.g. 0.95). Used in computing of energy profiles.",
            },
        ],
    },
    {
        "name": "wind_groups",
        "displayName": "Wind Resource Groups",
        "description": "Wind speed thresholds per resource group.",
        "parameters": [
            {
                "key": "rg_thr",
                "type": "mapping",
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
            {
                "key": "projection_manual",
                "type": "string",
                "description": "Optional manual projection override.",
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
                "type": "mapping",
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
                "key": "north_facing_pixels",
                "type": "number",
                "description": "Enable north-facing pixel exclusion.",
            },
            {
                "key": "max_population",
                "type": "number",
                "description": "Maximum population per pixel.",
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
                "key": "rg_thr",
                "type": "mapping",
                "description": "Solar resource group thresholds (kWh/m2/yr).",
            },
        ],
    },
]

CONFIG_SNAKEMAKE_STAGE_FLAGS: List[Dict[str, str]] = [
    {
        "key": "spatial_data_prep",
        "label": "Spatial Data Preparation",
        "description": "Clip and harmonise spatial inputs.",
    },
    {
        "key": "exclusion",
        "label": "Land Exclusion",
        "description": "Run Exclusion.py to derive available land.",
    },
    {
        "key": "suitability",
        "label": "Suitability",
        "description": "Execute suitability.py to grade resources.",
    },
    {
        "key": "weather_data_prep",
        "label": "Weather Data Prep",
        "description": "Prepare atlite-ready weather cut-outs.",
    },
    {
        "key": "weather_bias_adjust",
        "label": "Weather Bias Adjust",
        "description": "Apply bias correction to weather data.",
    },
    {
        "key": "energy_profiles",
        "label": "Energy Profiles",
        "description": "Generate energy profile time series.",
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
            {
                "key": "weather_years",
                "type": "string",
                "description": (
                    "Weather years to process. Accepts a single year [2015], "
                    "comma-separated years [2015,2020], or a range [2015*2020]."
                ),
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
                "type": "array",
                "description": "Region names for the run.",
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
    {
        "name": "stage_flags",
        "displayName": "Stage Toggles",
        "description": "Enable or disable individual workflow stages.",
        "parameters": [
            {
                "key": stage["key"],
                "type": "boolean",
                "label": stage["label"],
                "description": stage["description"],
            }
            for stage in CONFIG_SNAKEMAKE_STAGE_FLAGS
        ],
    },
]


def stringify_list_value(value: Any) -> str:
    """Return a comma-separated string representation for list-like values."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


def stringify_mapping_value(value: Any) -> str:
    """Return a readable string for mapping structures."""
    if isinstance(value, Mapping):
        pairs = []
        for key, item in value.items():
            if isinstance(item, list):
                list_repr = ", ".join(repr(elem) for elem in item)
                pairs.append(f"{key}: [{list_repr}]")
            elif item is None:
                pairs.append(f"{key}: null")
            else:
                pairs.append(f"{key}: {repr(item)}")
        return "\n".join(pairs)
    if value is None:
        return ""
    return str(value)


def parse_mapping_text(text: str) -> Any:
    """Best-effort parsing of mapping text coming from the UI."""
    stripped = text.strip()
    if not stripped:
        return {}
    # Try JSON first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, Mapping):
            return parsed
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # Fallback to Python literal evaluation
    try:
        parsed_literal = ast.literal_eval(text)
        if isinstance(parsed_literal, Mapping):
            return parsed_literal
    except (ValueError, SyntaxError):
        pass
    # Attempt ruamel round-trip loader if available
    if YAML_RT is not None:
        try:
            yaml_rt = YAML(typ="rt")
            parsed_yaml = yaml_rt.load(text)
            if isinstance(parsed_yaml, Mapping):
                return parsed_yaml
        except Exception:
            pass
    simple_mapping: Dict[str, Any] = {}
    for line in stripped.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        key, sep, raw = stripped_line.partition(":")
        if not sep:
            return text
        key = key.strip()
        raw_value = raw.strip()
        if "#" in raw_value:
            raw_value = raw_value.split("#", 1)[0].strip()
        if not key:
            return text
        if not raw_value:
            simple_mapping[key] = None
            continue
        lowered = raw_value.lower()
        if lowered == "null":
            simple_mapping[key] = None
            continue
        try:
            simple_mapping[key] = ast.literal_eval(raw_value)
        except Exception:
            simple_mapping[key] = raw_value
    if simple_mapping:
        return simple_mapping
    return text


def cast_value(param_type: str, value: Any) -> Any:
    """
    Cast a raw value according to the configuration parameter type notation.

    Supports the existing scalar types and list subtypes expressed as
    ``list:<subtype>`` (e.g. ``list:number``).
    """
    if not isinstance(param_type, str):
        return value

    kind = param_type.strip()

    if kind.startswith("list:"):
        subtype = (kind.split(":", 1)[1] or "string").strip().lower()

        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, (list, tuple)):
            items = []
            for item in value:
                text = str(item).strip()
                if text:
                    items.append(text)
        elif value in (None, ""):
            items = []
        else:
            text = str(value).strip()
            items = [text] if text else []

        if subtype in {"number", "float"}:
            numbers: List[float] = []
            for item in items:
                try:
                    numbers.append(float(item))
                except ValueError as exc:
                    raise ValueError(f"'{item}' is not a valid number") from exc
            return numbers

        if subtype == "integer":
            integers: List[int] = []
            for item in items:
                try:
                    integers.append(int(float(item)))
                except ValueError as exc:
                    raise ValueError(f"'{item}' is not a valid integer") from exc
            return integers

        return items

    if kind == "number":
        if isinstance(value, (int, float)):
            return value
        if value in (None, ""):
            return None
        text = str(value).strip()
        if not text:
            return None
        return float(text)

    if kind == "integer":
        if isinstance(value, int):
            return value
        if value in (None, ""):
            return None
        text = str(value).strip()
        if not text:
            return None
        return int(float(text))

    if kind == "mapping":
        if isinstance(value, Mapping):
            converted: Dict[str, Any] = {}
            for key, item in value.items():
                if isinstance(item, MutableSequence) and not isinstance(
                    item, (str, bytes, bytearray)
                ):
                    converted[key] = list(item)
                else:
                    converted[key] = item
            return converted
        if isinstance(value, str):
            parsed = parse_mapping_text(value)
            return parsed
        return value

    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    if kind == "source":
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip()
        try:
            return int(text)
        except ValueError:
            return text

    if isinstance(value, str):
        return value
    return "" if value is None else str(value)


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
    if param_type == "boolean":
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes"}
        if value is None:
            return False
        return bool(value)
    if param_type in {"number", "integer"}:
        if isinstance(value, (int, float)):
            return value
        if value is None or value == "":
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if param_type == "integer":
            return int(numeric)
        return int(numeric) if numeric.is_integer() else numeric
    if param_type == "mapping":
        if isinstance(value, Mapping):
            return deepcopy(value)
        if isinstance(value, str):
            parsed = cast_value("mapping", value)
            if isinstance(parsed, Mapping):
                return parsed
            return {}
        return {}
    if param_type == "source":
        return "" if value is None else str(value)
    if param_type.startswith("list:"):
        return stringify_list_value(value)
    if param_type == "array":
        if isinstance(value, (list, dict)):
            return value
        return _format_array_value(value)
    # treat as string by default
    if value is None:
        return ""
    return str(value)


def _infer_param_type(value: Any) -> str:
    if isinstance(value, Mapping):
        return "mapping"
    if isinstance(value, list):
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
            if key not in data:
                continue
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

        if params:
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
        sections.append(
            {
                "name": "additional_parameters",
                "displayName": "Additional Parameters",
                "description": "Parameters discovered in the active YAML file.",
                "parameters": extra_params,
            }
        )
    return sections


def _load_sections_from_yaml(
    path: Path,
    definitions: List[Dict[str, Any]],
    fallback: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    yaml_rt = YAML_RT
    if yaml_rt is None or not path.exists():
        return deepcopy(fallback)

    try:
        with path.open("r", encoding="utf-8") as stream:
            data = yaml_rt.load(stream) or CommentedMap()
        if not isinstance(data, Mapping):
            raise ValueError("Unexpected YAML structure")
    except Exception:
        return deepcopy(fallback)

    return _build_sections_from_data(dict(data), definitions)


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


def load_offshore_sections() -> List[Dict[str, Any]]:
    """Load an initialized offshore configuration using inferred field types."""
    return _load_sections_from_yaml(OFFSHORE_PATH, [], [])


def load_suitability_sections() -> List[Dict[str, Any]]:
    """Load suitability settings; nested structures are inferred as mappings."""
    return _load_sections_from_yaml(SUITABILITY_PATH, [], [])


def load_snakemake_sections() -> List[Dict[str, Any]]:
    fallback = _build_sections_from_data(
        {  # dummy data, user must specify
            "snakefile": "snakefile_dummy",
            "cores": "4",
            "study_region_name": "dummy_region",
            "scenario": "dummy",
            "technologies": ["dummy1", "dumm2"],
            "weather_years": "2015",
            **{stage["key"]: True for stage in CONFIG_SNAKEMAKE_STAGE_FLAGS},
        },
        CONFIG_SNAKEMAKE_SECTION_DEFINITIONS,
    )
    if YAML_RT is None or not SNAKEMAKE_PATH.exists():
        return fallback
    try:
        with SNAKEMAKE_PATH.open("r", encoding="utf-8") as stream:
            data = YAML_RT.load(stream) or CommentedMap()
        if not isinstance(data, Mapping):
            raise ValueError("Unexpected YAML structure")
        flattened = dict(data)
        stages = flattened.pop("stages", {})
        if isinstance(stages, Mapping):
            flattened.update(stages)
        return _build_sections_from_data(
            flattened, CONFIG_SNAKEMAKE_SECTION_DEFINITIONS
        )
    except Exception:
        return deepcopy(fallback)


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


def validate_configuration_documents(
    documents: Mapping[str, Any],
    configs_path: Path = CONFIGS_PATH,
) -> List[Dict[str, str]]:
    """Validate related active configuration documents.

    Each issue contains ``severity``, ``file``, ``key``, and ``message`` so UI
    clients can display it and navigate back to the affected setting.
    """
    issues: List[Dict[str, str]] = []

    def add(severity: str, file_name: str, key: str, message: str) -> None:
        issues.append(
            {"severity": severity, "file": file_name, "key": key, "message": message}
        )

    def as_mapping(file_name: str) -> Mapping[str, Any]:
        value = documents.get(file_name, {})
        return value if isinstance(value, Mapping) else {}

    def enabled(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def nonempty(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (Mapping, Sequence)):
            return bool(value)
        return True

    config = as_mapping("config.yaml")
    if "config.yaml" in documents:
        if not nonempty(config.get("study_region_name")):
            add(
                "error",
                "config.yaml",
                "study_region_name",
                "Study region name is required.",
            )
        country_code = str(config.get("country_code") or "").strip()
        if len(country_code) != 3 or not country_code.isalpha():
            add(
                "error",
                "config.yaml",
                "country_code",
                "Country code must contain exactly three letters.",
            )

        custom_area = nonempty(config.get("custom_study_area_filename"))
        gadm_name = nonempty(config.get("GADM_region_name"))
        gadm_level = nonempty(config.get("GADM_level"))
        if not custom_area and not (gadm_name and gadm_level):
            add(
                "error",
                "config.yaml",
                "GADM_region_name",
                "Provide both GADM region name and level, or a custom study-area file.",
            )
        elif custom_area and (gadm_name or gadm_level):
            add(
                "warning",
                "config.yaml",
                "custom_study_area_filename",
                "The custom study area overrides the configured GADM region.",
            )

        osm_source = str(config.get("OSM_source") or "").strip().lower()
        if osm_source not in {"overpass", "geofabrik"}:
            add(
                "error",
                "config.yaml",
                "OSM_source",
                "OSM source must be 'overpass' or 'geofabrik'.",
            )
        elif osm_source == "geofabrik" and not nonempty(config.get("OSM_folder_name")):
            add(
                "error",
                "config.yaml",
                "OSM_folder_name",
                "A Geofabrik folder name is required when using Geofabrik.",
            )

        weather_extend = str(config.get("weather_data_extend") or "").strip().lower()
        if weather_extend and weather_extend not in {
            "study_region",
            "geo_bounds",
            "country_code",
        }:
            add(
                "error",
                "config.yaml",
                "weather_data_extend",
                "Weather extent must be study_region, geo_bounds, or country_code.",
            )
        if weather_extend == "geo_bounds":
            bounds = config.get("weather_data_geo_bounds")
            required_bounds = ("west", "south", "east", "north")
            if not isinstance(bounds, Mapping) or any(
                not nonempty(bounds.get(k)) for k in required_bounds
            ):
                add(
                    "error",
                    "config.yaml",
                    "weather_data_geo_bounds",
                    "Geo bounds require west, south, east, and north values.",
                )
            else:
                try:
                    west, south, east, north = (
                        float(bounds[k]) for k in required_bounds
                    )
                    valid_order = west < east and south < north
                    valid_range = (
                        -180 <= west <= 180
                        and -180 <= east <= 180
                        and -90 <= south <= 90
                        and -90 <= north <= 90
                    )
                except (TypeError, ValueError):
                    valid_order = valid_range = False
                if not valid_order or not valid_range:
                    add(
                        "error",
                        "config.yaml",
                        "weather_data_geo_bounds",
                        "Geo bounds must be numeric, ordered, and within valid longitude/latitude ranges.",
                    )

        if enabled(config.get("solar_atlas")):
            if not nonempty(config.get("country_name_solar_atlas")):
                add(
                    "error",
                    "config.yaml",
                    "country_name_solar_atlas",
                    "Country name is required when Solar Atlas is enabled.",
                )
            if not nonempty(config.get("solar_atlas_measure")):
                add(
                    "error",
                    "config.yaml",
                    "solar_atlas_measure",
                    "A Solar Atlas measure is required when Solar Atlas is enabled.",
                )

    snakemake = as_mapping("snakemake.yaml")
    if "snakemake.yaml" in documents:
        if not nonempty(snakemake.get("study_region_name")):
            add(
                "error",
                "snakemake.yaml",
                "study_region_name",
                "Select at least one study region.",
            )
        if not nonempty(snakemake.get("scenario")):
            add("error", "snakemake.yaml", "scenario", "Scenario name is required.")
        if not nonempty(snakemake.get("snakefile")):
            add("error", "snakemake.yaml", "snakefile", "Snakefile path is required.")
        technologies = snakemake.get("technologies", [])
        if isinstance(technologies, str):
            technologies = [technologies]
        if not isinstance(technologies, Sequence) or isinstance(
            technologies, (bytes, bytearray)
        ):
            technologies = []
        technologies = [
            str(value).strip() for value in technologies if str(value).strip()
        ]
        if not technologies:
            add(
                "error",
                "snakemake.yaml",
                "technologies",
                "Select at least one technology.",
            )
        for technology in technologies:
            file_name = f"{technology}.yaml"
            if (
                file_name not in documents
                and not (Path(configs_path) / file_name).exists()
            ):
                add(
                    "error",
                    "snakemake.yaml",
                    "technologies",
                    f"Technology '{technology}' has no matching {file_name} configuration.",
                )

        try:
            cores = int(snakemake.get("cores", 0))
        except (TypeError, ValueError):
            cores = 0
        if cores < 1:
            add("error", "snakemake.yaml", "cores", "Core count must be at least 1.")

        stages = snakemake.get("stages", {})
        if not isinstance(stages, Mapping):
            add("error", "snakemake.yaml", "stages", "Stages must be a YAML mapping.")
            stages = {}
        dependencies = {
            "exclusion": ("spatial_data_prep",),
            "suitability": ("exclusion",),
            "energy_profiles": (
                "suitability",
                "weather_data_prep",
                "weather_bias_adjust",
            ),
        }
        for stage, required in dependencies.items():
            if not enabled(stages.get(stage)):
                continue
            missing = [name for name in required if not enabled(stages.get(name))]
            if missing:
                add(
                    "warning",
                    "snakemake.yaml",
                    stage,
                    f"Stage '{stage}' requires: {', '.join(missing)}.",
                )
        weather_stages = any(
            enabled(stages.get(name))
            for name in ("weather_data_prep", "weather_bias_adjust", "energy_profiles")
        )
        weather_years = snakemake.get("weather_years")
        if weather_stages and weather_years in (None, "", []):
            add(
                "error",
                "snakemake.yaml",
                "weather_years",
                "Select at least one weather year for the enabled weather stages.",
            )

    order = {"error": 0, "warning": 1}
    return sorted(
        issues,
        key=lambda issue: (
            order.get(issue["severity"], 2),
            issue["file"],
            issue["key"],
            issue["message"],
        ),
    )


# ---------------------------------------------------------------------------
# Round-trip YAML editing helpers (ruamel.yaml)
# ---------------------------------------------------------------------------


def round_trip_available() -> bool:
    """Return ``True`` when ruamel.yaml round-trip editing is available."""
    return YAML_RT is not None


def _ensure_round_trip_yaml() -> YAML:
    if YAML_RT is None:
        raise RuntimeError(
            "ruamel.yaml is required for comment-preserving editing. Install with `pip install ruamel.yaml`."
        )
    return YAML_RT


def load_config_document(path: Path) -> CommentedMap:
    """
    Load a YAML document with ruamel.yaml while preserving order, formatting, and comments.

    Returns a :class:`ruamel.yaml.comments.CommentedMap` ready to be mutated in place.
    """
    yaml_rt = _ensure_round_trip_yaml()
    if not path.exists():
        return CommentedMap()
    with path.open("r", encoding="utf-8") as stream:
        data = yaml_rt.load(stream)
    if data is None:
        return CommentedMap()
    if isinstance(data, CommentedMap):
        return data
    if isinstance(data, Mapping):
        cm = CommentedMap()
        for key, value in data.items():
            cm[key] = value
        return cm
    raise ValueError(
        f"Expected a mapping at the root of {path}, received {type(data)!r}."
    )


def _build_nested_mapping(keys: Sequence[str], value: Any) -> CommentedMap:
    container = CommentedMap()
    if not keys:
        return container
    head, *tail = keys
    if tail:
        container[head] = _build_nested_mapping(tail, value)
    else:
        container[head] = value
    return container


def _assign_sequence(target: Any, value: Sequence[Any]) -> MutableSequence[Any]:
    seq_values = list(value)
    if isinstance(target, MutableSequence):
        target[:] = seq_values
        return target
    if CommentedSeq is List:
        return list(seq_values)
    new_seq = CommentedSeq(seq_values)
    return new_seq


def deep_update(original: CommentedMap, updates: Mapping[str, Any]) -> CommentedMap:
    """
    Recursively merge *updates* into *original* while keeping existing keys,
    indentation, and comments intact.
    """
    for key, value in updates.items():
        if isinstance(value, Mapping):
            existing = original.get(key)
            if not isinstance(existing, Mapping):
                existing = CommentedMap()
                original[key] = existing
            deep_update(existing, value)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            original[key] = _assign_sequence(original.get(key), value)
        else:
            original[key] = value
    return original


def _get_path(container: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = container
    for key in path:
        if isinstance(current, Mapping) and key in current:
            current = current[key]
        else:
            return None
    return current


class RoundTripConfigStore:
    """
    Helper that wraps ruamel.yaml for comment-preserving load/edit/save cycles.

    Each ``set_value`` call only touches the targeted field; everything else in the
    document (comments, formatting, key order) stays untouched.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.yaml = _ensure_round_trip_yaml()
        self.document: CommentedMap = load_config_document(self.path)

    def get_value(self, dotted_path: str) -> Any:
        keys = [part for part in dotted_path.split(".") if part]
        if not keys:
            return self.document
        return _get_path(self.document, keys)

    def set_value(self, dotted_path: str, value: Any) -> None:
        keys = [part for part in dotted_path.split(".") if part]
        if not keys:
            raise ValueError(
                "dotted_path must reference a key (e.g. 'general.country_code')."
            )
        updates = _build_nested_mapping(keys, value)
        deep_update(self.document, updates)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as stream:
            self.yaml.dump(self.document, stream)


def sections_to_mapping(sections: List[Dict[str, Any]]) -> MutableMapping[str, Any]:
    """
    Convert section dictionaries into a flat mapping suitable for ``deep_update``.

    Parameter keys become top-level YAML keys. Values are used as-is.
    """
    if CommentedMap is dict:
        data: MutableMapping[str, Any] = {}
    else:
        data = CommentedMap()  # type: ignore[call-arg]
    for section in sections:
        for param in section.get("parameters", []):
            value = param.get("value")
            param_type = param.get("type", "string")
            if isinstance(param_type, str):
                if param_type.startswith("list:"):
                    value = cast_value(param_type, value)
                elif param_type == "mapping":
                    value = cast_value("mapping", value)
                elif param_type in {"integer", "source"}:
                    value = cast_value(param_type, value)
            mapping_key = param["key"]
            data[mapping_key] = value
    return data


def save_sections_round_trip(path: Path, sections: List[Dict[str, Any]]) -> str:
    """
    Persist *sections* into *path* while keeping formatting and comments intact.

    Returns the rendered YAML text after the save so callers can refresh UI state.
    """
    store = RoundTripConfigStore(Path(path))
    updates = sections_to_mapping(sections)
    deep_update(store.document, updates)
    store.save()
    return Path(path).read_text(encoding="utf-8")


def save_mapping_round_trip(path: Path, updates: Mapping[str, Any]) -> str:
    """Merge an already structured mapping into a YAML document and save it."""
    store = RoundTripConfigStore(Path(path))
    deep_update(store.document, updates)
    store.save()
    return Path(path).read_text(encoding="utf-8")


def demo_tkinter_round_trip_editor(config_path: Path = CONFIG_PATH) -> None:
    """
    Minimal Tkinter demo that wires ``RoundTripConfigStore`` variables to widgets.

    Edit the fields and hit "Save" to persist the changes while retaining the YAML
    file's comments and formatting.
    """

    import tkinter as tk
    from tkinter import ttk, messagebox

    store = RoundTripConfigStore(config_path)

    root = tk.Tk()
    root.title("Configuration Editor (ruamel.yaml demo)")

    main = ttk.Frame(root, padding=12)
    main.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    # Scalar example: general.country_code
    ttk.Label(main, text="general.country_code:").grid(row=0, column=0, sticky="w")
    country_var = tk.StringVar(value=str(store.get_value("general.country_code") or ""))

    def _on_country_change(*_args: Any) -> None:
        text = country_var.get().strip() or None
        store.set_value("general.country_code", text)

    country_var.trace_add("write", _on_country_change)
    ttk.Entry(main, textvariable=country_var, width=24).grid(
        row=0, column=1, sticky="ew", padx=(6, 0)
    )

    # List example: fclass.roads (comma-separated in the UI)
    ttk.Label(main, text="fclass.roads:").grid(row=1, column=0, sticky="w", pady=(6, 0))
    roads_value = store.get_value("fclass.roads") or []
    if isinstance(roads_value, Sequence) and not isinstance(roads_value, str):
        display_roads = ", ".join(str(item) for item in roads_value)
    else:
        display_roads = str(roads_value or "")
    roads_var = tk.StringVar(value=display_roads)

    def _on_roads_change(*_args: Any) -> None:
        tokens = [
            token.strip() for token in roads_var.get().split(",") if token.strip()
        ]
        store.set_value("fclass.roads", tokens)

    roads_var.trace_add("write", _on_roads_change)
    ttk.Entry(main, textvariable=roads_var, width=48).grid(
        row=1, column=1, sticky="ew", padx=(6, 0), pady=(6, 0)
    )

    # Null example: fclass.railways (toggle between blank and 'null')
    ttk.Label(main, text="fclass.railways:").grid(
        row=2, column=0, sticky="w", pady=(6, 0)
    )
    railways_var = tk.StringVar(value=str(store.get_value("fclass.railways") or ""))

    def _on_railways_change(*_args: Any) -> None:
        raw = railways_var.get().strip()
        store.set_value("fclass.railways", None if raw == "" else raw)

    railways_var.trace_add("write", _on_railways_change)
    ttk.Entry(main, textvariable=railways_var, width=24).grid(
        row=2, column=1, sticky="ew", padx=(6, 0), pady=(6, 0)
    )

    # Save button that writes the YAML file using ruamel.yaml
    def _save_and_notify() -> None:
        try:
            store.save()
        except Exception as exc:  # pragma: no cover - UI feedback
            messagebox.showerror("Save failed", str(exc))
        else:
            messagebox.showinfo("Saved", f"Configuration written to {store.path}")

    ttk.Button(main, text="Save", command=_save_and_notify).grid(
        row=3, column=0, columnspan=2, pady=(12, 0)
    )
    main.columnconfigure(1, weight=1)

    root.mainloop()
