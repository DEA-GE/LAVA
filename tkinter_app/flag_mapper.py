"""
Helpers to convert between UI-friendly boolean values and the numeric 0/1 flags
used inside the YAML configuration.
"""

from __future__ import annotations

from typing import Any

# Numeric flag keys in YAML that should appear as booleans in the UI
NUMERIC_FLAG_KEYS = {
    # OSM / layers toggles
    "railways",
    "roads",
    "airports",
    "waterbodies",
    "military",
    "substations",
    "transmission_lines",
    "generators",
    "plants",
    "coastlines",
    # Atlases / rasters toggles
    "wind_atlas",
    "solar_atlas",
    "forest_density",
    # Computation step toggles
    "compute_substation_proximity",
    "compute_road_proximity",
    "compute_terrain_ruggedness",
    # Behavior flags
    "force_osm_download",
    "heat_demand_constant",
}


def make_path(section_name: str, key: str) -> str:
    """Return a dotted path (section.key)."""
    return f"{section_name}.{key}" if section_name else key


def is_numeric_flag(param_path: str) -> bool:
    """Return True when the parameter should be stored as numeric 0/1."""
    return param_path.split(".")[-1] in NUMERIC_FLAG_KEYS


def ui_bool_to_numeric(param_path: str, ui_value: bool) -> int | bool:
    """Convert UI booleans to 0/1 when needed."""
    if is_numeric_flag(param_path):
        return 1 if ui_value else 0
    return ui_value


def yaml_numeric_to_ui_bool(param_path: str, yaml_value: Any) -> Any:
    """Convert YAML numeric flags (0/1) back into booleans for the UI."""
    if not is_numeric_flag(param_path):
        return yaml_value
    return yaml_value in (1, "1", True, "true", "True")

