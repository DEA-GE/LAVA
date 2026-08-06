"""Tkinter-based translation of the Python Script Manager interface."""

from __future__ import annotations
import ast
import html
import importlib.util
import json
import os
import queue
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping as MappingABC
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
import keyword
import re

from ruamel.yaml.comments import CommentedMap, CommentedSeq
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
from PIL import Image
import folium
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from branca.element import MacroElement, Template

try:  # Optional ttkbootstrap theming
    from ttkbootstrap import Style  # type: ignore

    HAVE_TTKBOOTSTRAP = True
except Exception:  # pragma: no cover - optional dependency
    HAVE_TTKBOOTSTRAP = False
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
CONFIGS_DIR = PARENT_DIR / "configs"
CONFIG_ADVANCED_SETTINGS_PATH = (
    CONFIGS_DIR / "advanced_settings" / "advanced_data_prep_settings.yaml"
)
SNAKEMAKE_GLOBAL_PATH = PARENT_DIR / "snakemake" / "Snakefile"
RUN_HISTORY_PATH = PARENT_DIR / "logs" / "ui_run_history.json"
RUN_LOG_DIR = PARENT_DIR / "logs" / "ui_runs"
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))
if str(PARENT_DIR) not in sys.path:
    sys.path.append(str(PARENT_DIR))
from flag_mapper import make_path, ui_bool_to_numeric, yaml_numeric_to_ui_bool  # type: ignore  # noqa: E402
from data_loader import (  # type: ignore  # noqa: E402
    CONFIG_SNAKEMAKE_STAGE_FLAGS,
    cast_value,
    round_trip_available,
    load_initial_sections,
    load_offshore_sections,
    load_onshore_sections,
    load_solar_sections,
    load_snakemake_sections,
    load_sample_results,
    save_mapping_round_trip,
    save_sections_round_trip,
    stringify_list_value,
    validate_configuration_documents,
)
from utils.initialization import (  # noqa: E402
    available_example_countries,
    initialize_config_templates,
    preview_config_templates,
)

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None
SNAKEFILE_TEMPLATE = """"""
SNAKEMAKE_STAGE_KEYS = [stage["key"] for stage in CONFIG_SNAKEMAKE_STAGE_FLAGS]
REQUIRED_ACTIVE_CONFIGS = (
    "config.yaml",
    "onshorewind.yaml",
    "solar.yaml",
)
OPTIONAL_ACTIVE_CONFIGS = (
    "suitability.yaml",
    "config_snakemake.yaml",
)

CONFIGURATION_CATEGORIES = (
    "General",
    "Technology exclusions",
    "Suitability",
    "Workflow",
    "Advanced settings",
    "Snakefile",
)

DOCUMENT_CATEGORIES = {
    "config.yaml": "General",
    "onshorewind.yaml": "Technology exclusions",
    "solar.yaml": "Technology exclusions",
    "offshorewind.yaml": "Technology exclusions",
    "suitability.yaml": "Suitability",
    "config_snakemake.yaml": "Workflow",
    "advanced_data_prep_settings.yaml": "Advanced settings",
    "Snakefile": "Snakefile",
}

PARAMETER_CHOICES: Dict[str, List[str]] = {
    "landcover_source": ["openeo", "file"],
    "OSM_source": ["overpass", "geofabrik"],
    "population_source": ["worldpop", "file"],
    "protected_areas_source": ["WDPA", "file"],
    "input_area": ["resource_grades", "available_land", "study_region"],
    "weather_data_extend": ["study_region", "geo_bounds", "country_code"],
    "technology": ["onshorewind", "solar", "offshorewind"],
}

PARAMETER_PICKERS: Dict[str, str] = {
    "custom_study_area_filename": "filename",
    "landcover_filename": "filename",
    "DEM_filename": "filename",
    "protected_areas_filename": "filename",
    "forest_density_filename": "filename",
    "model_areas_filename": "filename",
    "weather_external_data_path": "directory",
    "additional_exclusion_polygons_folder_name": "folder_name",
    "additional_exclusion_rasters_folder_name": "folder_name",
    "OSM_folder_name": "folder_name",
    "snakefile": "project_file",
}

PARAMETER_UNITS: Dict[str, str] = {
    "deployment_density": "MW/km2",
    "resolution_manual": "m",
    "resolution_landcover": "degrees",
    "max_elevation": "m",
    "max_slope": "degrees",
    "railways_buffer": "m",
    "roads_buffer": "m",
    "airports_buffer": "m",
    "waterbodies_buffer": "m",
    "military_buffer": "m",
    "coastlines_buffer": "m",
    "protectedAreas_buffer": "m",
    "transmission_lines_buffer": "m",
    "generators_buffer": "m",
    "plants_buffer": "m",
    "substations_inclusion_buffer": "m",
    "transmission_inclusion_buffer": "m",
    "roads_inclusion_buffer": "m",
    "min_wind_speed": "m/s",
    "max_wind_speed": "m/s",
    "min_solar_production": "kWh/kW/year",
    "max_solar_production": "kWh/kW/year",
    "min_area_distributed": "km2",
    "min_area_rg": "km2",
    "weather_year": "year",
    "population_year": "year",
}


def missing_active_configs(configs_dir: Path = CONFIGS_DIR) -> List[Path]:
    """Return initialized configuration files required by the main UI."""
    return [
        configs_dir / name
        for name in REQUIRED_ACTIVE_CONFIGS
        if not (configs_dir / name).exists()
    ]


def missing_optional_configs(configs_dir: Path = CONFIGS_DIR) -> List[Path]:
    """Return optional configuration files that may be needed by later stages."""
    return [
        configs_dir / name
        for name in OPTIONAL_ACTIVE_CONFIGS
        if not (configs_dir / name).exists()
    ]


def extract_yaml_comment_hints(yaml_text: str) -> Dict[str, str]:
    """Extract per-key help verbatim from YAML comments without inventing examples."""
    hints: Dict[str, str] = {}
    active_key = re.compile(r"^\s*([A-Za-z_][\w.-]*)\s*:[^#]*#\s*(.+?)\s*$")
    commented_value = re.compile(r"^\s*#\s*([A-Za-z_][\w.-]*)\s*:\s*(.+?)\s*$")
    for line in yaml_text.splitlines():
        match = active_key.match(line)
        if match:
            key, comment = match.groups()
            if comment and key not in hints:
                hints[key] = comment.strip()
            continue
        match = commented_value.match(line)
        if match:
            key, example = match.groups()
            if example and key not in hints:
                hints[key] = example.strip()
    return hints


def format_yaml_comment_hint(comment: str) -> str:
    """Move leading bracket metadata before the concise example label."""
    text = comment.strip()
    metadata_match = re.match(r"^((?:\[[^\]]+\]\s*)+)(.*)$", text)
    if not metadata_match:
        return f"Example: {text}"
    metadata_text, remainder = metadata_match.groups()
    metadata = " ".join(re.findall(r"\[[^\]]+\]", metadata_text))
    remainder = remainder.strip()
    return f"{metadata} Example: {remainder}" if remainder else metadata


class Tooltip:
    """Small delayed tooltip for longer setting descriptions."""

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text.strip()
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._window: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event: Optional[tk.Event] = None) -> None:
        self._cancel()
        if self.text:
            self._after_id = self.widget.after(self.delay_ms, self._show)

    def _show(self) -> None:
        self._after_id = None
        if not self.widget.winfo_exists() or self._window is not None:
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.attributes("-topmost", True)
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        window.geometry(f"+{x}+{y}")
        tk.Label(
            window,
            text=self.text,
            background="#FFFCE8",
            foreground="#202020",
            relief="solid",
            borderwidth=1,
            justify="left",
            wraplength=420,
            padx=7,
            pady=5,
        ).pack()
        self._window = window

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _hide(self, _event: Optional[tk.Event] = None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None


class TextSyntaxHighlighter:
    """Lightweight syntax highlighting for Tkinter ``Text`` widgets."""

    _TAG_STYLES: Dict[str, Dict[str, Any]] = {
        "comment": {"foreground": "#6A9955"},
        "keyword": {"foreground": "#C586C0"},
        "string": {"foreground": "#CE9178"},
        "number": {"foreground": "#B5CEA8"},
        "key": {"foreground": "#2F7ACC"},
        "boolean": {"foreground": "#4FC1FF"},
        "decorator": {"foreground": "#DCDCAA"},
    }
    _PY_KEYWORD_PATTERN = re.compile(
        r"\b(?:" + "|".join(sorted(re.escape(word) for word in keyword.kwlist)) + r")\b"
    )
    _PY_STRING_PATTERN = re.compile(
        r"""('''.*?'''|\"\"\".*?\"\"\"|'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")""",
        re.DOTALL,
    )
    _YAML_STRING_PATTERN = re.compile(r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")
    _LANGUAGE_RULES: Dict[str, List[Tuple[str, re.Pattern[str], int]]] = {
        "yaml": [
            ("comment", re.compile(r"#.*", re.MULTILINE), 0),
            ("key", re.compile(r"(?m)^\s*([^:\n]+)(?=\s*:)"), 1),
            ("string", _YAML_STRING_PATTERN, 0),
            ("boolean", re.compile(r"(?i)\b(?:true|false|yes|no|null|on|off)\b"), 0),
            ("number", re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?"), 0),
        ],
        "python": [
            ("comment", re.compile(r"#.*", re.MULTILINE), 0),
            ("decorator", re.compile(r"(?m)^\s*@[\w\.]+"), 0),
            ("string", _PY_STRING_PATTERN, 0),
            ("keyword", _PY_KEYWORD_PATTERN, 0),
            ("number", re.compile(r"\b\d+(?:\.\d+)?\b"), 0),
        ],
        "plain": [],
    }
    _DEBOUNCE_MS = 120

    def __init__(self, widget: tk.Text, language: str = "plain") -> None:
        self.widget = widget
        self.language = language if language in self._LANGUAGE_RULES else "plain"
        self._after_id: Optional[str] = None
        self._configured_tags: set[str] = set()
        self._setup_tags()
        for sequence in (
            "<KeyRelease>",
            "<<Paste>>",
            "<<Cut>>",
            "<<Undo>>",
            "<<Redo>>",
        ):
            widget.bind(sequence, self._schedule_refresh, add="+")
        widget.bind("<FocusIn>", self._schedule_refresh, add="+")
        widget.bind("<Expose>", self._schedule_refresh, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")
        self.refresh()

    def refresh(self) -> None:
        if not self.widget.winfo_exists():
            return
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._apply_highlight()

    def _setup_tags(self) -> None:
        for tag_name, options in self._TAG_STYLES.items():
            self.widget.tag_configure(tag_name, **options)
            self._configured_tags.add(tag_name)

    def _schedule_refresh(self, _event: Optional[tk.Event] = None) -> None:
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.widget.after(self._DEBOUNCE_MS, self._apply_highlight)

    def _apply_highlight(self) -> None:
        if not self.widget.winfo_exists():
            return
        rules = self._LANGUAGE_RULES.get(self.language, [])
        text = self.widget.get("1.0", "end-1c")
        for tag in self._configured_tags:
            self.widget.tag_remove(tag, "1.0", "end")
        if not text or not rules:
            return
        for tag, pattern, group in rules:
            for match in pattern.finditer(text):
                start_offset = match.start(group)
                end_offset = match.end(group)
                if start_offset == -1 or end_offset == -1:
                    continue
                start_index = f"1.0+{start_offset}c"
                end_index = f"1.0+{end_offset}c"
                self.widget.tag_add(tag, start_index, end_index)

    def _on_destroy(self, _event: Optional[tk.Event] = None) -> None:
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


def _coerce_list_value(param_type: str, value: Any) -> List[Any]:
    """
    Convert raw UI input into a list according to ``list:<subtype>`` typing.

    Returns a best-effort list; invalid numeric entries fall back to trimmed
    string tokens so the caller can surface them back to the user.
    """
    if isinstance(value, (list, tuple)):
        return list(value)

    text = stringify_list_value(value)
    if not text:
        return []

    try:
        parsed = cast_value(param_type, text)
    except ValueError:
        return [item.strip() for item in text.split(",") if item.strip()]

    if isinstance(parsed, list):
        return parsed
    return [parsed]


def _plain_yaml_value(value: Any) -> Any:
    """Convert ruamel container/scalar subclasses into PyYAML-safe values."""
    if isinstance(value, MappingABC):
        return {str(key): _plain_yaml_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, CommentedSeq)):
        return [_plain_yaml_value(item) for item in value]
    if value is None:
        return value
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    return value


def sections_to_yaml(sections: List[Dict[str, Any]]) -> str:
    """Serialize visual sections to the flat structure used by config.yaml."""
    data: Dict[str, Any] = {}
    for section in sections:
        for param in section.get("parameters", []):
            path = make_path(section["name"], param["key"])
            value_type = param.get("type", "string")
            value = param.get("value")
            if value_type == "boolean":
                value = ui_bool_to_numeric(path, bool(value))
            elif value_type.startswith("list:"):
                value = _coerce_list_value(value_type, value)
            elif value_type == "mapping":
                value = cast_value("mapping", value)
            elif value_type in {"integer", "source"}:
                value = cast_value(value_type, value)
            data[param["key"]] = value
    if yaml is not None:
        return yaml.safe_dump(
            _plain_yaml_value(data), sort_keys=False, allow_unicode=True
        )
    return (
        "\n".join(
            f"{key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}"
            for key, value in data.items()
        )
        + "\n"
    )


def rebuild_from_widgets(
    original: Any, registry: Dict[str, tk.Variable], path: str = ""
) -> Any:
    """
    Reconstruct a data structure using the original YAML object as template and
    the Tkinter variable registry for values.
    """
    if isinstance(original, MappingABC):
        result = deepcopy(original)
        for key, value in original.items():
            child_path = f"{path}.{key}" if path else key
            result[key] = rebuild_from_widgets(value, registry, child_path)
        return result

    if isinstance(original, (list, CommentedSeq)):
        var = registry.get(path)
        if var is None:
            return deepcopy(original)
        text = var.get()
        if text is None:
            return type(original)()
        stripped = text.strip()
        if not stripped:
            return type(original)()
        items = [item.strip() for item in stripped.split(",") if item.strip()]
        sample = next((item for item in original if item is not None), None)

        def _convert(item: str) -> Any:
            if sample is None:
                return item
            if isinstance(sample, bool):
                return item.lower() in {"1", "true", "yes", "on"}
            if isinstance(sample, int) and not isinstance(sample, bool):
                try:
                    return int(item)
                except ValueError:
                    return sample
            if isinstance(sample, float):
                try:
                    return float(item)
                except ValueError:
                    return sample
            return item

        converted = [_convert(token) for token in items]
        sequence = type(original)()
        if hasattr(sequence, "extend"):
            sequence.extend(converted)
            return sequence
        return converted

    var = registry.get(path)
    if var is None:
        return original
    value = var.get()
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "" or stripped.lower() == "null":
        return None
    if isinstance(original, bool):
        return stripped.lower() in {"1", "true", "yes", "on"}
    if isinstance(original, int) and not isinstance(original, bool):
        try:
            return int(stripped)
        except ValueError:
            return original
    if isinstance(original, float):
        try:
            return float(stripped)
        except ValueError:
            return original
    return stripped


def yaml_to_sections(
    baseline: List[Dict[str, Any]], yaml_text: str
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """Parse YAML and merge known keys back into the section structure."""
    if not yaml:
        return (
            None,
            "PyYAML is required for raw YAML editing. Install with `pip install PyYAML`.",
        )
    try:
        parsed = yaml.safe_load(yaml_text) or {}
    except Exception as exc:  # pragma: no cover - direct parsing feedback
        return None, f"Unable to parse YAML: {exc}"
    if not isinstance(parsed, dict):
        return None, "Parsed YAML does not contain a top-level mapping."
    updated = deepcopy(baseline)
    for section in updated:
        section_data = parsed.get(section["name"], {})
        if not isinstance(section_data, dict):
            section_data = {}
        if not section_data:
            section_data = parsed
        for param in section.get("parameters", []):
            key = param["key"]
            if key not in section_data:
                continue
            raw_value = section_data[key]
            path = make_path(section["name"], key)
            value_type = param.get("type", "string")
            if value_type == "boolean":
                param["value"] = bool(yaml_numeric_to_ui_bool(path, raw_value))
            elif value_type in {"number", "integer"}:
                if raw_value in (None, ""):
                    param["value"] = None
                else:
                    try:
                        numeric = float(raw_value)
                        param["value"] = (
                            int(numeric) if value_type == "integer" else numeric
                        )
                    except (TypeError, ValueError):
                        param["value"] = None
            elif value_type == "source":
                param["value"] = cast_value("source", raw_value)
            elif value_type.startswith("list:"):
                param["value"] = _coerce_list_value(value_type, raw_value)
            elif value_type == "mapping":
                param["value"] = cast_value("mapping", raw_value)
            elif value_type == "array":
                if isinstance(raw_value, (list, dict)):
                    param["value"] = raw_value
                else:
                    param["value"] = str(raw_value)
            else:
                param["value"] = "" if raw_value is None else str(raw_value)
    return updated, None


def _extract_geojson_bounds(payload: Any) -> Optional[List[List[float]]]:
    coords: List[Tuple[float, float]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                visit(value)
        elif isinstance(node, (list, tuple)):
            if node and isinstance(node[0], (int, float)):
                if len(node) >= 2:
                    lon, lat = node[:2]
                    coords.append((float(lat), float(lon)))
            else:
                for child in node:
                    visit(child)

    visit(payload)
    if not coords:
        return None
    lats, lons = zip(*coords)
    south, north = min(lats), max(lats)
    west, east = min(lons), max(lons)
    return [[south, west], [north, east]]


def _percentile_stretch(
    arr: np.ndarray, pmin: float = 2, pmax: float = 98
) -> np.ndarray:
    """Scale array to 0..255 using per-band percentiles."""
    a = arr.astype("float32", copy=False)
    lo = float(np.nanpercentile(a, pmin))
    hi = float(np.nanpercentile(a, pmax))
    if hi <= lo:
        hi = lo + 1.0
    scaled = (a - lo) / (hi - lo)
    scaled = np.clip(scaled, 0.0, 1.0) * 255.0
    return scaled.astype("uint8")


def geotiff_to_png_with_bounds(
    tif_path: str, out_dir: str, max_size_px: int = 2048, png_quality: int = 90
) -> Tuple[str, List[List[float]]]:
    """
    Convert GeoTIFF to PNG for Leaflet ImageOverlay with better visual parity to QGIS:
      - applies palette if present
      - percentile stretch for 16-bit / float bands
      - NoData -> alpha
    Returns (png_path, [[south, west],[north, east]]) in EPSG:4326.
    """
    src_path = Path(tif_path)
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as src:
        bounds = src.bounds
        if src.crs and src.crs.to_string() != "EPSG:4326":
            west, south, east, north = transform_bounds(
                src.crs,
                "EPSG:4326",
                bounds.left,
                bounds.bottom,
                bounds.right,
                bounds.top,
            )
        else:
            west, south, east, north = (
                bounds.left,
                bounds.bottom,
                bounds.right,
                bounds.top,
            )

        nodata = src.nodata
        mask = src.dataset_mask().astype(bool)

        try:
            palette = src.colormap(1)
        except Exception:
            palette = None

        if src.count == 1 and palette:
            band = src.read(1, resampling=Resampling.nearest)
            lut = np.zeros((256, 4), dtype="uint8")
            for key, value in palette.items():
                lut[key, :] = value
            band_clip = np.clip(band, 0, 255).astype("uint8")
            rgba = lut[band_clip]
            if nodata is not None:
                rgba[..., 3] = np.where((band == nodata) | (~mask), 0, rgba[..., 3])
            else:
                rgba[..., 3] = np.where(~mask, 0, rgba[..., 3])
            img = Image.fromarray(rgba, mode="RGBA")
        else:
            if src.count >= 3:
                arr = src.read([1, 2, 3], resampling=Resampling.nearest)
                if str(arr.dtype) != "uint8":
                    arr = np.stack(
                        [_percentile_stretch(arr[i]) for i in range(3)], axis=0
                    )
                arr = np.transpose(arr, (1, 2, 0))
            else:
                band = src.read(1, resampling=Resampling.nearest)
                if str(band.dtype) != "uint8":
                    band = _percentile_stretch(band)
                arr = np.stack([band, band, band], axis=-1)

            if nodata is not None and src.count >= 1:
                raw1 = src.read(1, resampling=Resampling.nearest)
                alpha = np.where((raw1 == nodata) | (~mask), 0, 255).astype("uint8")
            else:
                alpha = np.where(mask, 255, 0).astype("uint8")

            rgba = np.dstack([arr, alpha])
            img = Image.fromarray(rgba, mode="RGBA")

        width, height = img.size
        scale = min(1.0, max_size_px / float(max(width, height)))
        if scale < 1.0:
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.BILINEAR)

        png_path = out_dir_path / (src_path.stem + ".png")
        img.save(png_path, optimize=True, quality=png_quality)

    return str(png_path), [[south, west], [north, east]]


def build_map_html(
    layers: List[Dict[str, Any]],
    out_html: str,
    legend_html: str = "",
    default_center: Tuple[float, float] = (55.6761, 12.5683),
    default_zoom: int = 7,
    raster_opacity: float = 0.7,
) -> Optional[List[List[float]]]:
    out_html_path = Path(out_html)
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    fmap = folium.Map(
        location=default_center, zoom_start=default_zoom, control_scale=True
    )

    def update_union(
        current: Optional[List[List[float]]], new_bounds: Optional[List[List[float]]]
    ) -> Optional[List[List[float]]]:
        if not new_bounds:
            return current
        if current is None:
            return [
                [new_bounds[0][0], new_bounds[0][1]],
                [new_bounds[1][0], new_bounds[1][1]],
            ]
        south = min(current[0][0], new_bounds[0][0])
        west = min(current[0][1], new_bounds[0][1])
        north = max(current[1][0], new_bounds[1][0])
        east = max(current[1][1], new_bounds[1][1])
        return [[south, west], [north, east]]

    sorted_layers = sorted(
        layers, key=lambda item: (item.get("order", 0), item.get("index", 0))
    )
    union_bounds: Optional[List[List[float]]] = None
    for layer in sorted_layers:
        display_name = layer.get("display_name") or layer.get("name") or "Layer"
        if layer["type"] == "raster":
            image_path = Path(layer["image_path"])
            if not image_path.exists():
                raise FileNotFoundError(f"Raster image missing: {image_path}")
            overlay = folium.raster_layers.ImageOverlay(
                name=display_name,
                image=str(image_path.resolve()),
                bounds=layer["bounds"],
                opacity=float(layer.get("opacity", raster_opacity)),
                interactive=True,
                zindex=int(layer.get("order", 0)),
            )
            overlay.add_to(fmap)
            union_bounds = update_union(union_bounds, layer["bounds"])
        elif layer["type"] == "geojson":
            geojson_data = layer["data"]
            opacity = float(layer.get("opacity", 1.0))
            style_dict = layer.get("style") or {
                "color": layer.get("color", "#3388ff"),
                "weight": 2,
                "opacity": opacity,
                "fillOpacity": max(0.0, min(1.0, opacity * 0.6)),
            }

            def style_function(_feature, style=style_dict) -> Dict[str, Any]:
                return style

            def highlight_function(_feature, style=style_dict) -> Dict[str, Any]:
                highlighted = dict(style)
                highlighted["weight"] = style.get("weight", 2) + 1
                highlighted["opacity"] = min(1.0, style.get("opacity", opacity) + 0.1)
                highlighted["fillOpacity"] = min(
                    1.0, style.get("fillOpacity", opacity * 0.6) + 0.1
                )
                return highlighted

            geojson_layer = folium.GeoJson(
                geojson_data,
                name=display_name,
                style_function=style_function,
                highlight_function=highlight_function,
            )
            geojson_layer.add_to(fmap)
            gj_bounds = layer.get("bounds") or _extract_geojson_bounds(geojson_data)
            union_bounds = update_union(union_bounds, gj_bounds)
        else:
            raise ValueError(f"Unsupported layer type: {layer['type']}")
    folium.LayerControl(collapsed=False).add_to(fmap)
    if union_bounds:
        fmap.fit_bounds(union_bounds)

    if legend_html:
        legend_content = legend_html
        if "<" not in legend_content:
            legend_content = "<br>".join(
                html.escape(part) for part in legend_content.splitlines()
            )
        template = Template(
            f"""
            {{% macro html() %}}
            <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999; background: rgba(255, 255, 255, 0.85); padding: 12px; border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.3); max-width: 240px; font-size: 13px; line-height: 1.4;">
                {legend_content}
            </div>
            {{% endmacro %}}
            """
        )
        macro = MacroElement()
        macro._template = template
        fmap.get_root().add_child(macro)

    fmap.save(str(out_html_path))
    return union_bounds


def _show_map_fallback(
    html_path: Path, parent: tk.Widget, reason: Optional[str] = None
) -> Dict[str, Any]:
    info = "Interactive map opened in your default browser."
    if reason:
        info = f"{info} ({reason})"
    label = ttk.Label(
        parent, text=info, foreground="#a66b00", wraplength=420, justify="left"
    )
    label.pack(fill="x", padx=10, pady=8)
    webbrowser.open_new_tab(html_path.resolve().as_uri())
    return {"embedded": False, "widget": label, "cleanup": lambda: None}


def show_map_in_tk(html_path: str, parent: tk.Widget) -> Dict[str, Any]:
    target = Path(html_path)
    try:
        from tkwebview2.tkwebview2 import WebView2  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        return _show_map_fallback(target, parent, f"tkwebview2 unavailable: {exc}")

    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)
    container.update_idletasks()
    width = max(container.winfo_width(), 400)
    height = max(container.winfo_height(), 300)
    try:
        widget = WebView2(container, width=width, height=height)
    except Exception as exc:
        container.destroy()
        return _show_map_fallback(
            target, parent, f"Unable to initialise WebView2: {exc}"
        )

    widget.pack(fill="both", expand=True)
    uri = target.resolve().as_uri()
    loaded = False
    for method_name in ("load_url", "navigate", "go"):
        method = getattr(widget, method_name, None)
        if callable(method):
            try:
                method(uri)
                loaded = True
                break
            except Exception:
                continue
    if not loaded:
        try:
            html_text = target.read_text(encoding="utf-8")
        except Exception as exc:
            widget.destroy()
            container.destroy()
            return _show_map_fallback(target, parent, f"Unable to display map: {exc}")
        html_loaded = False
        for method_name in (
            "load_html",
            "load_html_string",
            "set_html",
            "load_html_content",
        ):
            method = getattr(widget, method_name, None)
            if callable(method):
                try:
                    method(html_text)
                    html_loaded = True
                    break
                except Exception:
                    continue
        if not html_loaded:
            try:
                widget.html = html_text  # type: ignore[attr-defined]
                html_loaded = True
            except Exception:
                html_loaded = False
        if not html_loaded:
            widget.destroy()
            container.destroy()
            return _show_map_fallback(
                target, parent, "Unable to display map in embedded viewer."
            )

    def cleanup() -> None:
        try:
            widget.destroy()
        except Exception:
            pass
        if container.winfo_exists():
            try:
                container.destroy()
            except Exception:
                pass

    container.bind("<Destroy>", lambda _e: cleanup())
    return {
        "embedded": True,
        "widget": container,
        "cleanup": cleanup,
        "browser": widget,
    }


class ConfigurationTab(ttk.Frame):
    """Configuration management tab."""

    def __init__(self, master: tk.Widget, sections: List[Dict[str, Any]]):
        super().__init__(master)
        self.sections_baseline = deepcopy(sections)
        self.sections = deepcopy(sections)
        self.config_save_path: Optional[Path] = None
        self._config_source_text: Optional[str] = None
        self.snakefile_save_path: Optional[Path] = None
        self._snakefile_source_text = SNAKEFILE_TEMPLATE
        self.config_dirty = False
        self.snakefile_dirty = False
        self.raw_dirty = False
        self.advanced_save_path: Optional[Path] = None
        self._advanced_source_text: str = ""
        self.advanced_dirty = False
        self.enable_visual_editor = True
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.config_mode = tk.StringVar(value="visual")
        self.param_vars: Dict[Tuple[int, int], Any] = {}
        self.param_widgets: Dict[Tuple[int, int], tk.Widget] = {}
        self.mapping_registries: Dict[Tuple[int, int], Dict[str, tk.StringVar]] = {}
        self.settings_search_var = tk.StringVar()
        self.filtered_section_indices = list(range(len(self.sections)))
        self._handling_settings_search = False
        self._comment_help_cache: Dict[str, Dict[str, str]] = {}
        self.validation_issues: List[Dict[str, str]] = []
        self.validation_issue_items: Dict[str, Dict[str, str]] = {}
        self._suspend_dirty_tracking = False
        self._visual_histories: Dict[str, Dict[str, Any]] = {}
        self.document_tabs: Dict[str, tk.Widget] = {}
        self.document_tab_notebooks: Dict[str, ttk.Notebook] = {}
        self.document_tab_titles: Dict[str, str] = {}
        self.document_categories: Dict[str, str] = {}
        self.category_tabs: Dict[str, ttk.Frame] = {}
        self.document_save_buttons: Dict[str, ttk.Button] = {}
        self.extra_files = self._load_additional_files()
        self._build_ui()
        self._refresh_config_view()
        if self.sections:
            self.section_listbox.selection_set(0)
        self._load_existing_config()
        self._initialize_visual_histories()
        self._refresh_dirty_state_ui()
        self.after_idle(self.validate_all)

    def _build_ui(self) -> None:
        validation_frame = ttk.LabelFrame(
            self, text="Configuration validation", padding=(8, 5)
        )
        validation_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        validation_frame.columnconfigure(0, weight=1)
        self.validation_status = ttk.Label(
            validation_frame,
            text="Not validated — errors block saving/running; warnings are advisory",
        )
        self.validation_status.grid(row=0, column=0, sticky="w")
        self.save_all_button = ttk.Button(
            validation_frame,
            text="Save All",
            command=self._save_all,
        )
        self.save_all_button.grid(row=0, column=1, sticky="e", padx=(8, 6))
        ttk.Button(
            validation_frame,
            text="Validate all configurations",
            command=self._run_manual_validation,
        ).grid(row=0, column=2, sticky="e")
        ttk.Label(
            validation_frame,
            text=(
                "Checks YAML syntax, required settings, relationships between fields, selected "
                "technology files, and workflow-stage dependencies. It does not inspect downloaded "
                "datasets, credentials, external services, or scientific suitability."
            ),
            foreground="#555555",
            wraplength=980,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(3, 0))
        self.validation_tree = ttk.Treeview(
            validation_frame,
            columns=("severity", "file", "setting", "message"),
            show="headings",
            height=4,
        )
        for column, heading, width in (
            ("severity", "Level", 70),
            ("file", "File", 135),
            ("setting", "Setting", 180),
            ("message", "Issue", 620),
        ):
            self.validation_tree.heading(column, text=heading)
            self.validation_tree.column(column, width=width, anchor="w")
        self.validation_tree.grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(5, 0)
        )
        self.validation_tree.bind("<Double-1>", self._on_validation_issue_open)
        self.validation_tree.bind("<Return>", self._on_validation_issue_open)
        self.validation_tree.grid_remove()
        self.save_summary_status = ttk.Label(
            validation_frame, text="", foreground="#2E6B3A"
        )
        self.save_summary_status.grid(
            row=3, column=0, columnspan=3, sticky="e", pady=(3, 0)
        )

        search_frame = ttk.LabelFrame(
            self, text="Search across settings", padding=(8, 5)
        )
        search_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=(2, 4))
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="Key, label, or description:").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self.settings_search_entry = ttk.Entry(
            search_frame, textvariable=self.settings_search_var
        )
        self.settings_search_entry.grid(row=0, column=1, sticky="ew")
        self.settings_search_entry.bind(
            "<Escape>", lambda _event: self.settings_search_var.set("")
        )
        self.settings_search_clear_button = ttk.Button(
            search_frame,
            text="Clear",
            command=lambda: self.settings_search_var.set(""),
            state="disabled",
        )
        self.settings_search_clear_button.grid(row=0, column=2, padx=(6, 0))
        self.settings_search_status = ttk.Label(
            search_frame, text="", foreground="#555555"
        )
        self.settings_search_status.grid(row=0, column=3, sticky="e", padx=(10, 0))
        ttk.Button(
            search_frame,
            text="Help & glossary...",
            command=self._show_configuration_help,
        ).grid(row=0, column=4, sticky="e", padx=(10, 0))

        notebook = ttk.Notebook(self)
        notebook.grid(row=2, column=0, sticky="nsew")
        self.config_notebook = notebook
        for category in CONFIGURATION_CATEGORIES:
            category_frame = ttk.Frame(notebook)
            notebook.add(category_frame, text=category)
            self.category_tabs[category] = category_frame
        technology_category = self.category_tabs["Technology exclusions"]
        technology_category.columnconfigure(0, weight=1)
        technology_category.rowconfigure(0, weight=1)
        self.technology_notebook = ttk.Notebook(technology_category)
        self.technology_notebook.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        self.config_tab = self.category_tabs["General"]
        self.config_tab.columnconfigure(0, weight=1)
        self.config_tab.rowconfigure(1, weight=1)
        self.document_tabs["config.yaml"] = self.config_tab
        self.document_tab_notebooks["config.yaml"] = notebook
        self.document_tab_titles["config.yaml"] = "General"
        self.document_categories["config.yaml"] = "General"
        mode_frame = ttk.Frame(self.config_tab)
        mode_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ttk.Label(mode_frame, text="config.yaml", font=("Segoe UI", 10, "bold")).pack(
            side="left", padx=(0, 16)
        )
        ttk.Label(mode_frame, text="Edit Mode:").pack(side="left")
        self.visual_button = ttk.Radiobutton(
            mode_frame,
            text="Visual Editor",
            value="visual",
            variable=self.config_mode,
            command=self._on_mode_change,
        )
        self.visual_button.pack(side="left", padx=6)
        self.raw_button = ttk.Radiobutton(
            mode_frame,
            text="Raw YAML",
            value="raw",
            variable=self.config_mode,
            command=self._on_mode_change,
        )
        self.raw_button.pack(side="left")
        self.config_status = ttk.Label(mode_frame, text="")
        self.config_status.pack(side="right")
        self.visual_container = ttk.Frame(self.config_tab)
        self.visual_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.visual_container.columnconfigure(1, weight=1)
        self.visual_container.columnconfigure(0, minsize=260)  # widen left pane
        self.visual_container.rowconfigure(0, weight=1)
        self.section_list_var = tk.StringVar(
            value=[sec.get("displayName", sec["name"]) for sec in self.sections]
        )
        self.section_listbox = tk.Listbox(
            self.visual_container,
            listvariable=self.section_list_var,
            exportselection=False,
            height=20,
        )
        self.section_listbox.grid(row=0, column=0, sticky="nsew")
        self.section_listbox.bind("<<ListboxSelect>>", self._on_section_select)
        section_scroll = ttk.Scrollbar(
            self.visual_container, orient="vertical", command=self.section_listbox.yview
        )
        section_scroll.grid(row=0, column=0, sticky="nse")
        self.section_listbox.configure(yscrollcommand=section_scroll.set)
        self.param_canvas = tk.Canvas(self.visual_container, highlightthickness=0)
        self.param_canvas.grid(row=0, column=1, sticky="nsew")
        params_scroll = ttk.Scrollbar(
            self.visual_container, orient="vertical", command=self.param_canvas.yview
        )
        params_scroll.grid(row=0, column=2, sticky="ns")
        self.param_canvas.configure(yscrollcommand=params_scroll.set)
        self.param_inner = ttk.Frame(self.param_canvas)
        self.param_inner.bind(
            "<Configure>",
            lambda e: self.param_canvas.configure(
                scrollregion=self.param_canvas.bbox("all")
            ),
        )
        self.param_canvas.create_window((0, 0), window=self.param_inner, anchor="nw")
        self.settings_search_var.trace_add("write", self._on_settings_search_changed)
        self.raw_container = ttk.Frame(self.config_tab)
        self.raw_container.columnconfigure(0, weight=1)
        self.raw_container.rowconfigure(0, weight=1)
        self.config_text = tk.Text(
            self.raw_container,
            wrap="none",
            font=("Courier New", 10),
            undo=True,
            autoseparators=True,
            maxundo=-1,
        )
        self.config_text.grid(row=0, column=0, sticky="nsew")
        self._bind_text_change_tracking(
            self.config_text, lambda: self._mark_config_dirty(raw=True)
        )
        text_scroll_y = ttk.Scrollbar(
            self.raw_container, orient="vertical", command=self.config_text.yview
        )
        text_scroll_y.grid(row=0, column=1, sticky="ns")
        self.config_text.configure(yscrollcommand=text_scroll_y.set)
        text_scroll_x = ttk.Scrollbar(
            self.raw_container, orient="horizontal", command=self.config_text.xview
        )
        text_scroll_x.grid(row=1, column=0, sticky="ew")
        self.config_text.configure(xscrollcommand=text_scroll_x.set)
        self.config_highlighter = TextSyntaxHighlighter(self.config_text, "yaml")
        button_row = ttk.Frame(self.config_tab)
        button_row.grid(row=2, column=0, sticky="e", padx=10, pady=(5, 10))
        ttk.Button(button_row, text="Discard Changes", command=self._reset_config).pack(
            side="right", padx=6
        )
        self.config_save_button = ttk.Button(
            button_row, text="Save", command=self._save_config
        )
        self.config_save_button.pack(side="right")
        ttk.Button(
            button_row, text="Redo", command=lambda: self._redo_document("config.yaml")
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            button_row, text="Undo", command=lambda: self._undo_document("config.yaml")
        ).pack(side="left")
        self.document_save_buttons["config.yaml"] = self.config_save_button
        self.snakefile_tab = self.category_tabs["Snakefile"]
        self.snakefile_tab.columnconfigure(0, weight=1)
        self.snakefile_tab.rowconfigure(0, weight=1)
        self.document_tabs["Snakefile"] = self.snakefile_tab
        self.document_tab_notebooks["Snakefile"] = notebook
        self.document_tab_titles["Snakefile"] = "Snakefile"
        self.document_categories["Snakefile"] = "Snakefile"
        self.snakefile_text = tk.Text(
            self.snakefile_tab,
            wrap="none",
            font=("Courier New", 10),
            undo=True,
            autoseparators=True,
            maxundo=-1,
        )
        self.snakefile_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.snakefile_text.insert("1.0", SNAKEFILE_TEMPLATE)
        self.snakefile_text.edit_reset()
        self._bind_text_change_tracking(self.snakefile_text, self._mark_snakefile_dirty)
        snake_scroll_y = ttk.Scrollbar(
            self.snakefile_tab, orient="vertical", command=self.snakefile_text.yview
        )
        snake_scroll_y.grid(row=0, column=1, sticky="ns", pady=10)
        self.snakefile_text.configure(yscrollcommand=snake_scroll_y.set)
        snake_scroll_x = ttk.Scrollbar(
            self.snakefile_tab, orient="horizontal", command=self.snakefile_text.xview
        )
        snake_scroll_x.grid(row=1, column=0, sticky="ew", padx=10)
        self.snakefile_text.configure(xscrollcommand=snake_scroll_x.set)
        self.snakefile_highlighter = TextSyntaxHighlighter(
            self.snakefile_text, "python"
        )
        snake_buttons = ttk.Frame(self.snakefile_tab)
        snake_buttons.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        self.snakefile_status = ttk.Label(snake_buttons, text="")
        self.snakefile_status.pack(side="left", padx=(0, 10))
        ttk.Button(
            snake_buttons, text="Discard Changes", command=self._reset_snakefile
        ).pack(side="right", padx=6)
        self.snakefile_save_button = ttk.Button(
            snake_buttons, text="Save", command=self._save_snakefile
        )
        self.snakefile_save_button.pack(side="right")
        ttk.Button(
            snake_buttons, text="Redo", command=lambda: self._redo_document("Snakefile")
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            snake_buttons, text="Undo", command=lambda: self._undo_document("Snakefile")
        ).pack(side="left")
        self.document_save_buttons["Snakefile"] = self.snakefile_save_button
        if SNAKEMAKE_GLOBAL_PATH.exists():
            try:
                snake_content = SNAKEMAKE_GLOBAL_PATH.read_text(encoding="utf-8")
            except OSError:
                self.snakefile_status.configure(
                    text=f"Could not read {SNAKEMAKE_GLOBAL_PATH.name}"
                )
            else:
                self.snakefile_text.delete("1.0", "end")
                self.snakefile_text.insert("1.0", snake_content)
                self.snakefile_status.configure(
                    text=f"Loaded from {SNAKEMAKE_GLOBAL_PATH.name}"
                )
                self.snakefile_save_path = SNAKEMAKE_GLOBAL_PATH
                self._snakefile_source_text = snake_content
                self.snakefile_dirty = False
                self._refresh_snakefile_highlight()
                self.snakefile_text.edit_reset()
        self.advanced_tab = self.category_tabs["Advanced settings"]
        self.advanced_tab.columnconfigure(0, weight=1)
        self.advanced_tab.rowconfigure(0, weight=1)
        self.document_tabs["advanced_data_prep_settings.yaml"] = self.advanced_tab
        self.document_tab_notebooks["advanced_data_prep_settings.yaml"] = notebook
        self.document_tab_titles["advanced_data_prep_settings.yaml"] = (
            "Advanced settings"
        )
        self.document_categories["advanced_data_prep_settings.yaml"] = (
            "Advanced settings"
        )
        self.advanced_text = tk.Text(
            self.advanced_tab,
            wrap="none",
            font=("Courier New", 10),
            undo=True,
            autoseparators=True,
            maxundo=-1,
        )
        self.advanced_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self._bind_text_change_tracking(self.advanced_text, self._mark_advanced_dirty)
        advanced_scroll_y = ttk.Scrollbar(
            self.advanced_tab, orient="vertical", command=self.advanced_text.yview
        )
        advanced_scroll_y.grid(row=0, column=1, sticky="ns", pady=10)
        self.advanced_text.configure(yscrollcommand=advanced_scroll_y.set)
        advanced_scroll_x = ttk.Scrollbar(
            self.advanced_tab, orient="horizontal", command=self.advanced_text.xview
        )
        advanced_scroll_x.grid(row=1, column=0, sticky="ew", padx=10)
        self.advanced_text.configure(xscrollcommand=advanced_scroll_x.set)
        self.advanced_highlighter = TextSyntaxHighlighter(self.advanced_text, "yaml")
        advanced_buttons = ttk.Frame(self.advanced_tab)
        advanced_buttons.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        self.advanced_status = ttk.Label(advanced_buttons, text="")
        self.advanced_status.pack(side="left", padx=(0, 10))
        ttk.Button(
            advanced_buttons,
            text="Discard Changes",
            command=self._reset_advanced_settings,
        ).pack(side="right", padx=6)
        self.advanced_save_button = ttk.Button(
            advanced_buttons, text="Save", command=self._save_advanced_settings
        )
        self.advanced_save_button.pack(side="right")
        ttk.Button(
            advanced_buttons,
            text="Redo",
            command=lambda: self._redo_document("advanced_data_prep_settings.yaml"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            advanced_buttons,
            text="Undo",
            command=lambda: self._undo_document("advanced_data_prep_settings.yaml"),
        ).pack(side="left")
        self.document_save_buttons["advanced_data_prep_settings.yaml"] = (
            self.advanced_save_button
        )
        self._load_advanced_settings()
        for label, info in self.extra_files.items():
            category = DOCUMENT_CATEGORIES.get(label, "Technology exclusions")
            if category == "Technology exclusions":
                owner_notebook = self.technology_notebook
                file_frame = ttk.Frame(owner_notebook)
                owner_notebook.add(file_frame, text=label)
                tab_title = label
            else:
                owner_notebook = notebook
                file_frame = self.category_tabs[category]
                tab_title = category
            file_frame.columnconfigure(0, weight=1)
            file_frame.rowconfigure(0, weight=1)
            info["tab_frame"] = file_frame
            self.document_tabs[label] = file_frame
            self.document_tab_notebooks[label] = owner_notebook
            self.document_tab_titles[label] = tab_title
            self.document_categories[label] = category
            if info.get("sections"):
                self._build_structured_extra_editor(label, info, file_frame)
            else:
                self._build_raw_extra_editor(label, info, file_frame)
        for info in self.extra_files.values():
            info.setdefault("dirty", False)

    def _bind_text_change_tracking(
        self, widget: tk.Text, callback: Callable[[], None]
    ) -> None:
        widget.bind("<KeyRelease>", lambda _event: callback())
        for sequence in ("<<Paste>>", "<<Cut>>", "<<Undo>>", "<<Redo>>"):
            widget.bind(
                sequence,
                lambda _event, action=callback: self.after_idle(action),
                add="+",
            )

    @staticmethod
    def _short_help_text(description: str, limit: int = 115) -> str:
        text = " ".join(description.split())
        if len(text) <= limit:
            return text
        first_sentence = re.match(r"^(.+?[.!?])(?:\s|$)", text)
        if first_sentence and len(first_sentence.group(1)) <= limit:
            return first_sentence.group(1)
        shortened = text[: limit - 3].rsplit(" ", 1)[0]
        return f"{shortened}..."

    @staticmethod
    def _attach_tooltip(widget: tk.Widget, description: str) -> None:
        text = description.strip()
        if not text:
            return
        tooltip = Tooltip(widget, text)
        setattr(widget, "_lava_tooltip", tooltip)

    def _yaml_comment_hints(self, label: str) -> Dict[str, str]:
        cached = self._comment_help_cache.get(label)
        if cached is not None:
            return cached
        if label == "config.yaml":
            source_path = self.config_save_path or (CONFIGS_DIR / "config.yaml")
            try:
                source_text = source_path.read_text(encoding="utf-8")
            except OSError:
                source_text = self._config_source_text or ""
        else:
            info = self.extra_files.get(label, {})
            source_text = str(info.get("baseline", ""))
        hints = extract_yaml_comment_hints(source_text)
        self._comment_help_cache[label] = hints
        return hints

    def _comment_hint_for(self, label: str, key: str) -> str:
        return self._yaml_comment_hints(label).get(key, "")

    def _open_help_target(self, target: str) -> None:
        if target.startswith(("https://", "http://")):
            webbrowser.open_new_tab(target)
            return
        path = PARENT_DIR / target
        if not path.exists():
            messagebox.showerror(
                "Documentation", f"Documentation file not found:\n{path}", parent=self
            )
            return
        webbrowser.open_new_tab(path.resolve().as_uri())

    def _show_configuration_help(self) -> None:
        existing = getattr(self, "_configuration_help_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return
        dialog = tk.Toplevel(self)
        self._configuration_help_dialog = dialog
        dialog.title("Configuration help and glossary")
        dialog.geometry("760x560")
        dialog.minsize(640, 480)
        dialog.transient(self.winfo_toplevel())
        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="Configuration help", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            body,
            text=(
                "Short explanations appear beside controls. Hover over shortened text or a setting name "
                "for the full description. Valid-value examples are copied verbatim from YAML comments only."
            ),
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        glossary = ttk.LabelFrame(body, text="Glossary", padding=10)
        glossary.grid(row=2, column=0, sticky="ew")
        glossary.columnconfigure(1, weight=1)
        glossary_entries = (
            (
                "GADM",
                "Administrative boundary data used to select a named study region and administrative level.",
                "Source: config.yaml comments",
            ),
            (
                "CRS",
                "Coordinate Reference System used to interpret and project spatial coordinates.",
                "Source: docs/full_workflow.rst",
            ),
            (
                "Resource grade",
                "A wind or solar resource group used when deriving suitability and energy-profile inputs.",
                "Source: docs/full_workflow.rst",
            ),
            (
                "Bias correction",
                "Adjustment of ERA5 wind and solar data using Global Wind Atlas and Global Solar Atlas data.",
                "Source: config.yaml comments",
            ),
        )
        for row, (term, definition, source) in enumerate(glossary_entries):
            ttk.Label(
                glossary, text=term, font=("Segoe UI", 10, "bold"), width=18
            ).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=3)
            text_frame = ttk.Frame(glossary)
            text_frame.grid(row=row, column=1, sticky="ew", pady=3)
            ttk.Label(text_frame, text=definition, wraplength=520, justify="left").pack(
                anchor="w"
            )
            ttk.Label(text_frame, text=source, foreground="#666666").pack(anchor="w")

        docs = ttk.LabelFrame(body, text="Documentation", padding=10)
        docs.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        for title, target in (
            ("Documentation home", "https://lava-tool.readthedocs.io/en/latest/"),
            ("Workflow guide", "docs/full_workflow.rst"),
            ("Data sources", "docs/data_sources.rst"),
            ("GADM maps", "https://gadm.org/maps.html"),
        ):
            ttk.Button(
                docs,
                text=title,
                command=lambda destination=target: self._open_help_target(destination),
            ).pack(side="left", padx=(0, 8))

        ttk.Button(body, text="Close", command=dialog.destroy).grid(
            row=4, column=0, sticky="e", pady=(14, 0)
        )
        dialog.bind(
            "<Destroy>",
            lambda _event: setattr(self, "_configuration_help_dialog", None),
            add="+",
        )

    def _load_existing_config(self) -> None:
        config_path = CONFIGS_DIR / "config.yaml"
        if not config_path.exists():
            return
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Load failed", f"Could not read config.yaml:\n{exc}")
            return
        self.config_save_path = config_path
        self._config_source_text = text
        self.config_dirty = False
        self.raw_dirty = False
        self.config_status.configure(text=f"Loaded from {config_path.name}")
        if self.config_mode.get() == "raw":
            self.config_text.delete("1.0", "end")
            self.config_text.insert("1.0", text)
            self.config_text.edit_reset()
            self._refresh_config_highlight()
        else:
            self._populate_raw_editor()
        self._update_config_status()

    def _parse_validation_document(
        self, file_name: str, yaml_text: str
    ) -> Tuple[Optional[Mapping[str, Any]], Optional[Dict[str, str]]]:
        if yaml is None:
            return None, {
                "severity": "error",
                "file": file_name,
                "key": "<yaml>",
                "message": "PyYAML is required to validate this configuration.",
            }
        try:
            parsed = yaml.safe_load(yaml_text) or {}
        except Exception as exc:
            return None, {
                "severity": "error",
                "file": file_name,
                "key": "<yaml>",
                "message": f"Invalid YAML: {exc}",
            }
        if not isinstance(parsed, MappingABC):
            return None, {
                "severity": "error",
                "file": file_name,
                "key": "<yaml>",
                "message": "The YAML document must contain a mapping at its root.",
            }
        return parsed, None

    def _collect_validation_documents(
        self,
    ) -> Tuple[Dict[str, Mapping[str, Any]], List[Dict[str, str]]]:
        documents: Dict[str, Mapping[str, Any]] = {}
        parse_issues: List[Dict[str, str]] = []

        if self.config_mode.get() == "raw":
            config_text = self.config_text.get("1.0", "end-1c")
        else:
            config_text = sections_to_yaml(self.sections)
        document, issue = self._parse_validation_document("config.yaml", config_text)
        if document is not None:
            documents["config.yaml"] = document
        if issue:
            parse_issues.append(issue)

        for label, info in self.extra_files.items():
            mode_var = info.get("mode_var")
            text_widget = info.get("text_widget")
            if text_widget is not None and (
                mode_var is None or mode_var.get() == "raw"
            ):
                content = text_widget.get("1.0", "end-1c")
            else:
                self._update_extra_sections_from_controls(label)
                content = self._serialize_sections_for_kind(
                    info.get("kind"), info.get("sections")
                )
            document, issue = self._parse_validation_document(label, content)
            if document is not None:
                documents[label] = document
            if issue:
                parse_issues.append(issue)
        return documents, parse_issues

    def _issues_for(self, file_name: str, key: str) -> List[Dict[str, str]]:
        return [
            issue
            for issue in self.validation_issues
            if issue.get("file") == file_name and issue.get("key") == key
        ]

    @staticmethod
    def _issue_colour(severity: str) -> str:
        return "#B42318" if severity == "error" else "#8A5A00"

    def _refresh_validation_display(self) -> None:
        for item in self.validation_tree.get_children():
            self.validation_tree.delete(item)
        self.validation_issue_items.clear()
        errors = sum(
            issue.get("severity") == "error" for issue in self.validation_issues
        )
        warnings = sum(
            issue.get("severity") == "warning" for issue in self.validation_issues
        )
        validated_at = datetime.now().strftime("%H:%M:%S")
        if not self.validation_issues:
            self.validation_status.configure(
                text=f"Validated at {validated_at} — no errors or warnings",
                foreground="#1A7F37",
            )
            self.validation_tree.grid_remove()
            return
        self.validation_status.configure(
            text=(
                f"Validated at {validated_at} — {errors} error(s), {warnings} warning(s); "
                "double-click an issue to open it"
            ),
            foreground="#B42318" if errors else "#8A5A00",
        )
        self.validation_tree.tag_configure("error", foreground="#B42318")
        self.validation_tree.tag_configure("warning", foreground="#8A5A00")
        for issue in self.validation_issues:
            item = self.validation_tree.insert(
                "",
                "end",
                values=(
                    issue["severity"].title(),
                    issue["file"],
                    issue["key"],
                    issue["message"],
                ),
                tags=(issue["severity"],),
            )
            self.validation_issue_items[item] = issue
        self.validation_tree.grid()

    def _run_manual_validation(self) -> None:
        """Run validation from the button and always provide explicit feedback."""
        self.validation_status.configure(
            text="Validating all configurations...", foreground="#555555"
        )
        self.update_idletasks()
        try:
            issues = self.validate_all()
        except Exception as exc:
            self.validation_status.configure(
                text="Validation failed", foreground="#B42318"
            )
            messagebox.showerror(
                "Validation Failed",
                f"The validation check could not be completed:\n\n{exc}",
                parent=self,
            )
            return
        errors = sum(issue.get("severity") == "error" for issue in issues)
        warnings = sum(issue.get("severity") == "warning" for issue in issues)
        if not issues:
            messagebox.showinfo(
                "Validation Complete",
                "All active configuration files passed the available checks.\n\n"
                "This confirms YAML syntax, required settings, field relationships, technology "
                "configuration references, and workflow-stage dependencies.\n\n"
                "It does not verify downloaded datasets, credentials, external services, or the "
                "scientific suitability of the selected values.",
                parent=self,
            )
            return
        messagebox.showwarning(
            "Validation Complete",
            f"Validation found {errors} error(s) and {warnings} warning(s).\n\n"
            "Errors must be fixed before the affected file can be saved or a run can start. "
            "Warnings are advisory and do not block those actions.\n\n"
            "Double-click an issue in the validation table to open the affected setting.",
            parent=self,
        )

    def validate_all(self, refresh_visual: bool = True) -> List[Dict[str, str]]:
        documents, parse_issues = self._collect_validation_documents()
        self.validation_issues = parse_issues + validate_configuration_documents(
            documents, CONFIGS_DIR
        )
        self._refresh_validation_display()
        if refresh_visual:
            if self.config_mode.get() == "visual":
                selected_section = self._selected_actual_section_index()
                if selected_section is not None:
                    self._render_parameters(selected_section)
            for label, info in self.extra_files.items():
                mode_var = info.get("mode_var")
                if mode_var is not None and mode_var.get() == "visual":
                    self._render_extra_visual_sections(label, info)
        return self.validation_issues

    def validate_before_action(self, file_name: Optional[str], action: str) -> bool:
        issues = list(self.validate_all())
        if action == "run":
            unsaved_files: List[str] = []
            if self.config_dirty:
                unsaved_files.append("config.yaml")
            if self.snakefile_dirty:
                unsaved_files.append("Snakefile")
            if self.advanced_dirty:
                unsaved_files.append(CONFIG_ADVANCED_SETTINGS_PATH.name)
            unsaved_files.extend(
                label for label, info in self.extra_files.items() if info.get("dirty")
            )
            if unsaved_files:
                messagebox.showerror(
                    "Unsaved Configuration Changes",
                    "Save these files before running:\n" + "\n".join(unsaved_files),
                )
                return False
        blocking = [
            issue
            for issue in issues
            if issue.get("severity") == "error"
            and (file_name is None or issue.get("file") == file_name)
        ]
        if not blocking:
            return True
        first = blocking[0]
        self._open_validation_issue(first)
        if action == "run":
            verb = "run"
        elif file_name is None:
            verb = "save all files"
        else:
            verb = f"save {file_name}"
        messagebox.showerror(
            "Configuration Validation",
            f"Cannot {verb} until {len(blocking)} validation error(s) are fixed.\n\n"
            f"{first['file']} — {first['key']}: {first['message']}",
        )
        return False

    def _on_validation_issue_open(self, _event: Optional[tk.Event] = None) -> None:
        selected = self.validation_tree.selection()
        if selected:
            issue = self.validation_issue_items.get(selected[0])
            if issue:
                self._open_validation_issue(issue)

    def _open_validation_issue(self, issue: Mapping[str, str]) -> None:
        file_name = issue.get("file", "")
        key = issue.get("key", "")
        if key != "<yaml>" and self.settings_search_var.get():
            self.settings_search_var.set("")
        if file_name == "config.yaml":
            self._select_document_tab("config.yaml")
            if key == "<yaml>":
                self.config_mode.set("raw")
                self._refresh_config_view()
                self.config_text.focus_set()
                return
            self.config_mode.set("visual")
            self._refresh_config_view()
            for section_index, section in enumerate(self.sections):
                for param_index, param in enumerate(section.get("parameters", [])):
                    if param.get("key") != key:
                        continue
                    self._select_actual_section(section_index)
                    widget = self.param_widgets.get((section_index, param_index))
                    if widget is not None:
                        widget.focus_set()
                        self.param_canvas.update_idletasks()
                        bounds = self.param_canvas.bbox("all")
                        if bounds and bounds[3] > 0:
                            self.param_canvas.yview_moveto(
                                max(0.0, widget.winfo_y() / bounds[3])
                            )
                    return
            return

        info = self.extra_files.get(file_name)
        if not info:
            return
        self._select_document_tab(file_name)
        mode_var = info.get("mode_var")
        if key == "<yaml>" or not mode_var:
            if mode_var is not None and mode_var.get() != "raw":
                mode_var.set("raw")
                self._handle_extra_mode_change(file_name)
            text_widget = info.get("text_widget")
            if text_widget is not None:
                text_widget.focus_set()
            return
        if mode_var.get() != "visual":
            mode_var.set("visual")
            self._handle_extra_mode_change(file_name)
        for control in info.get("param_controls", []):
            if control.get("param", {}).get("key") != key:
                continue
            widget = control.get("widget")
            if widget is not None:
                widget.focus_set()
                canvas = info.get("visual_canvas")
                if canvas is not None:
                    canvas.update_idletasks()
                    bounds = canvas.bbox("all")
                    if bounds and bounds[3] > 0:
                        canvas.yview_moveto(max(0.0, widget.winfo_y() / bounds[3]))
            return

    def _refresh_config_highlight(self) -> None:
        highlighter = getattr(self, "config_highlighter", None)
        if highlighter:
            highlighter.refresh()

    def _refresh_snakefile_highlight(self) -> None:
        highlighter = getattr(self, "snakefile_highlighter", None)
        if highlighter:
            highlighter.refresh()

    def _refresh_advanced_highlight(self) -> None:
        highlighter = getattr(self, "advanced_highlighter", None)
        if highlighter:
            highlighter.refresh()

    @staticmethod
    def _coerce_sequence_value(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, CommentedSeq):
            return list(value)
        if isinstance(value, (list, tuple)):
            return list(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return list(parsed)
            try:
                literal = ast.literal_eval(text)
            except Exception:
                literal = None
            if isinstance(literal, list):
                return list(literal)
            if "," in text:
                return [item.strip() for item in text.split(",") if item.strip()]
            return [text]
        return [value]

    @staticmethod
    def _coerce_boolean_value(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if not text:
            return default
        return text in {"1", "true", "yes", "on", "y"}

    @staticmethod
    def _coerce_integer_value(value: Any, default: int = 0) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if value in (None, ""):
            return default
        try:
            text = str(value).strip()
            if not text:
                return default
            return int(float(text))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _stringify_weather_years_field(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        sequence = ConfigurationTab._coerce_sequence_value(value)
        return ", ".join(str(item) for item in sequence) if sequence else ""

    def _choices_for_parameter(self, key: str, current_value: Any = None) -> List[str]:
        if key in {"panel", "turbine"}:
            choices = sorted(
                path.name for path in (CONFIGS_DIR / "technologies").glob("*.yaml")
            )
        elif key == "technologies":
            excluded = {"config", "snakemake", "suitability"}
            choices = sorted(
                path.stem
                for path in CONFIGS_DIR.glob("*.yaml")
                if "_template" not in path.stem and path.stem not in excluded
            )
        else:
            choices = list(PARAMETER_CHOICES.get(key, []))
        current_items = self._coerce_sequence_value(current_value)
        for item in current_items:
            text = str(item).strip()
            if text and text not in choices:
                choices.append(text)
        return choices

    @staticmethod
    def _numeric_limits(key: str, param_type: str) -> Tuple[float, float, float]:
        if key == "GADM_level":
            return 0, 5, 1
        if key in {"population_year", "weather_year"}:
            return 1900, 2100, 1
        if key == "cores":
            return 1, 512, 1
        if key == "max_slope":
            return 0, 90, 1
        if key == "tech_derate":
            return 0, 1, 0.01
        if key.endswith("_buffer") or key in {
            "deployment_density",
            "resolution_manual",
            "min_pixels_connected",
            "max_population",
            "max_forest_density",
        }:
            return 0, 1_000_000_000, 1
        return (-1_000_000_000, 1_000_000_000, 1 if param_type == "integer" else 0.1)

    def _browse_for_parameter(self, key: str, variable: tk.StringVar) -> None:
        picker = PARAMETER_PICKERS.get(key)
        if not picker:
            return
        current = variable.get().strip()
        initial_dir = PARENT_DIR
        if current:
            candidate = Path(current)
            if not candidate.is_absolute():
                candidate = PARENT_DIR / candidate
            if candidate.exists():
                initial_dir = candidate if candidate.is_dir() else candidate.parent
        if picker in {"directory", "folder_name"}:
            selected = filedialog.askdirectory(initialdir=str(initial_dir), parent=self)
        else:
            selected = filedialog.askopenfilename(
                initialdir=str(initial_dir),
                filetypes=[("All files", "*.*")],
                parent=self,
            )
        if not selected:
            return
        selected_path = Path(selected)
        if picker in {"filename", "folder_name"}:
            rendered = selected_path.name
        elif picker == "project_file":
            try:
                rendered = (
                    selected_path.resolve().relative_to(PARENT_DIR.resolve()).as_posix()
                )
            except ValueError:
                rendered = str(selected_path)
        else:
            rendered = str(selected_path)
        variable.set(rendered)

    @staticmethod
    def _is_simple_sequence(value: Any) -> bool:
        if value in (None, "") or isinstance(value, str):
            return True
        return isinstance(value, (list, tuple, CommentedSeq)) and all(
            not isinstance(item, (MappingABC, list, tuple, CommentedSeq))
            for item in value
        )

    def _create_list_editor(
        self,
        parent: tk.Widget,
        value: Any,
        on_change: Callable[[List[Any]], None],
        choices: Optional[List[str]] = None,
    ) -> Tuple[ttk.Frame, tk.Listbox]:
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        current = self._coerce_sequence_value(value)
        available = list(choices or [])
        for item in current:
            text = str(item)
            if text not in available:
                available.append(text)
        choice_mode = bool(choices)
        listbox = tk.Listbox(
            frame,
            height=min(6, max(3, len(available) or len(current) or 3)),
            selectmode=tk.MULTIPLE if choice_mode else tk.EXTENDED,
            exportselection=False,
        )
        for item in available if choice_mode else current:
            listbox.insert("end", str(item))
        if choice_mode:
            selected_text = {str(item) for item in current}
            for index in range(listbox.size()):
                if str(listbox.get(index)) in selected_text:
                    listbox.selection_set(index)
        listbox.grid(row=0, column=0, columnspan=3, sticky="ew")

        def parse_scalar(text: str) -> Any:
            if yaml is not None:
                try:
                    parsed = yaml.safe_load(text)
                    if not isinstance(parsed, (MappingABC, list)):
                        return parsed
                except Exception:
                    pass
            return text

        def emit_selection(_event: Optional[tk.Event] = None) -> None:
            if choice_mode:
                values = [
                    parse_scalar(str(listbox.get(index)))
                    for index in listbox.curselection()
                ]
            else:
                values = [
                    parse_scalar(str(listbox.get(index)))
                    for index in range(listbox.size())
                ]
            on_change(values)

        if choice_mode:
            listbox.bind("<<ListboxSelect>>", emit_selection)
        else:
            add_var = tk.StringVar()
            add_entry = ttk.Entry(frame, textvariable=add_var)
            add_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))

            def add_item() -> None:
                text = add_var.get().strip()
                if text:
                    listbox.insert("end", text)
                    add_var.set("")
                    emit_selection()

            def remove_selected() -> None:
                for index in reversed(listbox.curselection()):
                    listbox.delete(index)
                emit_selection()

            ttk.Button(frame, text="Add", command=add_item).grid(
                row=1, column=1, padx=(4, 0), pady=(4, 0)
            )
            ttk.Button(frame, text="Remove", command=remove_selected).grid(
                row=1, column=2, padx=(4, 0), pady=(4, 0)
            )
            add_entry.bind("<Return>", lambda _event: add_item())
        return frame, listbox

    def _load_advanced_settings(self) -> None:
        candidates = [CONFIG_ADVANCED_SETTINGS_PATH]
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                self.advanced_status.configure(text=f"Could not read {candidate.name}")
                continue
            self.advanced_text.delete("1.0", "end")
            self.advanced_text.insert("1.0", text)
            self.advanced_text.edit_reset()
            self.advanced_save_path = candidate
            self._advanced_source_text = text
            self.advanced_dirty = False
            self.advanced_status.configure(text=f"Loaded from {candidate.name}")
            self._refresh_advanced_highlight()
            return
        self.advanced_save_path = CONFIG_ADVANCED_SETTINGS_PATH
        self._advanced_source_text = ""
        self.advanced_text.delete("1.0", "end")
        self.advanced_text.edit_reset()
        self.advanced_status.configure(
            text=f"{CONFIG_ADVANCED_SETTINGS_PATH.name} not found"
        )
        self._refresh_advanced_highlight()

    def _load_additional_files(self) -> Dict[str, Dict[str, Any]]:
        entries: Dict[str, Dict[str, Any]] = {}
        specs = [
            (
                "onshorewind.yaml",
                CONFIGS_DIR / "onshorewind.yaml",
                load_onshore_sections,
                "generic",
            ),
            ("solar.yaml", CONFIGS_DIR / "solar.yaml", load_solar_sections, "generic"),
            (
                "offshorewind.yaml",
                CONFIGS_DIR / "offshorewind.yaml",
                load_offshore_sections,
                "generic",
            ),
            # Suitability contains deeply nested, technology-specific structures.
            # Keep it as raw YAML so the UI preserves that structure and its comments.
            ("suitability.yaml", CONFIGS_DIR / "suitability.yaml", None, "generic"),
            (
                "config_snakemake.yaml",
                CONFIGS_DIR / "config_snakemake.yaml",
                load_snakemake_sections,
                "config_snakemake",
            ),
        ]
        for label, expected_path, section_loader, kind in specs:
            if not expected_path.exists():
                continue
            existing_path: Optional[Path] = expected_path
            try:
                content = expected_path.read_text(encoding="utf-8")
            except OSError:
                content = ""
            sections = section_loader() if section_loader else None
            if sections and not content:
                content = self._serialize_sections_for_kind(kind, sections)
            entries[label] = {
                "path": existing_path,
                "baseline": content,
                "text_widget": None,
                "status_label": None,
                "dirty": False,
                "save_path": existing_path or expected_path,
                "expected_path": expected_path,
                "sections": sections,
                "sections_baseline": deepcopy(sections),
                "mode_var": None,
                "visual_frame": None,
                "raw_frame": None,
                "param_controls": [],
                "kind": kind,
            }
        return entries

    def _detect_language_for_label(self, label: str) -> str:
        """Return a best-guess language identifier for syntax highlighting."""
        name = (label or "").lower()
        if name in {"snakefile", "snakefile.py"} or name.endswith((".py", ".smk")):
            return "python"
        if name.endswith((".yaml", ".yml")) or "config" in name:
            return "yaml"
        return "plain"

    def _build_raw_extra_editor(
        self, label: str, info: Dict[str, Any], parent: tk.Widget
    ) -> None:
        text_widget = tk.Text(
            parent,
            wrap="none",
            font=("Courier New", 10),
            undo=True,
            autoseparators=True,
            maxundo=-1,
        )
        if label == "suitability.yaml":
            text_widget.configure(
                background="#FFFFFF",
                foreground="#202020",
                insertbackground="#202020",
                selectbackground="#B9D7F5",
                selectforeground="#101010",
            )
        text_widget.grid(row=0, column=0, sticky="nsew", padx=8, pady=(4, 6))
        text_widget.insert("1.0", info.get("baseline", ""))
        text_widget.edit_reset()
        self._bind_text_change_tracking(
            text_widget, lambda name=label: self._mark_extra_dirty(name, raw=True)
        )
        highlighter = TextSyntaxHighlighter(
            text_widget, self._detect_language_for_label(label)
        )
        if label == "suitability.yaml":
            dark_yaml_colours = {
                "comment": "#356B3B",
                "key": "#005A8D",
                "string": "#8A351B",
                "boolean": "#62358A",
                "number": "#6E4C00",
            }
            for tag_name, colour in dark_yaml_colours.items():
                text_widget.tag_configure(tag_name, foreground=colour)
            highlighter.refresh()
        info["highlighter"] = highlighter
        scroll_y = ttk.Scrollbar(parent, orient="vertical", command=text_widget.yview)
        scroll_y.grid(row=0, column=1, sticky="ns", pady=(4, 6))
        text_widget.configure(yscrollcommand=scroll_y.set)
        scroll_x = ttk.Scrollbar(parent, orient="horizontal", command=text_widget.xview)
        scroll_x.grid(row=1, column=0, sticky="ew", padx=8)
        text_widget.configure(xscrollcommand=scroll_x.set)
        buttons = ttk.Frame(parent)
        buttons.grid(row=2, column=0, sticky="e", padx=8, pady=(2, 8))
        if info["path"]:
            status_text = f"Loaded from {info['path'].name}"
        else:
            status_text = f"Saving to {info['expected_path'].name}"
        status_label = ttk.Label(buttons, text=status_text)
        status_label.pack(side="left", padx=(0, 10))
        ttk.Button(
            buttons,
            text="Discard Changes",
            command=lambda name=label: self._reset_extra_file(name),
        ).pack(side="right", padx=6)
        save_button = ttk.Button(
            buttons, text="Save", command=lambda name=label: self._save_extra_file(name)
        )
        save_button.pack(side="right")
        ttk.Button(
            buttons, text="Redo", command=lambda name=label: self._redo_document(name)
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            buttons, text="Undo", command=lambda name=label: self._undo_document(name)
        ).pack(side="left")
        info["text_widget"] = text_widget
        info["status_label"] = status_label
        info["save_button"] = save_button
        self.document_save_buttons[label] = save_button

    def _build_structured_extra_editor(
        self, label: str, info: Dict[str, Any], parent: tk.Widget
    ) -> None:
        # Keep the toggle row compact while letting the editor stack take the excess space.
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=0)

        # --- Mode toggle row (unchanged) ---
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(0, 2))
        mode_var = tk.StringVar(value="visual")
        info["mode_var"] = mode_var
        ttk.Label(mode_frame, text="Edit Mode:").pack(side="left")
        ttk.Radiobutton(
            mode_frame,
            text="Visual Editor",
            value="visual",
            variable=mode_var,
            command=lambda name=label: self._handle_extra_mode_change(name),
        ).pack(side="left", padx=6)
        ttk.Radiobutton(
            mode_frame,
            text="Raw YAML",
            value="raw",
            variable=mode_var,
            command=lambda name=label: self._handle_extra_mode_change(name),
        ).pack(side="left")

        # --- STACK that owns the space for both editors (prevents layout jump) ---
        editor_stack = ttk.Frame(parent)
        editor_stack.grid(row=1, column=0, sticky="nsew", padx=8, pady=0)
        editor_stack.columnconfigure(0, weight=1)
        editor_stack.rowconfigure(0, weight=1)
        info["editor_stack"] = editor_stack

        # --- Visual editor (scrollable) INSIDE the stack ---
        visual_container = ttk.Frame(editor_stack)
        visual_container.grid(row=0, column=0, sticky="nsew")
        visual_container.columnconfigure(0, weight=1)
        visual_container.rowconfigure(0, weight=1)

        visual_canvas = tk.Canvas(visual_container, highlightthickness=0, borderwidth=0)
        visual_canvas.grid(row=0, column=0, sticky="nsew", pady=0)

        vsb = ttk.Scrollbar(
            visual_container, orient="vertical", command=visual_canvas.yview
        )
        vsb.grid(row=0, column=1, sticky="ns")
        visual_canvas.configure(yscrollcommand=vsb.set)

        visual_frame = ttk.Frame(visual_canvas)
        inner_id = visual_canvas.create_window((0, 0), window=visual_frame, anchor="nw")

        # Scroll region follows content
        def _on_inner_config(_event):
            visual_canvas.configure(scrollregion=visual_canvas.bbox("all"))

        visual_frame.bind("<Configure>", _on_inner_config)

        # Inner frame width tracks canvas width
        def _on_canvas_config(event):
            visual_canvas.itemconfigure(inner_id, width=event.width)

        visual_canvas.bind("<Configure>", _on_canvas_config)

        info["visual_container"] = visual_container
        info["visual_canvas"] = visual_canvas
        info["visual_frame"] = visual_frame

        # Optional: mousewheel
        if hasattr(self, "_enable_mousewheel"):
            self._enable_mousewheel(visual_canvas)

        # --- Raw editor INSIDE the stack (same grid cell) ---
        raw_frame = ttk.Frame(editor_stack)
        raw_frame.grid(row=0, column=0, sticky="nsew")
        info["raw_frame"] = raw_frame

        text_widget = tk.Text(
            raw_frame,
            wrap="none",
            font=("Courier New", 10),
            undo=True,
            autoseparators=True,
            maxundo=-1,
        )
        text_widget.grid(row=0, column=0, sticky="nsew")
        raw_frame.rowconfigure(0, weight=1)
        raw_frame.columnconfigure(0, weight=1)

        baseline = info.get("baseline") or self._serialize_sections_for_kind(
            info.get("kind"), info.get("sections")
        )
        text_widget.insert("1.0", baseline)
        text_widget.edit_reset()
        self._bind_text_change_tracking(
            text_widget, lambda name=label: self._mark_extra_dirty(name, raw=True)
        )
        info["highlighter"] = TextSyntaxHighlighter(
            text_widget, self._detect_language_for_label(label)
        )
        info["text_widget"] = text_widget

        scroll_y = ttk.Scrollbar(
            raw_frame, orient="vertical", command=text_widget.yview
        )
        scroll_y.grid(row=0, column=1, sticky="ns")
        text_widget.configure(yscrollcommand=scroll_y.set)
        scroll_x = ttk.Scrollbar(
            raw_frame, orient="horizontal", command=text_widget.xview
        )
        scroll_x.grid(row=1, column=0, sticky="ew")
        text_widget.configure(xscrollcommand=scroll_x.set)

        # --- Bottom buttons (outside the stack, fixed position) ---
        buttons = ttk.Frame(parent)
        buttons.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        status_text = (
            f"Loaded from {info['path'].name}"
            if info["path"]
            else f"Saving to {info['expected_path'].name}"
        )
        status_label = ttk.Label(buttons, text=status_text)
        status_label.pack(side="left", padx=(0, 10))
        info["status_label"] = status_label
        ttk.Button(
            buttons,
            text="Discard Changes",
            command=lambda name=label: self._reset_extra_file(name),
        ).pack(side="right", padx=6)
        save_button = ttk.Button(
            buttons, text="Save", command=lambda name=label: self._save_extra_file(name)
        )
        save_button.pack(side="right")
        ttk.Button(
            buttons, text="Redo", command=lambda name=label: self._redo_document(name)
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            buttons, text="Undo", command=lambda name=label: self._undo_document(name)
        ).pack(side="left")
        info["save_button"] = save_button
        self.document_save_buttons[label] = save_button

        # Build visual controls & select the starting mode
        self._render_extra_visual_sections(label, info)
        self._handle_extra_mode_change(label, initial=True)

    def _render_extra_visual_sections(self, label: str, info: Dict[str, Any]) -> None:
        frame = info.get("visual_frame")
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        info["param_controls"] = []
        query = self.settings_search_var.get().strip().casefold()
        rendered_sections = 0
        for s_index, section in enumerate(info.get("sections", [])):
            matching_parameters = set(self._matching_parameter_indices(section, query))
            if (
                query
                and not matching_parameters
                and query not in self._searchable_setting_text(section)
            ):
                continue
            rendered_sections += 1
            section_frame = ttk.LabelFrame(
                frame,
                text=section.get(
                    "displayName", section.get("name", f"Section {s_index + 1}")
                ),
            )
            section_frame.pack(fill="x", pady=(6, 6))
            section_frame.configure(padding=(6, 4))
            for p_index, param in enumerate(section.get("parameters", [])):
                if p_index not in matching_parameters:
                    continue
                label_text = param.get("label") or param["key"].replace("_", " ")
                desc_text = (param.get("description") or "").strip()
                comment_hint = self._comment_hint_for(label, param["key"])
                param_type = param.get("type", "string")
                ctrl_info: Dict[str, Any] = {
                    "section_index": s_index,
                    "param_index": p_index,
                    "param": param,
                    "type": param_type,
                }
                if param_type == "mapping":
                    mapping_value = param.get("value")
                    if not isinstance(mapping_value, MappingABC):
                        mapping_value = cast_value("mapping", mapping_value)
                    if mapping_value is None:
                        mapping_value = CommentedMap()
                    template = deepcopy(mapping_value)
                    param["_template"] = template
                    mapping_frame = ttk.LabelFrame(section_frame, text=label_text)
                    mapping_frame.pack(fill="x", padx=6, pady=2)
                    mapping_frame.columnconfigure(0, weight=1)
                    if desc_text:
                        description_label = ttk.Label(
                            mapping_frame,
                            text=self._short_help_text(desc_text),
                            wraplength=500,
                            justify="left",
                        )
                        description_label.pack(anchor="w", padx=4, pady=(0, 4))
                        self._attach_tooltip(description_label, desc_text)
                        self._attach_tooltip(mapping_frame, desc_text)
                    if comment_hint:
                        ttk.Label(
                            mapping_frame,
                            text=format_yaml_comment_hint(comment_hint),
                            foreground="#5B4A00",
                            wraplength=580,
                            justify="left",
                        ).pack(anchor="w", padx=4, pady=(0, 4))
                    registry: Dict[str, tk.StringVar] = {}
                    self._render_mapping_fields(
                        mapping_frame,
                        mapping_value,
                        param["key"],
                        registry,
                        lambda name=label, info_ref=ctrl_info: (
                            self._on_extra_mapping_changed(name, info_ref)
                        ),
                        row_width=100,
                    )
                    ctrl_info["mapping_registry"] = registry
                    ctrl_info["mapping_template"] = template
                    ctrl_info["mapping_base_path"] = param["key"]
                    ctrl_info["widget"] = mapping_frame
                    for issue in self._issues_for(label, param["key"]):
                        ttk.Label(
                            mapping_frame,
                            text=f"{issue['severity'].title()}: {issue['message']}",
                            foreground=self._issue_colour(issue["severity"]),
                            wraplength=600,
                            justify="left",
                        ).pack(anchor="w", padx=4, pady=(2, 3))
                    info["param_controls"].append(ctrl_info)
                    continue

                row = ttk.Frame(section_frame)
                row.pack(fill="x", pady=2, padx=6)
                row.columnconfigure(1, weight=1)
                row.columnconfigure(2, weight=1)
                key_label = ttk.Label(row, text=label_text)
                key_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
                if desc_text:
                    self._attach_tooltip(key_label, desc_text)
                if param_type == "boolean":
                    var = tk.BooleanVar(value=bool(param.get("value")))
                    ctrl_info["var"] = var
                    widget = ttk.Checkbutton(
                        row,
                        variable=var,
                        command=lambda name=label: self._on_extra_param_changed(name),
                    )
                    widget.grid(row=0, column=1, sticky="ew", padx=(0, 6))
                    ctrl_info["widget"] = widget
                elif param_type == "array" and self._is_simple_sequence(
                    param.get("value")
                ):
                    choices = (
                        self._choices_for_parameter(param["key"], param.get("value"))
                        if param["key"] == "technologies"
                        else None
                    )
                    editor, listbox = self._create_list_editor(
                        row,
                        param.get("value"),
                        lambda values, name=label, parameter=param: (
                            self._on_extra_list_changed(name, parameter, values)
                        ),
                        choices=choices,
                    )
                    editor.grid(row=0, column=1, sticky="ew", padx=(0, 6))
                    widget = listbox
                    ctrl_info["widget"] = listbox
                    ctrl_info["listbox"] = listbox
                    ctrl_info["list_choice_mode"] = bool(choices)
                elif param_type == "array":
                    widget = tk.Text(row, height=3, width=32, wrap="word")
                    value = param.get("value")
                    if isinstance(value, (list, dict)):
                        display = json.dumps(value, ensure_ascii=False, indent=2)
                    else:
                        display = "" if value is None else str(value)
                    widget.insert("1.0", display)
                    widget.grid(row=0, column=1, sticky="w", padx=(0, 6))
                    widget.bind(
                        "<KeyRelease>",
                        lambda _event, name=label: self._on_extra_param_changed(name),
                    )
                    ctrl_info["widget"] = widget
                else:
                    raw_value = param.get("value")
                    if param_type.startswith("list:"):
                        display_value = stringify_list_value(raw_value)
                    else:
                        display_value = "" if raw_value is None else str(raw_value)
                    var = tk.StringVar(value=display_value)
                    ctrl_info["var"] = var
                    input_frame = ttk.Frame(row)
                    input_frame.grid(row=0, column=1, sticky="ew", padx=(0, 6))
                    input_frame.columnconfigure(0, weight=1)
                    choices = self._choices_for_parameter(param["key"], raw_value)
                    if choices:
                        widget = ttk.Combobox(
                            input_frame,
                            textvariable=var,
                            values=choices,
                            state="normal",
                            width=24,
                        )
                    elif param_type in {"number", "integer"}:
                        minimum, maximum, increment = self._numeric_limits(
                            param["key"], param_type
                        )
                        widget = ttk.Spinbox(
                            input_frame,
                            textvariable=var,
                            from_=minimum,
                            to=maximum,
                            increment=increment,
                            width=24,
                        )
                    else:
                        widget = ttk.Entry(input_frame, textvariable=var, width=27)
                    widget.grid(row=0, column=0, sticky="ew")
                    unit = PARAMETER_UNITS.get(param["key"])
                    if unit:
                        ttk.Label(input_frame, text=unit).grid(
                            row=0, column=1, sticky="w", padx=(6, 0)
                        )
                    if param["key"] in PARAMETER_PICKERS:
                        ttk.Button(
                            input_frame,
                            text="Browse...",
                            command=lambda parameter=param["key"], variable=var: (
                                self._browse_for_parameter(parameter, variable)
                            ),
                        ).grid(row=0, column=2, sticky="w", padx=(6, 0))
                    var.trace_add(
                        "write",
                        lambda *_args, name=label: self._on_extra_param_changed(name),
                    )
                    ctrl_info["widget"] = widget
                if desc_text:
                    self._attach_tooltip(widget, desc_text)
                inline_issues = self._issues_for(label, param["key"])
                if desc_text or comment_hint or inline_issues:
                    help_frame = ttk.Frame(row)
                    help_frame.grid(row=0, column=2, sticky="nw", padx=(6, 0))
                    if desc_text:
                        help_label = ttk.Label(
                            help_frame,
                            text=self._short_help_text(desc_text),
                            wraplength=300,
                            justify="left",
                        )
                        help_label.pack(anchor="w")
                        self._attach_tooltip(help_label, desc_text)
                    if comment_hint:
                        ttk.Label(
                            help_frame,
                            text=format_yaml_comment_hint(comment_hint),
                            foreground="#5B4A00",
                            wraplength=320,
                            justify="left",
                        ).pack(anchor="w", pady=(2, 0))
                    for issue in inline_issues:
                        ttk.Label(
                            help_frame,
                            text=f"{issue['severity'].title()}: {issue['message']}",
                            foreground=self._issue_colour(issue["severity"]),
                            wraplength=360,
                            justify="left",
                        ).pack(anchor="w")
                info["param_controls"].append(ctrl_info)
        if query and rendered_sections == 0:
            ttk.Label(
                frame,
                text=f'No settings in {label} match "{query}".',
                foreground="#555555",
            ).pack(anchor="w", padx=8, pady=8)
        canvas = info.get("visual_canvas")
        if canvas:
            canvas.update_idletasks()
            canvas.yview_moveto(0.0)

    def _on_extra_param_changed(self, label: str) -> None:
        self._update_extra_sections_from_controls(label)
        self._mark_extra_dirty(label)

    def _on_extra_list_changed(
        self, label: str, param: Dict[str, Any], values: List[Any]
    ) -> None:
        param["value"] = values
        self._mark_extra_dirty(label)

    def _update_extra_sections_from_controls(self, label: str) -> None:
        info = self.extra_files.get(label)
        if not info:
            return
        for ctrl in info.get("param_controls", []):
            param = ctrl["param"]
            param_type = ctrl.get("type", "string")
            if param_type == "boolean":
                var = ctrl.get("var")
                param["value"] = bool(var.get()) if var is not None else False
            elif param_type in {"number", "integer"}:
                var = ctrl.get("var")
                if var is not None:
                    text = var.get().strip()
                    if not text:
                        param["value"] = None
                    else:
                        try:
                            numeric = float(text)
                        except ValueError:
                            param["value"] = None
                        else:
                            param["value"] = (
                                int(numeric)
                                if param_type == "integer" or numeric.is_integer()
                                else numeric
                            )
            elif param_type == "source":
                var = ctrl.get("var")
                param["value"] = cast_value("source", "" if var is None else var.get())
            elif param_type.startswith("list:"):
                var = ctrl.get("var")
                if var is not None:
                    param["value"] = _coerce_list_value(param_type, var.get())
                else:
                    param["value"] = []
            elif param_type == "mapping":
                registry = ctrl.get("mapping_registry")
                template = ctrl.get("mapping_template")
                base_key = ctrl.get("mapping_base_path", param["key"])
                if registry and template is not None:
                    new_value = rebuild_from_widgets(template, registry, base_key)
                    param["value"] = new_value
                    ctrl["mapping_template"] = deepcopy(new_value)
                    param["_template"] = deepcopy(new_value)
                else:
                    param["value"] = cast_value("mapping", param.get("value"))
            elif param_type == "array":
                listbox = ctrl.get("listbox")
                if listbox is not None:
                    indexes = (
                        listbox.curselection()
                        if ctrl.get("list_choice_mode")
                        else range(listbox.size())
                    )
                    values: List[Any] = []
                    for index in indexes:
                        text = str(listbox.get(index))
                        parsed: Any = text
                        if yaml is not None:
                            try:
                                candidate = yaml.safe_load(text)
                                if not isinstance(candidate, (MappingABC, list)):
                                    parsed = candidate
                            except Exception:
                                pass
                        values.append(parsed)
                    param["value"] = values
                    continue
                widget = ctrl.get("widget")
                if widget is not None:
                    text = widget.get("1.0", "end-1c").strip()
                    if not text:
                        param["value"] = []
                    else:
                        try:
                            param["value"] = json.loads(text)
                        except Exception:
                            if yaml is not None:
                                try:
                                    parsed = yaml.safe_load(text)
                                except Exception:
                                    parsed = text
                                param["value"] = parsed
                            else:
                                param["value"] = text
            else:
                var = ctrl.get("var")
                param["value"] = "" if var is None else var.get()

    def _update_extra_visual_controls(self, label: str) -> None:
        info = self.extra_files.get(label)
        if not info:
            return
        previous_suspend = self._suspend_dirty_tracking
        self._suspend_dirty_tracking = True
        for ctrl in info.get("param_controls", []):
            param = ctrl["param"]
            param_type = ctrl.get("type", "string")
            value = param.get("value")
            if param_type == "boolean":
                var = ctrl.get("var")
                if var is not None:
                    var.set(bool(value))
            elif param_type == "array":
                listbox = ctrl.get("listbox")
                if listbox is not None:
                    values = self._coerce_sequence_value(value)
                    if ctrl.get("list_choice_mode"):
                        selected = {str(item) for item in values}
                        listbox.selection_clear(0, "end")
                        for index in range(listbox.size()):
                            if str(listbox.get(index)) in selected:
                                listbox.selection_set(index)
                    else:
                        listbox.delete(0, "end")
                        for item in values:
                            listbox.insert("end", str(item))
                    continue
                widget = ctrl.get("widget")
                if widget is not None:
                    widget.delete("1.0", "end")
                    if isinstance(value, (list, dict)):
                        display = json.dumps(value, ensure_ascii=False, indent=2)
                    else:
                        display = "" if value is None else str(value)
                    widget.insert("1.0", display)
            elif param_type == "mapping":
                registry = ctrl.get("mapping_registry", {})
                mapping_value = value or CommentedMap()
                if not isinstance(mapping_value, MappingABC):
                    mapping_value = cast_value("mapping", mapping_value)
                base_key = param["key"]
                for full_path, var in registry.items():
                    if not isinstance(var, tk.StringVar):
                        continue
                    relative = (
                        full_path[len(base_key) :].lstrip(".")
                        if full_path.startswith(base_key)
                        else full_path
                    )
                    target = self._lookup_nested_value(mapping_value, relative)
                    if isinstance(target, (list, tuple, CommentedSeq)):
                        var.set(stringify_list_value(target))
                    elif target is None:
                        var.set("")
                    else:
                        var.set(str(target))
                ctrl["mapping_template"] = deepcopy(mapping_value)
            elif param_type.startswith("list:"):
                var = ctrl.get("var")
                if var is not None:
                    var.set(stringify_list_value(value))
            else:
                var = ctrl.get("var")
                if var is not None:
                    var.set("" if value is None else str(value))
        self._suspend_dirty_tracking = previous_suspend

    def _sync_extra_visual_to_text(self, label: str) -> None:
        info = self.extra_files.get(label)
        if not info:
            return
        text_widget: Optional[tk.Text] = info.get("text_widget")
        if not text_widget:
            return
        self._update_extra_sections_from_controls(label)
        yaml_text = self._serialize_sections_for_kind(
            info.get("kind"), info.get("sections")
        )
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", yaml_text)
        text_widget.edit_reset()
        info["raw_entry_text"] = yaml_text
        info["dirty"] = True

    def _sync_extra_text_to_visual(self, label: str) -> bool:
        info = self.extra_files.get(label)
        if not info:
            return True
        text_widget: Optional[tk.Text] = info.get("text_widget")
        if text_widget is None:
            return True
        yaml_text = text_widget.get("1.0", "end-1c")
        if info.get("kind") == "config_snakemake":
            sections = info.get("sections") or load_snakemake_sections()
            sections, error = self._config_snakemake_sections_from_yaml(
                yaml_text, sections
            )
            if error:
                messagebox.showerror("Invalid YAML", error)
                return False
            info["sections"] = sections
        else:
            updated, error = yaml_to_sections(info.get("sections", []), yaml_text)
            if error:
                messagebox.showerror("Invalid YAML", error)
                return False
            if updated is not None:
                info["sections"] = updated
        self._render_extra_visual_sections(label, info)
        self._reset_visual_history(label)
        return True

    def _handle_extra_mode_change(self, label: str, initial: bool = False) -> None:
        info = self.extra_files.get(label)
        if not info:
            return

        mode_var: Optional[tk.StringVar] = info.get("mode_var")
        if mode_var is None:
            return

        mode = mode_var.get()
        visual_container = info.get("visual_container")
        raw_frame = info.get("raw_frame")
        visual_canvas = info.get("visual_canvas")

        if mode == "visual":
            # Hide raw, show visual (inside the editor_stack at row=0,col=0)
            if raw_frame is not None:
                raw_frame.grid_remove()

            if not initial:
                # Pull YAML -> sections so visual is current
                if not self._sync_extra_text_to_visual(label):
                    mode_var.set("raw")
                    return

            if visual_container is not None:
                visual_container.grid(row=0, column=0, sticky="nsew")

            # Reset scroll to the very top to avoid any top gap
            if visual_canvas is not None:
                visual_canvas.update_idletasks()
                visual_canvas.yview_moveto(0.0)

        else:
            # Hide visual, show raw
            if visual_container is not None:
                visual_container.grid_remove()

            # Push sections -> YAML text so raw is current
            if info.get("dirty"):
                self._sync_extra_visual_to_text(label)

            if raw_frame is not None:
                raw_frame.grid(row=0, column=0, sticky="nsew")
            text_widget = info.get("text_widget")
            if text_widget is not None:
                info["raw_entry_text"] = text_widget.get("1.0", "end-1c")

    def _extra_sections_to_yaml(self, sections: Optional[List[Dict[str, Any]]]) -> str:
        data: Dict[str, Any] = {}
        if not sections:
            return ""
        for section in sections:
            for param in section.get("parameters", []):
                param_type = param.get("type", "string")
                value = param.get("value")
                if param_type.startswith("list:"):
                    value = _coerce_list_value(param_type, value)
                elif param_type in {"integer", "source"}:
                    value = cast_value(param_type, value)
                data[param["key"]] = value
        if yaml is not None:
            try:
                return yaml.safe_dump(
                    _plain_yaml_value(data), sort_keys=False, allow_unicode=True
                )
            except Exception:
                pass
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, ensure_ascii=False)
                lines.append(f"{key}: {rendered}")
            elif value is None:
                lines.append(f"{key}: null")
            elif isinstance(value, str) and any(ch.isspace() for ch in value):
                escaped = value.replace("\n", "\\n")
                lines.append(f'{key}: "{escaped}"')
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines) + "\n"

    def _serialize_sections_for_kind(
        self, kind: Optional[str], sections: Optional[List[Dict[str, Any]]]
    ) -> str:
        if kind == "config_snakemake":
            return self._config_snakemake_sections_to_yaml(sections or [])
        return self._extra_sections_to_yaml(sections or [])

    def _config_snakemake_sections_to_yaml(self, sections: List[Dict[str, Any]]) -> str:
        flat: Dict[str, Any] = {}
        for section in sections:
            for param in section.get("parameters", []):
                flat[param["key"]] = param.get("value")

        def _stringify(value: Any) -> str:
            return "" if value is None else str(value).strip()

        cores_value = self._coerce_integer_value(flat.get("cores", 4), default=4)
        snakefile_value = (
            _stringify(flat.get("snakefile", "snakemake_global")) or "snakemake_global"
        )
        study_regions = [
            str(item)
            for item in self._coerce_sequence_value(flat.get("study_region_name", []))
            if str(item).strip()
        ]
        scenario = _stringify(flat.get("scenario", ""))
        technologies = [
            str(item)
            for item in self._coerce_sequence_value(flat.get("technologies", []))
        ]
        weather_years_raw = self._coerce_sequence_value(flat.get("weather_years", []))
        weather_years: List[Any] = []
        for item in weather_years_raw:
            if isinstance(item, (int, float)):
                if isinstance(item, float) and not item.is_integer():
                    weather_years.append(item)
                else:
                    weather_years.append(int(item))
            else:
                text = str(item).strip()
                if not text:
                    continue
                if text.isdigit():
                    weather_years.append(int(text))
                else:
                    weather_years.append(text)
        stages = {
            key: self._coerce_boolean_value(flat.get(key, True), default=True)
            for key in SNAKEMAKE_STAGE_KEYS
        }
        data: Dict[str, Any] = {
            "study_region_name": study_regions,
            "scenario": scenario,
            "technologies": technologies,
            "cores": cores_value,
            "snakefile": snakefile_value,
            "weather_years": weather_years,
            "stages": stages,
        }
        if yaml is not None:
            try:
                return yaml.safe_dump(
                    _plain_yaml_value(data), sort_keys=False, allow_unicode=True
                )
            except Exception:
                pass
        return (
            f"study_region_name: {data['study_region_name']}\n"
            f"scenario: {data['scenario']}\n"
            f"technologies: {technologies}\n"
            f"cores: {data['cores']}\n"
            f"snakefile: {data['snakefile']}\n"
            f"weather_years: {data['weather_years']}\n"
            f"stages: {data['stages']}\n"
        )

    def _config_snakemake_sections_from_yaml(
        self, yaml_text: str, sections: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if yaml is None:
            return sections, "PyYAML is required to edit this file in visual mode."
        try:
            data = yaml.safe_load(yaml_text) or {}
        except Exception as exc:
            return sections, str(exc)
        if not isinstance(data, dict):
            return sections, "Expected a mapping at the top level."
        flat: Dict[str, Any] = {
            "snakefile": data.get("snakefile", "snakemake_global"),
            "cores": data.get("cores", 4),
            "study_region_name": self._coerce_sequence_value(
                data.get("study_region_name", [])
            ),
            "scenario": data.get("scenario", ""),
            "technologies": self._coerce_sequence_value(data.get("technologies", [])),
            "weather_years": self._coerce_sequence_value(data.get("weather_years", [])),
        }
        stages = data.get("stages") or {}
        if isinstance(stages, MappingABC):
            for key in SNAKEMAKE_STAGE_KEYS:
                flat[key] = self._coerce_boolean_value(
                    stages.get(key, True), default=True
                )
        else:
            for key in SNAKEMAKE_STAGE_KEYS:
                flat[key] = True
        for section in sections:
            for param in section.get("parameters", []):
                key = param["key"]
                value = flat.get(key, param.get("value"))
                param_type = param.get("type", "string")
                if param_type == "number":
                    default_val = 4 if key == "cores" else 0
                    param["value"] = self._coerce_integer_value(
                        value, default=default_val
                    )
                elif param_type == "boolean":
                    param["value"] = self._coerce_boolean_value(value)
                elif param_type == "array":
                    param["value"] = self._coerce_sequence_value(value)
                elif key == "weather_years":
                    param["value"] = self._stringify_weather_years_field(value)
                else:
                    param["value"] = "" if value is None else str(value)
        return sections, None

    def _document_is_dirty(self, label: str) -> bool:
        if label == "config.yaml":
            return self.config_dirty
        if label == "Snakefile":
            return self.snakefile_dirty
        if label == "advanced_data_prep_settings.yaml":
            return self.advanced_dirty
        info = self.extra_files.get(label)
        return bool(info and info.get("dirty"))

    def dirty_document_names(self) -> List[str]:
        return [
            label
            for category in CONFIGURATION_CATEGORIES
            for label in self.document_tabs
            if self.document_categories.get(label) == category
            and self._document_is_dirty(label)
        ]

    def has_unsaved_changes(self) -> bool:
        return bool(self.dirty_document_names())

    def _refresh_dirty_state_ui(self) -> None:
        dirty_names = set(self.dirty_document_names())
        for label, tab in self.document_tabs.items():
            owner = self.document_tab_notebooks.get(label)
            if owner is None or owner is self.config_notebook:
                continue
            title = self.document_tab_titles.get(label, label)
            try:
                owner.tab(tab, text=f"{title} *" if label in dirty_names else title)
            except tk.TclError:
                pass
        for category, tab in self.category_tabs.items():
            category_dirty = any(
                label in dirty_names
                for label, document_category in self.document_categories.items()
                if document_category == category
            )
            try:
                self.config_notebook.tab(
                    tab, text=f"{category} *" if category_dirty else category
                )
            except tk.TclError:
                pass
        for label, button in self.document_save_buttons.items():
            button.configure(state="normal" if label in dirty_names else "disabled")
        if hasattr(self, "save_all_button"):
            self.save_all_button.configure(
                state="normal" if dirty_names else "disabled"
            )
        if dirty_names and hasattr(self, "save_summary_status"):
            self.save_summary_status.configure(text="")
        try:
            self.master.tab(
                self, text="Configuration *" if dirty_names else "Configuration"
            )
        except (AttributeError, tk.TclError):
            pass

    def _select_document_tab(self, label: str) -> bool:
        tab = self.document_tabs.get(label)
        category = self.document_categories.get(label)
        if tab is None or category not in self.category_tabs:
            return False
        self.config_notebook.select(self.category_tabs[category])
        owner = self.document_tab_notebooks.get(label)
        if owner is not None and owner is not self.config_notebook:
            owner.select(tab)
        return True

    def _show_save_confirmation(self, message: str) -> None:
        if hasattr(self, "save_summary_status"):
            self.save_summary_status.configure(
                text=f"{message} ({datetime.now().strftime('%H:%M:%S')})"
            )

    def _visual_sections_for(self, label: str) -> Optional[List[Dict[str, Any]]]:
        if label == "config.yaml":
            return self.sections
        info = self.extra_files.get(label)
        if info is None:
            return None
        return info.get("sections")

    @classmethod
    def _semantic_editor_state(cls, value: Any) -> Any:
        """Return editor data without private rendering metadata."""
        if isinstance(value, MappingABC):
            return {
                key: cls._semantic_editor_state(item)
                for key, item in value.items()
                if not str(key).startswith("_")
            }
        if isinstance(value, (list, tuple, CommentedSeq)):
            return [cls._semantic_editor_state(item) for item in value]
        return value

    @classmethod
    def _editor_states_equal(cls, left: Any, right: Any) -> bool:
        return cls._semantic_editor_state(left) == cls._semantic_editor_state(right)

    def _initialize_visual_histories(self) -> None:
        self._reset_visual_history("config.yaml")
        for label, info in self.extra_files.items():
            if info.get("sections") is not None:
                self._reset_visual_history(label)

    def _reset_visual_history(self, label: str) -> None:
        sections = self._visual_sections_for(label)
        if sections is None:
            self._visual_histories.pop(label, None)
            return
        self._visual_histories[label] = {
            "undo": [],
            "redo": [],
            "current": deepcopy(sections),
        }

    def _record_visual_edit(self, label: str) -> None:
        if self._suspend_dirty_tracking:
            return
        sections = self._visual_sections_for(label)
        if sections is None:
            return
        history = self._visual_histories.get(label)
        if history is None:
            self._reset_visual_history(label)
            return
        current = deepcopy(sections)
        if current == history["current"]:
            return
        history["undo"].append(history["current"])
        if len(history["undo"]) > 100:
            del history["undo"][0]
        history["current"] = current
        history["redo"].clear()

    def _text_widget_for_document(self, label: str) -> Optional[tk.Text]:
        if label == "config.yaml":
            return self.config_text
        if label == "Snakefile":
            return self.snakefile_text
        if label == "advanced_data_prep_settings.yaml":
            return self.advanced_text
        info = self.extra_files.get(label)
        return info.get("text_widget") if info else None

    def _document_is_in_raw_mode(self, label: str) -> bool:
        if label == "config.yaml":
            return self.config_mode.get() == "raw"
        if label in {"Snakefile", "advanced_data_prep_settings.yaml"}:
            return True
        info = self.extra_files.get(label)
        if not info or info.get("sections") is None:
            return True
        mode_var = info.get("mode_var")
        return mode_var is None or mode_var.get() == "raw"

    def _mark_raw_document_from_text(self, label: str) -> None:
        widget = self._text_widget_for_document(label)
        if widget is None:
            return
        content = widget.get("1.0", "end-1c")
        if label == "config.yaml":
            baseline = self._config_source_text or ""
            self.config_dirty = content != baseline
            self.raw_dirty = content != getattr(
                self, "_config_raw_entry_text", baseline
            )
            self._update_config_status()
        elif label == "Snakefile":
            self.snakefile_dirty = content != self._snakefile_source_text
            self.snakefile_status.configure(
                text="Unsaved changes" if self.snakefile_dirty else "No unsaved changes"
            )
        elif label == "advanced_data_prep_settings.yaml":
            self.advanced_dirty = content != self._advanced_source_text
            self.advanced_status.configure(
                text="Unsaved changes" if self.advanced_dirty else "No unsaved changes"
            )
        else:
            info = self.extra_files.get(label)
            if not info:
                return
            info["dirty"] = content != info.get("baseline", "")
            status_label = info.get("status_label")
            if status_label:
                status_label.configure(
                    text="Unsaved changes"
                    if info["dirty"]
                    else f"Loaded from {info['expected_path'].name}"
                )
        if self._document_is_dirty(label):
            self._mark_validation_stale()
        self._refresh_dirty_state_ui()

    def _apply_visual_history_state(self, label: str, direction: str) -> None:
        history = self._visual_histories.get(label)
        if not history:
            return
        source = history[direction]
        if not source:
            self.bell()
            return
        opposite = "redo" if direction == "undo" else "undo"
        history[opposite].append(history["current"])
        target = deepcopy(source.pop())
        history["current"] = deepcopy(target)
        self._suspend_dirty_tracking = True
        try:
            if label == "config.yaml":
                self.sections = target
                self._on_settings_search_changed()
                self.config_dirty = not self._editor_states_equal(
                    self.sections, self.sections_baseline
                )
                self.raw_dirty = False
                self._update_config_status()
            else:
                info = self.extra_files[label]
                info["sections"] = target
                self._render_extra_visual_sections(label, info)
                info["dirty"] = not self._editor_states_equal(
                    target, info.get("sections_baseline")
                )
                status_label = info.get("status_label")
                if status_label:
                    status_label.configure(
                        text="Unsaved changes"
                        if info["dirty"]
                        else "No unsaved changes"
                    )
        finally:
            self._suspend_dirty_tracking = False
        if self._document_is_dirty(label):
            self._mark_validation_stale()
        self._refresh_dirty_state_ui()

    def _undo_document(self, label: str) -> None:
        if not self._document_is_in_raw_mode(label):
            self._apply_visual_history_state(label, "undo")
            return
        widget = self._text_widget_for_document(label)
        if widget is None:
            return
        try:
            widget.edit_undo()
        except tk.TclError:
            self.bell()
            return
        self._mark_raw_document_from_text(label)

    def _redo_document(self, label: str) -> None:
        if not self._document_is_in_raw_mode(label):
            self._apply_visual_history_state(label, "redo")
            return
        widget = self._text_widget_for_document(label)
        if widget is None:
            return
        try:
            widget.edit_redo()
        except tk.TclError:
            self.bell()
            return
        self._mark_raw_document_from_text(label)

    def _mark_extra_dirty(self, label: str, raw: bool = False) -> None:
        info = self.extra_files.get(label)
        if not info or self._suspend_dirty_tracking:
            return
        if raw:
            self._mark_raw_document_from_text(label)
            return
        self._record_visual_edit(label)
        info["dirty"] = not self._editor_states_equal(
            info.get("sections"), info.get("sections_baseline")
        )
        if info["dirty"]:
            self._mark_validation_stale()
        status_label = info.get("status_label")
        if status_label:
            status_label.configure(
                text="Unsaved changes" if info["dirty"] else "No unsaved changes"
            )
        self._refresh_dirty_state_ui()

    def _save_extra_file(self, label: str, validate: bool = True) -> bool:
        info = self.extra_files.get(label)
        if not info:
            return False
        if not info.get("dirty"):
            return True
        if validate and not self.validate_before_action(label, "save"):
            return False
        kind = info.get("kind")
        sections_data: Optional[List[Dict[str, Any]]] = info.get("sections")
        has_structured_sections = sections_data is not None
        text_widget: Optional[tk.Text] = info.get("text_widget")

        if has_structured_sections:
            mode_var: Optional[tk.StringVar] = info.get("mode_var")
            if mode_var is not None and mode_var.get() == "raw":
                if not self._sync_extra_text_to_visual(label):
                    return False
            else:
                self._update_extra_sections_from_controls(label)
            sections_list: List[Dict[str, Any]] = info.get("sections") or []
            serialized_content = self._serialize_sections_for_kind(kind, sections_list)
        else:
            if text_widget is None:
                return False
            serialized_content = text_widget.get("1.0", "end-1c")
            sections_list = []

        raw_save_path = info.get("save_path") or info.get("path")
        if isinstance(raw_save_path, Path):
            save_path = raw_save_path
        elif raw_save_path:
            save_path = Path(raw_save_path)
        else:
            save_path = None
        if save_path is None:
            filename = filedialog.asksaveasfilename(
                title=f"Save {label}",
                defaultextension=".yaml",
                initialfile=label,
                filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
            )
            if not filename:
                return False
            save_path = Path(filename)
        final_content = serialized_content
        used_round_trip = False
        if has_structured_sections and round_trip_available():
            try:
                if kind == "config_snakemake" and yaml is not None:
                    structured_content = yaml.safe_load(serialized_content) or {}
                    if not isinstance(structured_content, MappingABC):
                        raise ValueError(
                            "Expected a mapping at the root of config_snakemake.yaml"
                        )
                    final_content = save_mapping_round_trip(
                        save_path, structured_content
                    )
                else:
                    final_content = save_sections_round_trip(save_path, sections_list)
                used_round_trip = True
            except Exception:
                used_round_trip = False
        if not used_round_trip:
            try:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_text(serialized_content, encoding="utf-8")
                final_content = serialized_content
            except OSError as exc:
                messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
                return False

        if text_widget is not None:
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", final_content)
            text_widget.edit_reset()
            highlighter = info.get("highlighter")
            if isinstance(highlighter, TextSyntaxHighlighter):
                highlighter.refresh()

        info["baseline"] = final_content
        self._comment_help_cache.pop(label, None)
        info["dirty"] = False
        info["sections_baseline"] = deepcopy(info.get("sections"))
        info["save_path"] = save_path
        info["path"] = save_path
        info["expected_path"] = save_path
        if has_structured_sections:
            self._render_extra_visual_sections(label, info)
            self._update_extra_visual_controls(label)
            self._reset_visual_history(label)
        if kind == "config_snakemake":
            app = self.master.master
            if hasattr(app, "run_tab"):
                app.run_tab._refresh_snakemake_settings_display()
        status_label = info.get("status_label")
        if status_label:
            status_label.configure(text=f"Saved to {save_path.name}")
        self._refresh_dirty_state_ui()
        self._show_save_confirmation(f"Saved {label}")
        return True

    def _reset_extra_file(self, label: str) -> None:
        info = self.extra_files.get(label)
        if not info:
            return
        text_widget: Optional[tk.Text] = info.get("text_widget")
        baseline = info.get("baseline", "")
        sections = info.get("sections")
        kind = info.get("kind")
        if sections and baseline:
            if kind == "config_snakemake":
                updated_sections, error = self._config_snakemake_sections_from_yaml(
                    baseline, sections
                )
                if error:
                    messagebox.showerror("Invalid YAML", error)
                else:
                    info["sections"] = updated_sections
                    self._render_extra_visual_sections(label, info)
                    self._update_extra_visual_controls(label)
            else:
                updated, error = yaml_to_sections(sections, baseline)
                if error:
                    messagebox.showerror("Invalid YAML", error)
                elif updated is not None:
                    info["sections"] = updated
                self._render_extra_visual_sections(label, info)
                self._update_extra_visual_controls(label)
        if text_widget is not None:
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", baseline)
            text_widget.edit_reset()
            highlighter = info.get("highlighter")
            if isinstance(highlighter, TextSyntaxHighlighter):
                highlighter.refresh()
        info["dirty"] = False
        info["sections_baseline"] = deepcopy(info.get("sections"))
        if info.get("sections") is not None:
            self._reset_visual_history(label)
        status_label = info.get("status_label")
        if status_label:
            source = info.get("path")
            if source:
                status_label.configure(text=f"Loaded from {source.name}")
            else:
                expected = info.get("expected_path")
                name = expected.name if isinstance(expected, Path) else "file"
                status_label.configure(text=f"Saving to {name}")
        if kind == "config_snakemake":
            app = self.master.master
            if hasattr(app, "run_tab"):
                app.run_tab._refresh_snakemake_settings_display()
        self._refresh_dirty_state_ui()

    def _on_mode_change(self) -> None:
        if self.config_mode.get() == "visual" and self.raw_dirty:
            updated, error = yaml_to_sections(
                self.sections, self.config_text.get("1.0", "end-1c")
            )
            if error:
                messagebox.showerror("Invalid YAML", error)
                self.config_mode.set("raw")
                return
            if updated is not None:
                self.sections = updated
                self._on_settings_search_changed()
                self.raw_dirty = False
                self._reset_visual_history("config.yaml")
        self._refresh_config_view()

    def _refresh_config_view(self) -> None:
        mode = self.config_mode.get()
        if mode == "visual":
            self.raw_container.grid_remove()
            self.visual_container.grid()
            section_index = self._selected_actual_section_index()
            if section_index is not None:
                self._render_parameters(section_index)
            elif self.settings_search_var.get().strip():
                self._render_no_settings_match(self.settings_search_var.get().strip())
        else:
            self.visual_container.grid_remove()
            self.raw_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
            if self.enable_visual_editor:
                self._populate_raw_editor()
        self._update_config_status()

    def _populate_raw_editor(self) -> None:
        if not self.enable_visual_editor:
            return
        text = (
            self._config_source_text
            if not self.config_dirty and self._config_source_text is not None
            else sections_to_yaml(self.sections)
        )
        current = self.config_text.get("1.0", "end-1c")
        if current.strip() != text.strip():
            self.config_text.delete("1.0", "end")
            self.config_text.insert("1.0", text)
            self.raw_dirty = False
            self._refresh_config_highlight()
        self._config_raw_entry_text = self.config_text.get("1.0", "end-1c")
        self.config_text.edit_reset()

    @staticmethod
    def _searchable_setting_text(item: Mapping[str, Any]) -> str:
        return " ".join(
            str(item.get(field, ""))
            for field in ("name", "displayName", "key", "label", "description")
        ).casefold()

    def _matching_parameter_indices(
        self, section: Mapping[str, Any], query: str
    ) -> List[int]:
        parameters = section.get("parameters", [])
        if not query or query in self._searchable_setting_text(section):
            return list(range(len(parameters)))
        return [
            index
            for index, parameter in enumerate(parameters)
            if query in self._searchable_setting_text(parameter)
        ]

    def _selected_actual_section_index(self) -> Optional[int]:
        selected = self.section_listbox.curselection()
        if not selected:
            return None
        position = selected[0]
        if position >= len(self.filtered_section_indices):
            return None
        return self.filtered_section_indices[position]

    def _select_actual_section(
        self, section_index: int, *, render: bool = True
    ) -> bool:
        if section_index not in self.filtered_section_indices:
            return False
        position = self.filtered_section_indices.index(section_index)
        self.section_listbox.selection_clear(0, tk.END)
        self.section_listbox.selection_set(position)
        self.section_listbox.see(position)
        if render:
            self._render_parameters(section_index)
        return True

    def _on_settings_search_changed(self, *_args: Any) -> None:
        if self._handling_settings_search:
            return
        self._handling_settings_search = True
        try:
            self._refresh_settings_search_results()
        finally:
            self._handling_settings_search = False

    def _refresh_settings_search_results(self) -> None:
        query = self.settings_search_var.get().strip().casefold()
        current_section = self._selected_actual_section_index()
        self.filtered_section_indices = [
            index
            for index, section in enumerate(self.sections)
            if not query
            or query in self._searchable_setting_text(section)
            or self._matching_parameter_indices(section, query)
        ]
        labels = [
            self.sections[index].get("displayName", self.sections[index]["name"])
            for index in self.filtered_section_indices
        ]
        self.section_list_var.set(labels)
        self.settings_search_clear_button.configure(
            state="normal" if query else "disabled"
        )

        document_matches: List[Tuple[str, List[int]]] = []
        if self.filtered_section_indices:
            document_matches.append(("config.yaml", self.filtered_section_indices))
        for label, info in self.extra_files.items():
            sections = info.get("sections")
            if sections is None:
                continue
            matching_sections = [
                index
                for index, section in enumerate(sections)
                if not query
                or query in self._searchable_setting_text(section)
                or self._matching_parameter_indices(section, query)
            ]
            if matching_sections:
                document_matches.append((label, matching_sections))
            self._render_extra_visual_sections(label, info)

        if not query:
            self.settings_search_status.configure(text="")
            if self.filtered_section_indices:
                target = (
                    current_section
                    if current_section in self.filtered_section_indices
                    else self.filtered_section_indices[0]
                )
                self._select_actual_section(target)
            return

        matched_sections = sum(len(indices) for _label, indices in document_matches)
        matched_settings = 0
        for label, section_indices in document_matches:
            sections = (
                self.sections
                if label == "config.yaml"
                else self.extra_files[label].get("sections", [])
            )
            matched_settings += sum(
                len(self._matching_parameter_indices(sections[index], query))
                for index in section_indices
            )
        self.settings_search_status.configure(
            text=(
                f"{matched_settings} setting(s) in {matched_sections} section(s), "
                f"{len(document_matches)} file(s)"
                if document_matches
                else "No matching settings"
            )
        )

        if not document_matches:
            self.section_listbox.selection_clear(0, tk.END)
            self._render_no_settings_match(query)
            return

        first_label, first_sections = document_matches[0]
        if first_label == "config.yaml":
            self._select_document_tab("config.yaml")
            if self.config_mode.get() != "visual":
                self.config_mode.set("visual")
                self._on_mode_change()
            target = (
                current_section
                if current_section in first_sections
                else first_sections[0]
            )
            self._select_actual_section(target)
            return

        if not self.filtered_section_indices:
            self.section_listbox.selection_clear(0, tk.END)
            self._render_no_settings_match(query)
        info = self.extra_files[first_label]
        self._select_document_tab(first_label)
        mode_var = info.get("mode_var")
        if mode_var is not None and mode_var.get() != "visual":
            mode_var.set("visual")
            self._handle_extra_mode_change(first_label)
        self._render_extra_visual_sections(first_label, info)

    def _render_no_settings_match(self, query: str) -> None:
        for child in self.param_inner.winfo_children():
            child.destroy()
        self.param_vars.clear()
        self.param_widgets.clear()
        ttk.Label(
            self.param_inner,
            text=f'No settings match "{query}".',
            foreground="#555555",
            font=("Segoe UI", 11),
        ).grid(row=0, column=0, sticky="w", padx=8, pady=8)

    def _on_section_select(self, _event: tk.Event) -> None:
        section_index = self._selected_actual_section_index()
        if section_index is not None:
            self._render_parameters(section_index)

    def _render_parameters(self, section_index: int) -> None:
        for child in self.param_inner.winfo_children():
            child.destroy()
        self.param_vars.clear()
        self.param_widgets.clear()
        if section_index >= len(self.sections):
            return
        section = self.sections[section_index]
        query = self.settings_search_var.get().strip().casefold()
        matching_parameters = set(self._matching_parameter_indices(section, query))
        header = section.get("displayName", section["name"])
        ttk.Label(self.param_inner, text=header, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.param_inner.columnconfigure(1, weight=1)
        row_pointer = 1
        for idx, param in enumerate(section.get("parameters", [])):
            if idx not in matching_parameters:
                continue
            description = str(param.get("description") or "").strip()
            key = param["key"]
            comment_hint = self._comment_hint_for("config.yaml", key)
            value_type = param.get("type", "string")
            self.mapping_registries.pop((section_index, idx), None)
            if value_type == "mapping":
                mapping_value = param.get("value")
                if not isinstance(mapping_value, MappingABC):
                    mapping_value = cast_value("mapping", mapping_value)
                if mapping_value is None:
                    mapping_value = CommentedMap()
                template = deepcopy(mapping_value)
                param["_template"] = template
                param_path = make_path(section["name"], key)
                param["_base_path"] = param_path
                frame = ttk.LabelFrame(self.param_inner, text=key)
                frame.grid(
                    row=row_pointer,
                    column=0,
                    columnspan=2,
                    sticky="ew",
                    padx=(0, 10),
                    pady=2,
                )
                frame.columnconfigure(0, weight=1)
                if description:
                    description_label = ttk.Label(
                        frame,
                        text=self._short_help_text(description),
                        foreground="#555555",
                        wraplength=600,
                        anchor="w",
                        justify="left",
                    )
                    description_label.pack(anchor="w", padx=6, pady=(2, 2))
                    self._attach_tooltip(description_label, description)
                    self._attach_tooltip(frame, description)
                if comment_hint:
                    ttk.Label(
                        frame,
                        text=format_yaml_comment_hint(comment_hint),
                        foreground="#5B4A00",
                        wraplength=600,
                        justify="left",
                    ).pack(anchor="w", padx=6, pady=(0, 3))
                registry: Dict[str, tk.StringVar] = {}
                self._render_mapping_fields(
                    frame,
                    mapping_value,
                    param_path,
                    registry,
                    lambda s=section_index, p=idx: self._on_mapping_param_change(s, p),
                    row_width=100,
                )
                self.mapping_registries[(section_index, idx)] = registry
                self.param_vars[(section_index, idx)] = registry
                self.param_widgets[(section_index, idx)] = frame
                for issue in self._issues_for("config.yaml", key):
                    ttk.Label(
                        frame,
                        text=f"{issue['severity'].title()}: {issue['message']}",
                        foreground=self._issue_colour(issue["severity"]),
                        wraplength=600,
                        justify="left",
                    ).pack(anchor="w", padx=6, pady=(2, 3))
                row_pointer += 1
                continue
            key_label = ttk.Label(self.param_inner, text=key)
            key_label.grid(row=row_pointer, column=0, sticky="w", padx=(0, 10), pady=2)
            if description:
                self._attach_tooltip(key_label, description)
            if value_type == "boolean":
                var = tk.BooleanVar(value=bool(param.get("value")))
                widget = ttk.Checkbutton(
                    self.param_inner,
                    variable=var,
                    command=lambda idx=idx: self._on_param_toggle(section_index, idx),
                )
                widget.grid(row=row_pointer, column=1, sticky="w")
                self.param_vars[(section_index, idx)] = var
            elif value_type == "array" and self._is_simple_sequence(param.get("value")):
                choices = (
                    self._choices_for_parameter(key, param.get("value"))
                    if key == "technologies"
                    else None
                )
                editor, listbox = self._create_list_editor(
                    self.param_inner,
                    param.get("value"),
                    lambda values, s_index=section_index, p_index=idx: (
                        self._on_list_param_change(s_index, p_index, values)
                    ),
                    choices=choices,
                )
                editor.grid(row=row_pointer, column=1, sticky="ew")
                widget = listbox
                self.param_vars[(section_index, idx)] = listbox
            elif value_type == "array":
                widget = tk.Text(self.param_inner, height=4, width=40, wrap="word")
                current_value = param.get("value")
                if isinstance(current_value, (list, dict)):
                    display_text = json.dumps(
                        current_value, ensure_ascii=False, indent=2
                    )
                else:
                    display_text = "" if current_value is None else str(current_value)
                widget.insert("1.0", display_text)
                widget.grid(row=row_pointer, column=1, sticky="ew")
                widget.bind(
                    "<KeyRelease>",
                    lambda _event, s_index=section_index, p_index=idx, v_type=value_type, control=widget: (
                        self._on_text_param_change(s_index, p_index, v_type, control)
                    ),
                )
                self.param_vars[(section_index, idx)] = widget
            else:
                if value_type in {"number", "integer"}:
                    raw_initial = param.get("value")
                    initial = "" if raw_initial in (None, "") else str(raw_initial)
                elif value_type.startswith("list:"):
                    initial = stringify_list_value(param.get("value"))
                else:
                    raw_initial = param.get("value", "")
                    initial = "" if raw_initial is None else str(raw_initial)
                var = tk.StringVar(value=initial)
                control_frame = ttk.Frame(self.param_inner)
                control_frame.grid(row=row_pointer, column=1, sticky="ew")
                control_frame.columnconfigure(0, weight=1)
                choices = self._choices_for_parameter(key, param.get("value"))
                if choices:
                    widget = ttk.Combobox(
                        control_frame,
                        textvariable=var,
                        values=choices,
                        state="normal",
                        width=37,
                    )
                elif value_type in {"number", "integer"}:
                    minimum, maximum, increment = self._numeric_limits(key, value_type)
                    widget = ttk.Spinbox(
                        control_frame,
                        textvariable=var,
                        from_=minimum,
                        to=maximum,
                        increment=increment,
                        width=37,
                    )
                else:
                    widget = ttk.Entry(control_frame, textvariable=var, width=40)
                widget.grid(row=0, column=0, sticky="ew")
                unit = PARAMETER_UNITS.get(key)
                if unit:
                    ttk.Label(control_frame, text=unit).grid(
                        row=0, column=1, sticky="w", padx=(6, 0)
                    )
                if key in PARAMETER_PICKERS:
                    ttk.Button(
                        control_frame,
                        text="Browse...",
                        command=lambda parameter=key, variable=var: (
                            self._browse_for_parameter(parameter, variable)
                        ),
                    ).grid(row=0, column=2, sticky="w", padx=(6, 0))
                var.trace_add(
                    "write",
                    lambda *_, s_index=section_index, p_index=idx, v_type=value_type, variable=var: (
                        self._on_param_change(s_index, p_index, v_type, variable)
                    ),
                )
                self.param_vars[(section_index, idx)] = var
            self.param_widgets[(section_index, idx)] = widget
            inline_issues = self._issues_for("config.yaml", key)
            if description:
                self._attach_tooltip(widget, description)
            if description or comment_hint or inline_issues:
                help_frame = ttk.Frame(self.param_inner)
                help_frame.grid(
                    row=row_pointer, column=2, sticky="nw", padx=(8, 0), pady=2
                )
                if description:
                    help_label = ttk.Label(
                        help_frame,
                        text=self._short_help_text(description),
                        foreground="#555555",
                        wraplength=320,
                        justify="left",
                    )
                    help_label.pack(anchor="w")
                    self._attach_tooltip(help_label, description)
                if comment_hint:
                    ttk.Label(
                        help_frame,
                        text=format_yaml_comment_hint(comment_hint),
                        foreground="#5B4A00",
                        wraplength=340,
                        justify="left",
                    ).pack(anchor="w", pady=(2, 0))
                for issue in inline_issues:
                    ttk.Label(
                        help_frame,
                        text=f"{issue['severity'].title()}: {issue['message']}",
                        foreground=self._issue_colour(issue["severity"]),
                        wraplength=360,
                        justify="left",
                    ).pack(anchor="w")
            row_pointer += 1
        self.param_canvas.after_idle(lambda: self.param_canvas.yview_moveto(0.0))

    def _lookup_nested_value(
        self, mapping: Mapping[str, Any], relative_path: str
    ) -> Any:
        if not relative_path:
            return mapping
        current: Any = mapping
        for part in relative_path.split("."):
            if not part:
                continue
            if isinstance(current, MappingABC):
                current = current.get(part)
            else:
                return None
        return current

    def _render_mapping_fields(
        self,
        parent: tk.Widget,
        mapping_value: Mapping[str, Any],
        base_path: str,
        registry: Dict[str, tk.StringVar],
        on_change: Callable[[], None],
        *,
        anchor: str = "w",
        row_width: int = 100,
    ) -> None:
        if not isinstance(mapping_value, MappingABC):
            mapping = CommentedMap()
        else:
            mapping = mapping_value
        for key, sub_value in mapping.items():
            path = f"{base_path}.{key}" if base_path else key
            if isinstance(sub_value, MappingABC):
                frame = ttk.LabelFrame(parent, text=key)
                frame.pack(fill="x", padx=(6, 6), pady=3, anchor=anchor)
                frame.columnconfigure(0, weight=1)
                self._render_mapping_fields(
                    frame,
                    sub_value,
                    path,
                    registry,
                    on_change,
                    anchor=anchor,
                    row_width=row_width,
                )
                continue
            row = ttk.Frame(parent)
            row.pack(fill="x", padx=(6, 6), pady=2)
            ttk.Label(row, text=key, width=18).pack(side="left", padx=(0, 8))
            if isinstance(sub_value, (list, tuple, CommentedSeq)):
                initial = stringify_list_value(sub_value)
            elif sub_value is None:
                initial = ""
            else:
                initial = str(sub_value)
            var = tk.StringVar(value=initial)
            registry[path] = var
            var.trace_add("write", lambda *_: on_change())
            entry = ttk.Entry(row, textvariable=var, width=row_width)
            entry.pack(side="left", fill="x", expand=True)

    def _on_mapping_param_change(self, section_index: int, param_index: int) -> None:
        registry = self.mapping_registries.get((section_index, param_index))
        if registry is None:
            return
        param = self.sections[section_index]["parameters"][param_index]
        template = param.get("_template")
        if not isinstance(template, MappingABC):
            template = CommentedMap()
        base_key = param.get(
            "_base_path", make_path(self.sections[section_index]["name"], param["key"])
        )
        new_value = rebuild_from_widgets(template, registry, base_key)
        param["value"] = new_value
        param["_template"] = deepcopy(new_value)
        self._mark_config_dirty()

    def _on_extra_mapping_changed(self, label: str, ctrl_info: Dict[str, Any]) -> None:
        registry = ctrl_info.get("mapping_registry")
        if not registry:
            return
        param = ctrl_info["param"]
        template = ctrl_info.get("mapping_template")
        if not isinstance(template, MappingABC):
            template = CommentedMap()
        base_key = ctrl_info.get("mapping_base_path", param["key"])
        new_value = rebuild_from_widgets(template, registry, base_key)
        param["value"] = new_value
        ctrl_info["mapping_template"] = deepcopy(new_value)
        param["_template"] = deepcopy(new_value)
        self._mark_extra_dirty(label)

    def _on_param_toggle(self, section_index: int, param_index: int) -> None:
        var = self.param_vars.get((section_index, param_index))
        if not var:
            return
        self.sections[section_index]["parameters"][param_index]["value"] = bool(
            var.get()
        )
        self._mark_config_dirty()

    def _on_list_param_change(
        self, section_index: int, param_index: int, values: List[Any]
    ) -> None:
        self.sections[section_index]["parameters"][param_index]["value"] = values
        self._mark_config_dirty()

    def _on_param_change(
        self,
        section_index: int,
        param_index: int,
        value_type: str,
        variable: tk.Variable,
    ) -> None:
        raw_value = variable.get()
        if value_type in {"number", "integer"}:
            text = raw_value.strip()
            if not text:
                value = None
            else:
                try:
                    numeric = float(text)
                    value = int(numeric) if value_type == "integer" else numeric
                except ValueError:
                    value = None
        elif value_type == "source":
            value = cast_value("source", raw_value)
        elif value_type.startswith("list:"):
            value = _coerce_list_value(value_type, raw_value)
        else:
            value = raw_value
        self.sections[section_index]["parameters"][param_index]["value"] = value
        self._mark_config_dirty()

    def _on_text_param_change(
        self, section_index: int, param_index: int, value_type: str, widget: tk.Text
    ) -> None:
        text = widget.get("1.0", "end-1c")
        if value_type == "array":
            stripped = text.strip()
            if not stripped:
                value: Any = []
            else:
                try:
                    value = json.loads(stripped)
                except Exception:
                    if yaml is not None:
                        try:
                            parsed = yaml.safe_load(stripped)
                        except Exception:
                            parsed = stripped
                        value = parsed
                    else:
                        value = stripped
        elif value_type == "mapping":
            value = cast_value("mapping", text)
        else:
            value = text
        self.sections[section_index]["parameters"][param_index]["value"] = value
        self._mark_config_dirty()

    def _mark_config_dirty(self, raw: bool = False) -> None:
        if self._suspend_dirty_tracking:
            return
        if raw:
            self._mark_raw_document_from_text("config.yaml")
            return
        self._record_visual_edit("config.yaml")
        self.config_dirty = not self._editor_states_equal(
            self.sections, self.sections_baseline
        )
        if self.config_dirty:
            self._mark_validation_stale()
        self._update_config_status()
        self._refresh_dirty_state_ui()

    def _mark_validation_stale(self) -> None:
        if hasattr(self, "validation_status"):
            self.validation_status.configure(
                text="Configuration changed — validate again", foreground="#8A5A00"
            )

    def _update_config_status(self) -> None:
        if self.config_dirty:
            status = "Unsaved changes"
        elif self.config_save_path:
            status = f"Saved ({self.config_save_path.name})"
        else:
            status = "Saved"
        self.config_status.configure(text=status)

    def _save_all(self) -> None:
        dirty_names = self.dirty_document_names()
        if not dirty_names:
            return
        if not self.validate_before_action(None, "save"):
            return
        results: List[bool] = []
        for label in dirty_names:
            if label == "config.yaml":
                results.append(self._save_config(validate=False))
            elif label == "Snakefile":
                results.append(self._save_snakefile())
            elif label == "advanced_data_prep_settings.yaml":
                results.append(self._save_advanced_settings())
            else:
                results.append(self._save_extra_file(label, validate=False))
        saved_count = sum(results)
        if saved_count:
            self._show_save_confirmation(f"Saved {saved_count} file(s)")

    def _save_config(self, validate: bool = True) -> bool:
        if not self.config_dirty:
            return True
        if validate and not self.validate_before_action("config.yaml", "save"):
            return False
        saving_raw = self.config_mode.get() == "raw" or not self.enable_visual_editor
        if not self.config_save_path:
            self.config_save_path = CONFIGS_DIR / "config.yaml"
        if saving_raw:
            yaml_text = self.config_text.get("1.0", "end-1c")
            if self.enable_visual_editor:
                updated, error = yaml_to_sections(self.sections, yaml_text)
                if error:
                    messagebox.showerror("Invalid YAML", error)
                    return False
                if updated is not None:
                    self.sections = updated
                    self.sections_baseline = deepcopy(updated)
                    self.raw_dirty = False
            if not yaml_text.endswith("\n"):
                yaml_text += "\n"
        elif round_trip_available() and self.config_save_path.exists():
            try:
                round_trip_sections = deepcopy(self.sections)
                for section in round_trip_sections:
                    for param in section.get("parameters", []):
                        if param.get("type") == "boolean":
                            path = make_path(section.get("name", ""), param["key"])
                            param["value"] = ui_bool_to_numeric(
                                path, bool(param.get("value"))
                            )
                yaml_text = save_sections_round_trip(
                    self.config_save_path, round_trip_sections
                )
            except Exception as exc:
                messagebox.showerror(
                    "Save failed", f"Could not update config.yaml:\n{exc}"
                )
                return False
        else:
            yaml_text = sections_to_yaml(self.sections)
            if not yaml_text.endswith("\n"):
                yaml_text += "\n"
        try:
            if (
                saving_raw
                or not round_trip_available()
                or not self.config_save_path.exists()
            ):
                self.config_save_path.parent.mkdir(parents=True, exist_ok=True)
                self.config_save_path.write_text(yaml_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return False
        self._config_source_text = yaml_text
        self._comment_help_cache.pop("config.yaml", None)
        self.config_dirty = False
        self.raw_dirty = False
        self.sections_baseline = deepcopy(self.sections)
        self._reset_visual_history("config.yaml")
        self.config_text.edit_reset()
        self._update_config_status()
        self._refresh_dirty_state_ui()
        self._show_save_confirmation("Saved config.yaml")
        return True

    def _reset_config(self) -> None:
        selected_section = self._selected_actual_section_index()
        self.sections = deepcopy(self.sections_baseline)
        self.config_dirty = False
        self.raw_dirty = False
        if self.config_mode.get() == "visual":
            self._on_settings_search_changed()
            if selected_section is not None:
                self._select_actual_section(selected_section)
        else:
            if self.enable_visual_editor:
                self._populate_raw_editor()
            else:
                source_text = self._config_source_text
                if (
                    source_text is None
                    and self.config_save_path
                    and self.config_save_path.exists()
                ):
                    try:
                        source_text = self.config_save_path.read_text(encoding="utf-8")
                    except OSError:
                        source_text = None
                if source_text is not None:
                    self.config_text.delete("1.0", "end")
                    self.config_text.insert("1.0", source_text)
                    self._refresh_config_highlight()
        self.config_text.edit_reset()
        self._reset_visual_history("config.yaml")
        self._update_config_status()
        self._refresh_dirty_state_ui()

    def _mark_snakefile_dirty(self) -> None:
        if self._suspend_dirty_tracking:
            return
        self._mark_raw_document_from_text("Snakefile")

    def _save_snakefile(self) -> bool:
        if not self.snakefile_dirty:
            return True
        content = self.snakefile_text.get("1.0", "end-1c")
        if not self.snakefile_save_path:
            filename = filedialog.asksaveasfilename(
                title="Save Snakefile",
                defaultextension=".smk",
                initialfile="Snakefile",
                filetypes=[("Snakefile", "Snakefile"), ("All files", "*.*")],
            )
            if not filename:
                return False
            self.snakefile_save_path = Path(filename)
        try:
            self.snakefile_save_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return False
        self._snakefile_source_text = content
        self.snakefile_dirty = False
        self.snakefile_text.edit_reset()
        self.snakefile_status.configure(
            text=f"Saved to {self.snakefile_save_path.name}"
        )
        self._refresh_dirty_state_ui()
        self._show_save_confirmation("Saved Snakefile")
        return True

    def _reset_snakefile(self) -> None:
        self.snakefile_text.delete("1.0", "end")
        self.snakefile_text.insert("1.0", self._snakefile_source_text)
        self.snakefile_text.edit_reset()
        self.snakefile_dirty = False
        self.snakefile_status.configure(text="Reverted to saved content")
        self._refresh_snakefile_highlight()
        self._refresh_dirty_state_ui()

    def _mark_advanced_dirty(self) -> None:
        if self._suspend_dirty_tracking:
            return
        self._mark_raw_document_from_text("advanced_data_prep_settings.yaml")

    def _save_advanced_settings(self) -> bool:
        if not self.advanced_dirty:
            return True
        content = self.advanced_text.get("1.0", "end-1c")
        save_path = self.advanced_save_path
        if not save_path:
            initial_dir = (
                CONFIG_ADVANCED_SETTINGS_PATH.parent
                if CONFIG_ADVANCED_SETTINGS_PATH.parent.exists()
                else CONFIGS_DIR
            )
            filename = filedialog.asksaveasfilename(
                title="Save advanced_data_prep_settings.yaml",
                defaultextension=".yaml",
                initialdir=str(initial_dir),
                initialfile="advanced_data_prep_settings.yaml",
                filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
            )
            if not filename:
                return False
            save_path = Path(filename)
            self.advanced_save_path = save_path
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return False
        self._advanced_source_text = content
        self.advanced_dirty = False
        self.advanced_text.edit_reset()
        self.advanced_status.configure(text=f"Saved to {save_path.name}")
        self._refresh_dirty_state_ui()
        self._show_save_confirmation("Saved advanced settings")
        return True

    def _reset_advanced_settings(self) -> None:
        self.advanced_text.delete("1.0", "end")
        self.advanced_text.insert("1.0", self._advanced_source_text)
        self.advanced_text.edit_reset()
        self.advanced_dirty = False
        self._refresh_advanced_highlight()
        if self.advanced_save_path and self._advanced_source_text:
            self.advanced_status.configure(
                text=f"Reverted to {self.advanced_save_path.name}"
            )
        else:
            self.advanced_status.configure(text="Advanced settings cleared")
        self._refresh_dirty_state_ui()

    def get_config_path(self) -> Optional[Path]:
        """Return the saved config.yaml path, if one exists."""
        return self.config_save_path

    def get_snakefile_path(self) -> Optional[Path]:
        """Return the saved Snakefile path, if one exists."""
        return self.snakefile_save_path

    def get_snakefile_text(self) -> str:
        """Return the current Snakefile content from the editor."""
        return self.snakefile_text.get("1.0", "end-1c")

    def snakefile_has_unsaved_changes(self) -> bool:
        """Indicate whether the Snakefile has unsaved edits."""
        return self.snakefile_dirty

    def _enable_mousewheel(self, canvas: tk.Canvas) -> None:
        """Enable cross-platform mousewheel scrolling on a Canvas."""
        import sys

        def _on_mousewheel(event):
            # Windows / macOS use <MouseWheel>
            delta = -1 if sys.platform == "darwin" else int(-event.delta / 120)
            canvas.yview_scroll(delta, "units")

        # Bindings for Windows/macOS
        canvas.bind(
            "<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel)
        )
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Bindings for Linux (X11)
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))


class ProcessRunner:
    """Run subprocesses on a background thread and stream output back to Tk."""

    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen] = None
        self.reader_threads: List[threading.Thread] = []
        self.wait_thread: Optional[threading.Thread] = None
        self.widget: Optional[tk.Widget] = None
        self.queue: queue.Queue[Tuple[str, Any]] = queue.Queue()
        self.after_id: Optional[str] = None
        self.on_line: Optional[Callable[[str, str], None]] = None
        self.on_exit: Optional[Callable[[int], None]] = None
        self._lock = threading.Lock()
        self._stopping = False

    def run(
        self,
        widget: tk.Widget,
        cmd: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        on_line: Optional[Callable[[str, str], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None,
    ) -> None:
        with self._lock:
            if self.process:
                raise RuntimeError("Process already running")
            self.widget = widget
            self.on_line = on_line
            self.on_exit = on_exit
            self.queue = queue.Queue()
            self.reader_threads = []
            self.wait_thread = None
            self._stopping = False
            popen_kwargs: Dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "stdin": subprocess.PIPE,
                "text": True,
                "bufsize": 1,
                "universal_newlines": True,
            }
            if cwd:
                popen_kwargs["cwd"] = str(cwd)
            if env:
                popen_kwargs["env"] = env
            if os.name == "nt":
                popen_kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                )
            else:
                popen_kwargs["preexec_fn"] = os.setsid  # type: ignore[attr-defined]
            self.process = subprocess.Popen(cmd, **popen_kwargs)
        if self.process.stdout:
            self._start_reader(self.process.stdout, "info")
        if self.process.stderr:
            self._start_reader(self.process.stderr, "error")
        self.wait_thread = threading.Thread(target=self._wait_for_process, daemon=True)
        self.wait_thread.start()
        self._schedule_drain()

    def stop(self) -> None:
        with self._lock:
            proc = self.process
        if not proc:
            return
        self._stopping = True
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
        except OSError:
            pass
        try:
            proc.terminate()
        except OSError:
            pass

    def cancel(self) -> None:
        """Cancel any pending Tk callbacks."""
        if self.after_id and self.widget:
            try:
                self.widget.after_cancel(self.after_id)
            except tk.TclError:
                pass
        self.after_id = None

    def is_running(self) -> bool:
        with self._lock:
            return self.process is not None

    def stop_requested(self) -> bool:
        return self._stopping

    def send_input(self, data: str) -> None:
        with self._lock:
            proc = self.process
            stdin = proc.stdin if proc else None  # type: ignore[assignment]
        if not proc or not stdin:
            raise RuntimeError("Process is not running")
        text = data if data.endswith("\n") else f"{data}\n"
        try:
            stdin.write(text)
            stdin.flush()
        except Exception as exc:  # pragma: no cover - interactive fallback
            raise RuntimeError(f"Failed to send input: {exc}") from exc

    def _start_reader(self, stream: Any, level: str) -> None:
        def _reader() -> None:
            for raw_line in iter(stream.readline, ""):
                line = raw_line.rstrip("\r\n")
                self.queue.put(("line", level, line))
            try:
                stream.close()
            except Exception:
                pass

        thread = threading.Thread(target=_reader, daemon=True)
        self.reader_threads.append(thread)
        thread.start()

    def _wait_for_process(self) -> None:
        proc: Optional[subprocess.Popen]
        with self._lock:
            proc = self.process
        if not proc:
            return
        return_code = proc.wait()
        for thread in self.reader_threads:
            thread.join()
        self.queue.put(("exit", return_code))

    def _schedule_drain(self) -> None:
        if not self.widget:
            return
        if self.after_id:
            return
        self.after_id = self.widget.after(100, self._drain_queue)

    def _drain_queue(self) -> None:
        self.after_id = None
        exit_code: Optional[int] = None
        while True:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            if kind == "line":
                _, level, message = item
                if self.on_line:
                    self.on_line(level, message)
            elif kind == "exit":
                exit_code = item[1]
        if exit_code is not None:
            self._cleanup_process_handles()
            if self.on_exit:
                self.on_exit(exit_code)
        if (self.process is not None) or (not self.queue.empty()):
            self._schedule_drain()

    def _cleanup_process_handles(self) -> None:
        proc: Optional[subprocess.Popen]
        with self._lock:
            proc = self.process
            self.process = None
        if not proc:
            return
        for stream in (proc.stdout, proc.stderr, proc.stdin):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass


class PreflightDialog(tk.Toplevel):
    """Modal review of the exact run inputs and blocking preflight checks."""

    def __init__(self, master: tk.Widget, report: Mapping[str, Any]):
        super().__init__(master)
        self.report = report
        self.confirmed = False
        self.title("Run preflight")
        self.geometry("900x700")
        self.minsize(720, 560)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        errors = [
            item for item in report.get("issues", []) if item.get("severity") == "error"
        ]
        warnings = [
            item
            for item in report.get("issues", [])
            if item.get("severity") == "warning"
        ]
        if errors:
            heading = f"Preflight found {len(errors)} blocking problem(s)"
            color = "#B42318"
            detail = "Resolve the errors below before starting this run."
        elif warnings:
            heading = f"Ready to start with {len(warnings)} warning(s)"
            color = "#8A5A00"
            detail = "Review the warnings, then start when ready."
        else:
            heading = "Ready to start"
            color = "#1A7F37"
            detail = "All available preflight checks passed."

        header = ttk.Frame(self, padding=(14, 12, 14, 4))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            header, text=heading, font=("Segoe UI", 14, "bold"), foreground=color
        ).pack(anchor="w")
        ttk.Label(header, text=detail, foreground="#555555").pack(
            anchor="w", pady=(3, 0)
        )

        summary_frame = ttk.LabelFrame(self, text="Run summary", padding=8)
        summary_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 6))
        summary_frame.columnconfigure(1, weight=1)
        for row, (label, value) in enumerate(report.get("summary", {}).items()):
            ttk.Label(
                summary_frame, text=f"{label}:", font=("Segoe UI", 9, "bold")
            ).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=2)
            ttk.Label(
                summary_frame, text=str(value), wraplength=690, justify="left"
            ).grid(row=row, column=1, sticky="w", pady=2)

        details = ttk.Notebook(self)
        details.grid(row=2, column=0, sticky="nsew", padx=14, pady=6)

        files_frame = ttk.Frame(details, padding=6)
        files_frame.columnconfigure(0, weight=1)
        files_frame.rowconfigure(0, weight=1)
        details.add(files_frame, text=f"Files ({len(report.get('files', []))})")
        files_tree = ttk.Treeview(
            files_frame,
            columns=("status", "purpose", "path"),
            show="headings",
            selectmode="browse",
        )
        files_tree.heading("status", text="Status")
        files_tree.heading("purpose", text="Used for")
        files_tree.heading("path", text="Path")
        files_tree.column("status", width=85, stretch=False)
        files_tree.column("purpose", width=190, stretch=False)
        files_tree.column("path", width=560, stretch=True)
        files_tree.grid(row=0, column=0, sticky="nsew")
        files_scroll = ttk.Scrollbar(
            files_frame, orient="vertical", command=files_tree.yview
        )
        files_scroll.grid(row=0, column=1, sticky="ns")
        files_tree.configure(yscrollcommand=files_scroll.set)
        files_tree.tag_configure("missing", foreground="#B42318")
        files_tree.tag_configure("invalid", foreground="#B42318")
        files_tree.tag_configure("ready", foreground="#1A7F37")
        for item in report.get("files", []):
            status = str(item.get("status", "Unknown"))
            files_tree.insert(
                "",
                "end",
                values=(status, item.get("label", ""), item.get("path", "")),
                tags=(status.lower(),),
            )

        checks_frame = ttk.Frame(details, padding=6)
        checks_frame.columnconfigure(0, weight=1)
        checks_frame.rowconfigure(0, weight=1)
        details.add(checks_frame, text=f"Checks ({len(report.get('issues', []))})")
        checks_tree = ttk.Treeview(
            checks_frame,
            columns=("severity", "message"),
            show="headings",
            selectmode="browse",
        )
        checks_tree.heading("severity", text="Result")
        checks_tree.heading("message", text="Details")
        checks_tree.column("severity", width=90, stretch=False)
        checks_tree.column("message", width=720, stretch=True)
        checks_tree.grid(row=0, column=0, sticky="nsew")
        checks_scroll = ttk.Scrollbar(
            checks_frame, orient="vertical", command=checks_tree.yview
        )
        checks_scroll.grid(row=0, column=1, sticky="ns")
        checks_tree.configure(yscrollcommand=checks_scroll.set)
        checks_tree.tag_configure("error", foreground="#B42318")
        checks_tree.tag_configure("warning", foreground="#8A5A00")
        checks_tree.tag_configure("passed", foreground="#1A7F37")
        issues = report.get("issues", [])
        if issues:
            for issue in issues:
                severity = str(issue.get("severity", "warning"))
                checks_tree.insert(
                    "",
                    "end",
                    values=(severity.title(), issue.get("message", "")),
                    tags=(severity,),
                )
        else:
            checks_tree.insert(
                "",
                "end",
                values=("Passed", "No problems found by the available checks."),
                tags=("passed",),
            )
        if issues:
            details.select(checks_frame)

        footer = ttk.Frame(self, padding=(14, 6, 14, 14))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Cancel", command=self.destroy).grid(
            row=0, column=1, padx=(6, 0)
        )
        self.start_button = ttk.Button(footer, text="Start run", command=self._confirm)
        self.start_button.grid(row=0, column=2, padx=(6, 0))
        if errors:
            self.start_button.configure(state="disabled")

        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._confirm())
        self.update_idletasks()
        self._center_on_parent(master)
        self.grab_set()
        self.start_button.focus_set()

    def _center_on_parent(self, master: tk.Widget) -> None:
        parent = master.winfo_toplevel()
        x = parent.winfo_rootx() + max(
            0, (parent.winfo_width() - self.winfo_width()) // 2
        )
        y = parent.winfo_rooty() + max(
            0, (parent.winfo_height() - self.winfo_height()) // 2
        )
        self.geometry(f"+{x}+{y}")

    def _confirm(self) -> None:
        if str(self.start_button.cget("state")) == "disabled":
            return
        self.confirmed = True
        self.destroy()


class RunTab(ttk.Frame):
    """Execution tab that runs real commands and streams output."""

    STAGE_LABELS = {
        "spatial_data_prep": "Spatial data preparation",
        "exclusion": "Technology exclusion",
        "suitability": "Suitability",
        "weather_data_prep": "Weather data preparation",
        "weather_bias_adjust": "Weather bias adjustment",
        "energy_profiles": "Energy profiles",
        "snakemake": "Snakemake workflow",
    }

    def __init__(
        self, master: tk.Widget, config_tab: ConfigurationTab, results_tab: ResultsTab
    ):
        super().__init__(master)
        self.config_tab = config_tab
        self.results_tab = results_tab
        self.status = "idle"
        self.progress = tk.DoubleVar(value=0)
        self.execution_mode = tk.StringVar(value="single")
        self.selected_script = tk.StringVar(value="results_analysis")
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.after_id: Optional[str] = None
        self.runner = ProcessRunner()
        self.stop_requested = False
        self.reset_requested = False
        self.temp_snakefile_path: Optional[Path] = None
        self.snakemake_file_var = tk.StringVar()
        self.snakemake_cores_var = tk.IntVar()
        self.available_scripts = [
            {
                "id": "spatial_data_prep",
                "name": "spatial_data_prep.py",
                "description": "Prepare spatial datasets",
            },
            {
                "id": "weather_data_prep",
                "name": "weather_data_prep.py",
                "description": "Download weather data",
            },
            {
                "id": "exclusion",
                "name": "exclusion.py",
                "description": "Run exclusion analysis",
            },
            {
                "id": "suitability",
                "name": "suitability.py",
                "description": "Perform resource grade modeling",
            },
            {
                "id": "weather_bias_adjust",
                "name": "weather_bias_adjust.py",
                "description": "Adjust weather data biases",
            },
            {
                "id": "energy_profiles",
                "name": "energy_profiles.py",
                "description": "Generate energy production profiles",
            },
        ]
        self.expected_output_dir: Optional[Path] = None
        self.last_run_script_id: Optional[str] = None
        self.last_command_text = ""
        self.current_stage = ""
        self.current_region = ""
        self.current_technology = ""
        self.completed_jobs = 0
        self.total_jobs = 0
        self.issue_count = 0
        self.issue_link_counter = 0
        self.traceback_active = False
        self.current_run_log_path: Optional[Path] = None
        self.last_log_folder: Optional[Path] = None
        self.current_run_record_id: Optional[str] = None
        self.run_history = self._load_run_history()
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Run Script", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=10
        )
        self.status_badge = ttk.Label(self, text="Status: Idle")
        self.status_badge.grid(row=0, column=1, sticky="e", padx=10, pady=10)
        body = ttk.Frame(self)
        body.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10)
        body.columnconfigure(0, weight=1)
        mode_group = ttk.LabelFrame(body, text="Execution Mode")
        mode_group.grid(row=0, column=0, sticky="ew")
        ttk.Radiobutton(
            mode_group,
            text="Single Script",
            value="single",
            variable=self.execution_mode,
            command=self._on_mode_change,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Radiobutton(
            mode_group,
            text="Snakemake Workflow",
            value="snakemake",
            variable=self.execution_mode,
            command=self._on_mode_change,
        ).grid(row=0, column=1, sticky="w", padx=6, pady=6)
        self.script_frame = ttk.Frame(body)
        self.script_frame.grid(row=1, column=0, sticky="ew", pady=10)
        ttk.Label(self.script_frame, text="Select script:").grid(
            row=0, column=0, sticky="w"
        )
        script_names = [script["name"] for script in self.available_scripts]
        self.script_combo = ttk.Combobox(
            self.script_frame, values=script_names, state="readonly"
        )
        self.script_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.script_combo.current(0)
        self.selected_script.set(self.available_scripts[0]["id"])
        self.script_frame.columnconfigure(1, weight=1)
        self.script_combo.bind("<<ComboboxSelected>>", self._on_script_change)
        self.snakemake_options_frame = ttk.Frame(body)
        self.snakemake_options_frame.grid(row=1, column=0, sticky="ew", pady=10)
        self.snakemake_options_frame.columnconfigure(1, weight=1)
        ttk.Label(self.snakemake_options_frame, text="Snakefile:").grid(
            row=0, column=0, sticky="w"
        )
        self.snakemake_file_display = ttk.Label(
            self.snakemake_options_frame,
            textvariable=self.snakemake_file_var,
            anchor="w",
            relief="sunken",
        )
        self.snakemake_file_display.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(self.snakemake_options_frame, text="Cores:").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.snakemake_cores_display = ttk.Label(
            self.snakemake_options_frame,
            textvariable=self.snakemake_cores_var,
            width=6,
            relief="sunken",
            anchor="w",
        )
        self.snakemake_cores_display.grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0)
        )
        self.info_label = ttk.Label(
            body,
            text="Runs all rules defined in the Snakefile",
            wraplength=500,
            foreground="#555555",
        )
        controls = ttk.Frame(body)
        controls.grid(row=3, column=0, sticky="ew", pady=10)
        controls.columnconfigure((0, 1, 2, 3, 4), weight=1)
        ttk.Button(controls, text="Run", command=self.handle_run).grid(
            row=0, column=0, sticky="ew", padx=4
        )
        ttk.Button(controls, text="Stop", command=self.handle_stop).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(controls, text="Reset", command=self.handle_reset).grid(
            row=0, column=2, sticky="ew", padx=4
        )
        self.copy_command_button = ttk.Button(
            controls,
            text="Copy command",
            command=self._copy_last_command,
            state="disabled",
        )
        self.copy_command_button.grid(row=0, column=3, sticky="ew", padx=4)
        self.open_log_button = ttk.Button(
            controls, text="Open log folder", command=self._open_log_folder
        )
        self.open_log_button.grid(row=0, column=4, sticky="ew", padx=4)
        if not self.last_log_folder:
            self.open_log_button.configure(state="disabled")
        progress_frame = ttk.Frame(body)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=10)
        progress_frame.columnconfigure((1, 3), weight=1)
        ttk.Label(
            progress_frame, text="Current stage:", font=("Segoe UI", 9, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.current_stage_var = tk.StringVar(value="--")
        ttk.Label(progress_frame, textvariable=self.current_stage_var).grid(
            row=0, column=1, sticky="w", padx=(6, 18)
        )
        ttk.Label(progress_frame, text="Region:", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=2, sticky="w"
        )
        self.current_region_var = tk.StringVar(value="--")
        ttk.Label(progress_frame, textvariable=self.current_region_var).grid(
            row=0, column=3, sticky="w", padx=(6, 0)
        )
        self.jobs_var = tk.StringVar(value="Completed: 0   Remaining: --")
        ttk.Label(progress_frame, textvariable=self.jobs_var).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 3)
        )
        self.progress_bar = ttk.Progressbar(
            progress_frame, maximum=100, variable=self.progress
        )
        self.progress_bar.grid(row=2, column=0, columnspan=4, sticky="ew")
        status_frame = ttk.Frame(body)
        status_frame.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        status_frame.columnconfigure((0, 1, 2), weight=1)
        self.start_label = ttk.Label(status_frame, text="Started: --")
        self.start_label.grid(row=0, column=0, sticky="w")
        self.state_label = ttk.Label(status_frame, text="Status: Idle")
        self.state_label.grid(row=0, column=1, sticky="w")
        self.duration_label = ttk.Label(status_frame, text="Duration: --")
        self.duration_label.grid(row=0, column=2, sticky="w")
        self.run_feedback_notebook = ttk.Notebook(body)
        self.run_feedback_notebook.grid(row=6, column=0, sticky="nsew")

        output_frame = ttk.Frame(self.run_feedback_notebook)
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        self.run_feedback_notebook.add(output_frame, text="Output")
        self.log_text = tk.Text(
            output_frame,
            height=16,
            wrap="none",
            state="disabled",
            font=("Consolas", 10),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(
            output_frame, orient="vertical", command=self.log_text.yview
        )
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.issues_frame = ttk.Frame(self.run_feedback_notebook)
        self.issues_frame.columnconfigure(0, weight=1)
        self.issues_frame.rowconfigure(1, weight=1)
        self.run_feedback_notebook.add(self.issues_frame, text="Warnings & Errors (0)")
        ttk.Label(
            self.issues_frame,
            text="Warnings and errors are separated from normal output. Blue links open the related setting.",
            foreground="#555555",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 3))
        self.issue_text = tk.Text(
            self.issues_frame,
            height=16,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
        )
        self.issue_text.grid(row=1, column=0, sticky="nsew")
        issue_scroll = ttk.Scrollbar(
            self.issues_frame, orient="vertical", command=self.issue_text.yview
        )
        issue_scroll.grid(row=1, column=1, sticky="ns")
        self.issue_text.configure(yscrollcommand=issue_scroll.set)

        history_frame = ttk.Frame(self.run_feedback_notebook)
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)
        self.run_feedback_notebook.add(history_frame, text="Run history")
        self.run_history_tree = ttk.Treeview(
            history_frame,
            columns=(
                "started",
                "finished",
                "mode",
                "work",
                "regions",
                "status",
                "duration",
            ),
            show="headings",
            selectmode="browse",
        )
        for column, heading, width in (
            ("started", "Started", 145),
            ("finished", "Finished", 145),
            ("mode", "Mode", 90),
            ("work", "Stage(s)", 210),
            ("regions", "Region(s)", 150),
            ("status", "Exit status", 120),
            ("duration", "Duration", 80),
        ):
            self.run_history_tree.heading(column, text=heading)
            self.run_history_tree.column(
                column, width=width, stretch=column in {"work", "regions"}
            )
        self.run_history_tree.grid(row=0, column=0, sticky="nsew")
        history_scroll = ttk.Scrollbar(
            history_frame, orient="vertical", command=self.run_history_tree.yview
        )
        history_scroll.grid(row=0, column=1, sticky="ns")
        self.run_history_tree.configure(yscrollcommand=history_scroll.set)
        self.run_history_tree.bind("<Double-1>", self._open_selected_history_log)

        for tag, color in {
            "info": "#333333",
            "success": "#1a7f37",
            "warning": "#a66b00",
            "error": "#b42318",
        }.items():
            self.log_text.tag_configure(tag, foreground=color)
            self.issue_text.tag_configure(tag, foreground=color)
        body.rowconfigure(6, weight=1)
        self._refresh_run_history_tree()
        self._on_mode_change()
        self._update_status_labels()
        self._refresh_snakemake_settings_display()

    def _on_mode_change(self) -> None:
        is_single = self.execution_mode.get() == "single"
        if is_single:
            self.script_frame.grid()
            self.snakemake_options_frame.grid_remove()
            self.info_label.grid_remove()
        else:
            self.script_frame.grid_remove()
            self.snakemake_options_frame.grid(row=1, column=0, sticky="ew", pady=10)
            self.info_label.grid(row=2, column=0, sticky="ew", pady=(0, 10))
            self._refresh_snakemake_settings_display()
        self._update_status_labels()

    def _on_script_change(self, _event: tk.Event) -> None:
        index = self.script_combo.current()
        if index >= 0:
            self.selected_script.set(self.available_scripts[index]["id"])

    def _load_run_history(self) -> List[Dict[str, Any]]:
        if not RUN_HISTORY_PATH.is_file():
            return []
        try:
            data = json.loads(RUN_HISTORY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        records = [record for record in data if isinstance(record, dict)][:200]
        for record in records:
            if record.get("status") == "Running":
                record["status"] = "Interrupted"
                record["exit_status"] = "Interrupted"
        for record in records:
            log_file = self._resolve_preflight_path(record.get("log_file"))
            if log_file and log_file.parent.is_dir():
                self.last_log_folder = log_file.parent
                break
        return records

    def _save_run_history(self) -> Optional[str]:
        try:
            RUN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            temp_path = RUN_HISTORY_PATH.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps(self.run_history[:200], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temp_path.replace(RUN_HISTORY_PATH)
        except OSError as exc:
            return str(exc)
        return None

    def _refresh_run_history_tree(self) -> None:
        if not hasattr(self, "run_history_tree"):
            return
        self.run_history_tree.delete(*self.run_history_tree.get_children())
        for record in self.run_history:
            duration = record.get("duration_seconds")
            duration_text = (
                f"{int(duration)}s" if isinstance(duration, (int, float)) else "--"
            )
            stages = record.get("stages") or [record.get("script_id", "")]
            regions = record.get("regions") or []
            self.run_history_tree.insert(
                "",
                "end",
                iid=str(record.get("id", len(self.run_history_tree.get_children()))),
                values=(
                    str(record.get("started_at", "")).replace("T", " ")[:19],
                    str(record.get("finished_at") or "").replace("T", " ")[:19] or "--",
                    record.get("mode", ""),
                    ", ".join(
                        str(value).replace("_", " ") for value in stages if value
                    ),
                    ", ".join(str(value) for value in regions),
                    record.get("exit_status", record.get("status", "")),
                    duration_text,
                ),
            )

    def _begin_run_record(
        self, report: Mapping[str, Any], command: List[Any], cwd: Path
    ) -> None:
        now = datetime.now()
        run_id = now.strftime("%Y%m%d_%H%M%S_%f")
        script_id = str(report.get("script_id") or "run")
        safe_script = re.sub(r"[^A-Za-z0-9_.-]+", "_", script_id)
        log_path = RUN_LOG_DIR / f"{run_id}_{safe_script}.log"
        self.current_run_log_path = log_path
        self.last_log_folder = RUN_LOG_DIR
        self.current_run_record_id = run_id
        context = report.get("run_context", {})
        stages = list(context.get("stages", [])) if isinstance(context, Mapping) else []
        regions = (
            list(context.get("regions", [])) if isinstance(context, Mapping) else []
        )
        technologies = (
            list(context.get("technologies", []))
            if isinstance(context, Mapping)
            else []
        )
        record = {
            "id": run_id,
            "started_at": now.isoformat(timespec="seconds"),
            "finished_at": None,
            "mode": self.execution_mode.get(),
            "script_id": script_id,
            "stages": stages,
            "regions": regions,
            "technologies": technologies,
            "command": self._format_command([str(part) for part in command]),
            "cwd": str(cwd),
            "status": "Running",
            "exit_status": "Running",
            "exit_code": None,
            "duration_seconds": None,
            "log_file": str(log_path),
        }
        self.run_history.insert(0, record)
        self.run_history = self.run_history[:200]
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                f"Started: {record['started_at']}\n"
                f"Mode: {record['mode']}\n"
                f"Command: {record['command']}\n"
                f"Working directory: {record['cwd']}\n\n",
                encoding="utf-8",
            )
        except OSError:
            self.current_run_log_path = None
        history_error = self._save_run_history()
        self._refresh_run_history_tree()
        self.open_log_button.configure(state="normal")
        if history_error:
            self.add_log("warning", f"Run history could not be saved: {history_error}")

    def _finish_run_record(self, exit_code: Optional[int], status: str) -> None:
        if not self.current_run_record_id:
            return
        now = datetime.now()
        for record in self.run_history:
            if record.get("id") != self.current_run_record_id:
                continue
            record["finished_at"] = now.isoformat(timespec="seconds")
            record["status"] = status
            record["exit_code"] = exit_code
            record["exit_status"] = (
                f"{exit_code} ({status})" if exit_code is not None else status
            )
            if self.start_time:
                record["duration_seconds"] = max(
                    0, round(time.time() - self.start_time, 1)
                )
            break
        self._save_run_history()
        self._refresh_run_history_tree()
        self.current_run_record_id = None

    def _append_run_log(self, line: str) -> None:
        if not self.current_run_log_path:
            return
        try:
            with self.current_run_log_path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
        except OSError:
            self.current_run_log_path = None

    def _copy_last_command(self) -> None:
        if not self.last_command_text:
            return
        self.clipboard_clear()
        self.clipboard_append(self.last_command_text)
        self.add_log("success", "Command copied to the clipboard.")

    def _history_record_for_selection(self) -> Optional[Dict[str, Any]]:
        if not hasattr(self, "run_history_tree"):
            return None
        selection = self.run_history_tree.selection()
        if not selection:
            return None
        return next(
            (
                record
                for record in self.run_history
                if str(record.get("id")) == selection[0]
            ),
            None,
        )

    def _open_path_in_file_manager(self, path: Path) -> None:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _open_log_folder(self) -> None:
        record = self._history_record_for_selection()
        folder = self.last_log_folder
        if record:
            selected_log = self._resolve_preflight_path(record.get("log_file"))
            if selected_log:
                folder = selected_log.parent
        if not folder or not folder.is_dir():
            messagebox.showwarning(
                "Log Folder", "No run log folder is available yet.", parent=self
            )
            return
        try:
            self._open_path_in_file_manager(folder)
        except OSError as exc:
            messagebox.showerror(
                "Log Folder", f"Could not open the log folder:\n{exc}", parent=self
            )

    def _open_selected_history_log(self, _event: Optional[tk.Event] = None) -> None:
        record = self._history_record_for_selection()
        if not record:
            return
        log_path = self._resolve_preflight_path(record.get("log_file"))
        if log_path and log_path.parent.is_dir():
            self.last_log_folder = log_path.parent
            self._open_log_folder()

    def _open_failure_setting(self, file_name: str, key: str) -> None:
        try:
            self.master.select(self.config_tab)  # type: ignore[attr-defined]
        except (AttributeError, tk.TclError):
            pass
        self.config_tab._open_validation_issue({"file": file_name, "key": key})

    def _failure_config_target(self, message: str) -> Optional[Tuple[str, str]]:
        lower = message.lower()
        keyword_targets = (
            (("dem", "elevation"), ("config.yaml", "DEM_filename")),
            (("landcover", "land cover"), ("config.yaml", "landcover_source")),
            (("protected area", "wdpa"), ("config.yaml", "protected_areas_source")),
            (("osm", "overpass", "geofabrik"), ("config.yaml", "OSM_source")),
            (
                ("weather", "cutout", "era5"),
                ("config.yaml", "weather_external_data_path"),
            ),
            (("country code",), ("config.yaml", "country_code")),
            (("crs", "projection"), ("config.yaml", "CRS_manual")),
            (("resource grade", "input area"), ("config.yaml", "input_area")),
        )
        for keywords, target in keyword_targets:
            if any(keyword in lower for keyword in keywords):
                return target
        if self.current_stage == "suitability":
            return ("suitability.yaml", "<yaml>")
        if self.current_stage == "exclusion" and self.current_technology:
            return (f"{self.current_technology}.yaml", "<yaml>")
        stage_targets = {
            "spatial_data_prep": ("config.yaml", "study_region_name"),
            "exclusion": ("config.yaml", "technology"),
            "weather_data_prep": ("config.yaml", "weather_data_extend"),
            "weather_bias_adjust": ("config.yaml", "weather_bias_correction"),
            "energy_profiles": ("config.yaml", "input_area"),
        }
        return stage_targets.get(self.current_stage)

    def add_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        if level in {"warning", "error"}:
            context = " / ".join(
                part
                for part in (
                    self.STAGE_LABELS.get(self.current_stage, self.current_stage),
                    self.current_region,
                )
                if part
            )
            display = f"[{timestamp}] {level.upper()}"
            if context:
                display += f" [{context}]"
            display += f" {message}"
            target = self._failure_config_target(message) if level == "error" else None
            self.issue_text.configure(state="normal")
            self.issue_text.insert("end", display, level)
            if target:
                self.issue_link_counter += 1
                link_tag = f"issue_link_{self.issue_link_counter}"
                self.issue_text.insert("end", "  Open related setting", (link_tag,))
                self.issue_text.tag_configure(
                    link_tag, foreground="#0D5D9B", underline=True
                )
                self.issue_text.tag_bind(
                    link_tag,
                    "<Button-1>",
                    lambda _event, file_name=target[0], key=target[1]: (
                        self._open_failure_setting(file_name, key)
                    ),
                )
                self.issue_text.tag_bind(
                    link_tag,
                    "<Enter>",
                    lambda _event: self.issue_text.configure(cursor="hand2"),
                )
                self.issue_text.tag_bind(
                    link_tag,
                    "<Leave>",
                    lambda _event: self.issue_text.configure(cursor=""),
                )
            self.issue_text.insert("end", "\n")
            self.issue_text.configure(state="disabled")
            self.issue_text.see("end")
            self.issue_count += 1
            self.run_feedback_notebook.tab(
                self.issues_frame, text=f"Warnings & Errors ({self.issue_count})"
            )
            if level == "error":
                self.run_feedback_notebook.select(self.issues_frame)
        else:
            tag = level if level in {"info", "success"} else "info"
            self.log_text.configure(state="normal")
            self.log_text.insert("end", formatted + "\n", tag)
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
        self._append_run_log(formatted)

    def _update_status_labels(self) -> None:
        self.status_badge.configure(text=f"Status: {self.status.capitalize()}")
        start_display = (
            datetime.fromtimestamp(self.start_time).strftime("%H:%M:%S")
            if self.start_time
            else "--"
        )
        self.start_label.configure(text=f"Started: {start_display}")
        duration_text = "--"
        if self.start_time:
            end = self.end_time or time.time()
            duration_text = f"{int(end - self.start_time)}s"
        self.duration_label.configure(text=f"Duration: {duration_text}")
        self.state_label.configure(text=f"Status: {self.status.capitalize()}")

    def _clear_logs(self) -> None:
        for widget in (self.log_text, self.issue_text):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.configure(state="disabled")
        self.issue_count = 0
        self.issue_link_counter = 0
        self.traceback_active = False
        self.run_feedback_notebook.tab(self.issues_frame, text="Warnings & Errors (0)")

    def _resolve_results_json_path(self) -> Path:
        base_dir = self.expected_output_dir or PARENT_DIR
        json_path = base_dir / "aggregated_available_land.json"
        try:
            return json_path.resolve()
        except Exception:
            return json_path

    def _update_results_tab_with_json(self) -> None:
        if self.last_run_script_id != "results_analysis":
            return
        json_path = self._resolve_results_json_path()
        status, message, _ = self.results_tab.display_aggregated_json(json_path)
        if status == "success":
            self.add_log("info", message)
        elif status in {"missing", "empty"}:
            self.add_log("warning", message)
        else:
            self.add_log("error", message)

    def _start_duration_timer(self) -> None:
        self._cancel_duration_timer()
        if self.status == "running":
            self.after_id = self.after(1000, self._tick_duration)

    def _cancel_duration_timer(self) -> None:
        if self.after_id:
            try:
                self.after_cancel(self.after_id)
            except tk.TclError:
                pass
        self.after_id = None

    def _tick_duration(self) -> None:
        self.after_id = None
        if self.status == "running":
            self._update_status_labels()
            self.after_id = self.after(1000, self._tick_duration)

    def _expected_job_count(self, report: Mapping[str, Any]) -> int:
        context = report.get("run_context", {})
        if not isinstance(context, Mapping):
            return 1
        if self.execution_mode.get() != "snakemake":
            return 1
        region_count = max(1, len(context.get("regions", [])))
        technology_count = max(1, len(context.get("technologies", [])))
        year_count = max(1, len(context.get("weather_years", [])))
        stages = set(context.get("stages", []))
        total = 1  # Snakemake's final `all` job.
        if "spatial_data_prep" in stages:
            total += region_count
        if "exclusion" in stages:
            total += region_count * technology_count
        if "suitability" in stages:
            total += region_count
        if "weather_data_prep" in stages:
            total += region_count * year_count
        if "weather_bias_adjust" in stages:
            total += region_count
        if "energy_profiles" in stages:
            total += region_count * technology_count * year_count
        return max(1, total)

    def _initialize_run_feedback(self, report: Mapping[str, Any]) -> None:
        context = report.get("run_context", {})
        context = context if isinstance(context, Mapping) else {}
        stages = list(context.get("stages", []))
        regions = list(context.get("regions", []))
        self.current_stage = stages[0] if stages else str(report.get("script_id") or "")
        self.current_region = str(regions[0]) if regions else ""
        self.current_technology = ""
        self.completed_jobs = 0
        self.total_jobs = self._expected_job_count(report)
        self._refresh_progress_feedback()

    def _refresh_progress_feedback(self) -> None:
        self.current_stage_var.set(
            self.STAGE_LABELS.get(
                self.current_stage, self.current_stage.replace("_", " ").title()
            )
            if self.current_stage
            else "--"
        )
        self.current_region_var.set(self.current_region or "--")
        if self.total_jobs > 0:
            self.completed_jobs = min(self.completed_jobs, self.total_jobs)
            remaining = max(0, self.total_jobs - self.completed_jobs)
            self.jobs_var.set(
                f"Completed: {self.completed_jobs}   Remaining: {remaining}   Total: {self.total_jobs}"
            )
            if self.status == "running":
                self.progress.set((self.completed_jobs / self.total_jobs) * 100)
        else:
            self.jobs_var.set(f"Completed: {self.completed_jobs}   Remaining: --")

    def _classify_process_message(self, raw_level: str, message: str) -> str:
        lower = message.lower()
        if "traceback (most recent call last)" in lower:
            self.traceback_active = True
            return "error"
        if self.traceback_active:
            if re.match(r"^[A-Za-z_][\w.]*?(?:Error|Exception):", message.strip()):
                self.traceback_active = False
            return "error"
        if re.search(r"\bwarning\b|\bwarn:|userwarning|futurewarning", lower):
            return "warning"
        if re.search(
            r"traceback|\berror\b|exception|\bfailed\b|\bfailure\b|fatal|"
            r"file.?not.?found|no such file|missinginput|ruleexception|non-zero|"
            r"not found|cannot open|terminated by signal",
            lower,
        ):
            return "error"
        if re.search(
            r"finished job|successfully|completed successfully|\bdone!?$", lower
        ):
            return "success"
        # Snakemake and several Python libraries write routine progress to stderr.
        return "info"

    def _update_run_context_from_output(self, message: str) -> None:
        stripped = message.strip()
        failed_match = re.search(
            r"Error in rule\s+([A-Za-z0-9_-]+)", stripped, re.IGNORECASE
        )
        rule_match = re.match(r"(?:localrule|rule)\s+([A-Za-z0-9_-]+):\s*$", stripped)
        if failed_match:
            self.current_stage = failed_match.group(1)
        elif rule_match and rule_match.group(1) != "all":
            self.current_stage = rule_match.group(1)

        lower = stripped.lower()
        if "weather data preparation" in lower:
            self.current_stage = "weather_data_prep"
        elif lower.startswith("exclusion for"):
            self.current_stage = "exclusion"

        wildcard_match = re.search(r"wildcards:\s*(.+)$", stripped, re.IGNORECASE)
        measures_match = re.search(r"measures:\s*(.+)$", stripped, re.IGNORECASE)
        values_text = (
            wildcard_match.group(1)
            if wildcard_match
            else (measures_match.group(1) if measures_match else "")
        )
        if values_text:
            for key, value in re.findall(r"([A-Za-z_]+)=([^,]+)", values_text):
                clean_value = value.strip()
                if key in {"region", "study_region", "study_region_name"}:
                    self.current_region = clean_value
                elif key == "technology":
                    self.current_technology = clean_value

        finished_match = re.search(r"Finished job\s+\d+", stripped, re.IGNORECASE)
        if finished_match:
            self.completed_jobs = min(self.total_jobs, self.completed_jobs + 1)
        steps_match = re.search(r"(\d+)\s+of\s+(\d+)\s+steps", stripped, re.IGNORECASE)
        if steps_match:
            self.completed_jobs = int(steps_match.group(1))
            self.total_jobs = max(1, int(steps_match.group(2)))
        if "nothing to be done" in lower:
            self.completed_jobs = self.total_jobs
        self._refresh_progress_feedback()

    def _start_spinner(self) -> None:
        if self.total_jobs > 0:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self._refresh_progress_feedback()
        else:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(10)

    def _stop_spinner(self) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")

    def _format_command(self, cmd: List[str]) -> str:
        if hasattr(shlex, "join"):
            return shlex.join(cmd)
        return " ".join(cmd)

    def _resolve_script_path(self, script_name: str) -> Path:
        candidates = [
            PARENT_DIR / script_name,
            CURRENT_DIR / script_name,
            PARENT_DIR / "scripts" / script_name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError(
            f"Could not find {script_name} in the expected locations."
        )

    def _load_snakemake_settings(self) -> Tuple[str, int]:
        default_snakefile = "Snakefile"
        default_cores = 4
        path = CONFIGS_DIR / "config_snakemake.yaml"
        if yaml is None or not path.exists():
            return default_snakefile, default_cores
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return default_snakefile, default_cores
        if not isinstance(data, dict):
            return default_snakefile, default_cores
        snakefile = (
            str(data.get("snakefile", default_snakefile)).strip() or default_snakefile
        )
        cores = data.get("cores", default_cores)
        if isinstance(cores, str):
            try:
                cores = int(cores.strip())
            except ValueError:
                cores = default_cores
        if not isinstance(cores, int):
            cores = default_cores
        return snakefile, max(1, cores)

    def _refresh_snakemake_settings_display(self) -> None:
        snakefile, cores = self._load_snakemake_settings()
        self.snakemake_file_var.set(snakefile)
        self.snakemake_cores_var.set(cores)

    def _build_single_command(self) -> Tuple[List[str], Path]:
        script_id = self.selected_script.get()
        script = next(
            (item for item in self.available_scripts if item["id"] == script_id), None
        )
        script_name = script["name"] if script else f"{script_id}.py"
        script_path = self._resolve_script_path(script_name)
        command = [sys.executable, str(script_path)]
        config_path = self.config_tab.get_config_path()
        if config_path and Path(config_path).exists():
            command.extend(["--config", str(config_path)])
        return command, script_path.parent

    def _build_snakemake_command(self) -> Tuple[List[str], Path, Optional[Path]]:
        snakefile_setting, cores_value = self._load_snakemake_settings()
        self.snakemake_file_var.set(snakefile_setting)
        self.snakemake_cores_var.set(cores_value)
        if not snakefile_setting:
            raise RuntimeError("Select a Snakemake file to run.")
        snakefile_path = Path(snakefile_setting)
        if not snakefile_path.is_absolute():
            snakefile_path = (PARENT_DIR / snakefile_path).resolve()
        if not snakefile_path.exists():
            raise RuntimeError(f"Snakemake file not found: {snakefile_setting}")
        snakemake_exec = shutil.which("snakemake")
        command = self._assemble_snakemake_command(
            str(snakefile_path), cores_value, snakemake_exec
        )
        return command, PARENT_DIR, None

    def _assemble_snakemake_command(
        self, snakefile_path: str, cores: int, snakemake_exec: Optional[str]
    ) -> List[str]:
        base_args = [
            "--snakefile",
            snakefile_path,
            "--cores",
            str(cores),
            "--resources",
            "openeo_req=1",
        ]
        if snakemake_exec:
            return [snakemake_exec, *base_args]
        return [sys.executable, "-m", "snakemake", *base_args]

    @staticmethod
    def _preflight_values(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value)]

    @staticmethod
    def _preflight_enabled(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _add_preflight_issue(
        self, report: Dict[str, Any], severity: str, message: str
    ) -> None:
        issue = {"severity": severity, "message": message}
        if issue not in report["issues"]:
            report["issues"].append(issue)

    def _resolve_preflight_path(self, value: Any) -> Optional[Path]:
        if value is None or not str(value).strip():
            return None
        try:
            path = Path(str(value).strip()).expanduser()
            if not path.is_absolute():
                path = PARENT_DIR / path
            return path.resolve()
        except (OSError, RuntimeError, ValueError):
            return None

    def _record_preflight_path(
        self,
        report: Dict[str, Any],
        label: str,
        value: Any,
        *,
        kind: str = "file",
        required: bool = True,
        missing_status: str = "Missing",
    ) -> Optional[Path]:
        path = self._resolve_preflight_path(value)
        display_path = str(value or "")
        if path is None:
            status = "Invalid"
            if required:
                self._add_preflight_issue(
                    report, "error", f"{label} has an invalid or empty path."
                )
        else:
            display_path = str(path)
            correct_type = path.is_dir() if kind == "directory" else path.is_file()
            if correct_type:
                status = "Ready"
            else:
                status = missing_status
                if required:
                    expected = "directory" if kind == "directory" else "file"
                    self._add_preflight_issue(
                        report, "error", f"Missing {expected} for {label}: {path}"
                    )
        record = {"label": label, "path": display_path, "status": status}
        if record not in report["files"]:
            report["files"].append(record)
        return path

    def _load_preflight_yaml(
        self,
        path: Path,
        label: str,
        report: Dict[str, Any],
        *,
        required: bool = True,
    ) -> Dict[str, Any]:
        resolved = self._record_preflight_path(report, label, path, required=required)
        if resolved is None or not resolved.is_file():
            return {}
        if yaml is None:
            self._add_preflight_issue(
                report,
                "error",
                "PyYAML is unavailable; YAML run files cannot be loaded.",
            )
            return {}
        try:
            data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            self._add_preflight_issue(
                report, "error", f"Invalid YAML in {resolved.name}: {exc}"
            )
            return {}
        if not isinstance(data, dict):
            self._add_preflight_issue(
                report,
                "error",
                f"{resolved.name} must contain a YAML mapping at its root.",
            )
            return {}
        return data

    def _check_preflight_dependencies(
        self, report: Dict[str, Any], stages: List[str], mode: str
    ) -> None:
        if not Path(sys.executable).is_file():
            self._add_preflight_issue(
                report,
                "error",
                f"The configured Python executable is unavailable: {sys.executable}",
            )
        dependencies = {
            "spatial_data_prep": (
                "geopandas",
                "yaml",
                "rasterio",
                "pygadm",
                "openeo",
                "richdem",
                "xdem",
                "numpy",
                "pyproj",
            ),
            "exclusion": (
                "atlite",
                "scipy",
                "numpy",
                "geopandas",
                "rasterio",
                "yaml",
                "rasterstats",
            ),
            "suitability": ("rasterio", "numpy", "pandas", "yaml"),
            "weather_data_prep": ("atlite", "yaml", "geopandas"),
            "weather_bias_adjust": (
                "xarray",
                "rioxarray",
                "matplotlib",
                "geopandas",
                "yaml",
            ),
            "energy_profiles": (
                "atlite",
                "numpy",
                "xarray",
                "pandas",
                "matplotlib",
                "geopandas",
                "yaml",
            ),
        }
        missing_modules: List[str] = []
        for module_name in sorted(
            {name for stage in stages for name in dependencies.get(stage, ())}
        ):
            try:
                available = importlib.util.find_spec(module_name) is not None
            except (ImportError, AttributeError, ValueError):
                available = False
            if not available:
                missing_modules.append(module_name)
        if missing_modules:
            self._add_preflight_issue(
                report,
                "error",
                "Unavailable Python dependencies for the enabled work: "
                + ", ".join(missing_modules)
                + ".",
            )
        if mode == "snakemake":
            snakemake_exec = shutil.which("snakemake")
            try:
                snakemake_module = importlib.util.find_spec("snakemake") is not None
            except (ImportError, AttributeError, ValueError):
                snakemake_module = False
            if not snakemake_exec and not snakemake_module:
                self._add_preflight_issue(
                    report,
                    "error",
                    "Snakemake is unavailable. Install it in this Python environment or add its executable to PATH.",
                )

    def _check_referenced_inputs(
        self,
        report: Dict[str, Any],
        config: Mapping[str, Any],
        regions: List[str],
        stages: List[str],
    ) -> None:
        stage_set = set(stages)
        if "spatial_data_prep" in stage_set:
            dem_name = str(config.get("DEM_filename") or "").strip()
            if dem_name:
                self._record_preflight_path(
                    report,
                    "Elevation raster",
                    PARENT_DIR / "Raw_Spatial_Data" / "DEM" / dem_name,
                )
            else:
                self._add_preflight_issue(
                    report,
                    "error",
                    "DEM_filename is required for spatial data preparation.",
                )

            custom_name = str(config.get("custom_study_area_filename") or "").strip()
            if custom_name:
                for region in regions or [str(config.get("study_region_name") or "")]:
                    try:
                        resolved_name = custom_name.format(region_name=region)
                    except (KeyError, ValueError):
                        resolved_name = custom_name
                        self._add_preflight_issue(
                            report,
                            "error",
                            f"Invalid custom study-area filename template: {custom_name}",
                        )
                    self._record_preflight_path(
                        report,
                        f"Custom study area ({region})",
                        PARENT_DIR
                        / "Raw_Spatial_Data"
                        / "custom_study_area"
                        / resolved_name,
                    )

            if str(config.get("landcover_source") or "").strip().lower() == "file":
                name = str(config.get("landcover_filename") or "").strip()
                self._record_preflight_path(
                    report,
                    "Land-cover raster",
                    PARENT_DIR / "Raw_Spatial_Data" / "landcover" / name
                    if name
                    else None,
                )

            if (
                str(config.get("protected_areas_source") or "").strip().lower()
                == "file"
            ):
                name = str(config.get("protected_areas_filename") or "").strip()
                self._record_preflight_path(
                    report,
                    "Protected-areas dataset",
                    PARENT_DIR / "Raw_Spatial_Data" / "protected_areas" / name
                    if name
                    else None,
                )

            if self._preflight_enabled(config.get("forest_density")):
                name = str(config.get("forest_density_filename") or "").strip()
                self._record_preflight_path(
                    report,
                    "Forest-density raster",
                    PARENT_DIR / "Raw_Spatial_Data" / "landcover" / name
                    if name
                    else None,
                )

            if str(config.get("OSM_source") or "").strip().lower() == "geofabrik":
                folder = str(config.get("OSM_folder_name") or "").strip()
                self._record_preflight_path(
                    report,
                    "Geofabrik OSM folder",
                    PARENT_DIR / "Raw_Spatial_Data" / "OSM" / folder
                    if folder
                    else None,
                    kind="directory",
                )

            for key, folder_name, label in (
                (
                    "additional_exclusion_polygons_folder_name",
                    "additional_exclusion_polygons",
                    "Additional exclusion polygons",
                ),
                (
                    "additional_exclusion_rasters_folder_name",
                    "additional_exclusion_rasters",
                    "Additional exclusion rasters",
                ),
            ):
                folder = str(config.get(key) or "").strip()
                if folder:
                    self._record_preflight_path(
                        report,
                        label,
                        PARENT_DIR / "Raw_Spatial_Data" / folder_name / folder,
                        kind="directory",
                    )

        if "exclusion" in stage_set:
            model_areas = str(config.get("model_areas_filename") or "").strip()
            if model_areas:
                self._record_preflight_path(
                    report,
                    "Model-areas dataset",
                    PARENT_DIR / "Raw_Spatial_Data" / "model_areas" / model_areas,
                )

        weather_consumers = {"suitability", "weather_bias_adjust", "energy_profiles"}
        weather_path_value = config.get("weather_external_data_path")
        if stage_set & weather_consumers:
            if weather_path_value is None or not str(weather_path_value).strip():
                if "suitability" in stage_set:
                    self._add_preflight_issue(
                        report,
                        "error",
                        "suitability.py requires weather_external_data_path to contain a valid directory path.",
                    )
                weather_path_value = PARENT_DIR / "Raw_Spatial_Data" / "Weather_data"
            weather_path = self._record_preflight_path(
                report,
                "Weather-data directory",
                weather_path_value,
                kind="directory",
                required="weather_data_prep" not in stage_set,
                missing_status="Will create",
            )
            if (
                weather_path
                and weather_path.is_dir()
                and {"weather_bias_adjust", "energy_profiles"} & stage_set
            ):
                metadata = weather_path / "cutout_metadata.json"
                if "weather_data_prep" not in stage_set:
                    self._record_preflight_path(
                        report, "Weather cutout metadata", metadata
                    )
        elif "weather_data_prep" in stage_set and weather_path_value:
            weather_path = self._resolve_preflight_path(weather_path_value)
            if weather_path is not None:
                status = "Ready" if weather_path.is_dir() else "Will create"
                record = {
                    "label": "Weather-data directory",
                    "path": str(weather_path),
                    "status": status,
                }
                if record not in report["files"]:
                    report["files"].append(record)

    def build_preflight_report(self) -> Dict[str, Any]:
        """Build a non-mutating report for the currently selected execution."""
        report: Dict[str, Any] = {
            "summary": {},
            "files": [],
            "issues": [],
            "command": None,
            "cwd": None,
            "temp_path": None,
            "script_id": None,
        }
        mode = self.execution_mode.get()
        config_path = self.config_tab.get_config_path() or (CONFIGS_DIR / "config.yaml")
        config = self._load_preflight_yaml(
            Path(config_path), "General configuration", report
        )
        snakemake: Dict[str, Any] = {}
        if mode == "snakemake":
            snakemake = self._load_preflight_yaml(
                CONFIGS_DIR / "config_snakemake.yaml",
                "Workflow configuration",
                report,
            )

        try:
            validation_issues = self.config_tab.validate_all(refresh_visual=False)
        except Exception as exc:
            validation_issues = []
            self._add_preflight_issue(
                report, "error", f"Configuration validation could not run: {exc}"
            )
        for issue in validation_issues:
            if (
                mode != "snakemake"
                and issue.get("file") == "config_snakemake.yaml"
            ):
                continue
            self._add_preflight_issue(
                report,
                str(issue.get("severity", "warning")),
                f"{issue.get('file', 'Configuration')} — {issue.get('key', '')}: {issue.get('message', '')}",
            )
        dirty_names = self.config_tab.dirty_document_names()
        if dirty_names:
            self._add_preflight_issue(
                report,
                "error",
                "Save unsaved changes before starting: " + ", ".join(dirty_names) + ".",
            )

        if mode == "snakemake":
            regions = self._preflight_values(snakemake.get("study_region_name"))
            technologies = self._preflight_values(snakemake.get("technologies"))
            scenario = str(snakemake.get("scenario") or "").strip()
            weather_years = self._preflight_values(snakemake.get("weather_years"))
            stages_mapping = snakemake.get("stages", {})
            stages = [
                str(name)
                for name, enabled in (
                    stages_mapping.items()
                    if isinstance(stages_mapping, Mapping)
                    else []
                )
                if self._preflight_enabled(enabled)
            ]
            _, cores = self._load_snakemake_settings()
            script_id = "snakemake"
        else:
            regions = self._preflight_values(config.get("study_region_name"))
            scenario = str(config.get("scenario") or "").strip()
            weather_years = self._preflight_values(config.get("weather_year"))
            script_id = self.selected_script.get()
            stages = [script_id]
            technologies = self._preflight_values(config.get("technology"))
            cores = 1

        suitability: Dict[str, Any] = {}
        if "suitability" in stages:
            suitability = self._load_preflight_yaml(
                CONFIGS_DIR / "suitability.yaml", "Suitability configuration", report
            )
            suitability_techs = self._preflight_values(
                suitability.get("suitability_techs")
            )
            if mode == "single":
                technologies = suitability_techs
            selected_set = set(technologies)
            suitability_set = set(suitability_techs)
            missing_from_workflow = sorted(suitability_set - selected_set)
            omitted_from_suitability = sorted(selected_set - suitability_set)
            if mode == "snakemake" and missing_from_workflow:
                self._add_preflight_issue(
                    report,
                    "error",
                    "Suitability technologies not selected in the workflow: "
                    + ", ".join(missing_from_workflow)
                    + ".",
                )
            if mode == "snakemake" and omitted_from_suitability:
                severity = "error" if "energy_profiles" in stages else "warning"
                self._add_preflight_issue(
                    report,
                    severity,
                    "Workflow technologies omitted from suitability_techs: "
                    + ", ".join(omitted_from_suitability)
                    + ".",
                )
        elif "energy_profiles" in stages:
            suitability = self._load_preflight_yaml(
                CONFIGS_DIR / "suitability.yaml", "Suitability configuration", report
            )
            suitability_techs = set(
                self._preflight_values(suitability.get("suitability_techs"))
            )
            absent = sorted(set(technologies) - suitability_techs)
            if absent:
                self._add_preflight_issue(
                    report,
                    "error",
                    "Energy-profile technologies missing from suitability_techs: "
                    + ", ".join(absent)
                    + ".",
                )

        duplicates = sorted(
            {tech for tech in technologies if technologies.count(tech) > 1}
        )
        if duplicates:
            self._add_preflight_issue(
                report,
                "warning",
                "Duplicate technology selections: " + ", ".join(duplicates) + ".",
            )
        technologies = list(dict.fromkeys(technologies))

        technology_configs_needed: List[str] = []
        if mode == "snakemake" and ({"exclusion", "energy_profiles"} & set(stages)):
            technology_configs_needed.extend(technologies)
        elif mode == "single" and script_id in {"exclusion", "energy_profiles"}:
            technology_configs_needed.extend(technologies)
        if "suitability" in stages:
            technology_configs_needed.extend(
                self._preflight_values(suitability.get("suitability_techs"))
            )
        for technology in dict.fromkeys(technology_configs_needed):
            self._load_preflight_yaml(
                CONFIGS_DIR / f"{technology}.yaml",
                f"{technology} configuration",
                report,
            )

        if "spatial_data_prep" in stages:
            advanced_path = CONFIG_ADVANCED_SETTINGS_PATH
            if not advanced_path.is_file():
                fallback = advanced_path.with_name(
                    "advanced_data_prep_settings_template.yaml"
                )
                advanced_path = fallback if fallback.is_file() else advanced_path
            self._load_preflight_yaml(
                advanced_path, "Advanced spatial settings", report
            )

        if mode == "snakemake":
            snakefile_value = snakemake.get("snakefile", "Snakefile")
            snakefile_path = self._resolve_preflight_path(snakefile_value)
            self._record_preflight_path(
                report, "Snakefile", snakefile_path or snakefile_value
            )
            rule_base = (
                snakefile_path.parent
                if snakefile_path is not None
                else PARENT_DIR / "snakemake"
            )
            for stage in stages:
                self._record_preflight_path(
                    report, f"{stage} rule", rule_base / "rules" / f"{stage}.smk"
                )
                script = next(
                    (item for item in self.available_scripts if item["id"] == stage),
                    None,
                )
                if script:
                    try:
                        stage_script_path: Any = self._resolve_script_path(
                            script["name"]
                        )
                    except FileNotFoundError:
                        stage_script_path = PARENT_DIR / script["name"]
                    self._record_preflight_path(
                        report, f"{stage} script", stage_script_path
                    )
        else:
            script = next(
                (item for item in self.available_scripts if item["id"] == script_id),
                None,
            )
            script_name = script["name"] if script else f"{script_id}.py"
            try:
                selected_script_path: Any = self._resolve_script_path(script_name)
            except FileNotFoundError:
                selected_script_path = PARENT_DIR / script_name
            self._record_preflight_path(report, "Python script", selected_script_path)

        try:
            if mode == "snakemake":
                command, cwd, temp_path = self._build_snakemake_command()
            else:
                command, cwd = self._build_single_command()
                temp_path = None
            report.update(
                {
                    "command": command,
                    "cwd": cwd,
                    "temp_path": temp_path,
                    "script_id": script_id,
                }
            )
        except (FileNotFoundError, RuntimeError) as exc:
            self._add_preflight_issue(report, "error", str(exc))

        self._check_referenced_inputs(report, config, regions, stages)
        self._check_preflight_dependencies(report, stages, mode)

        report["summary"] = {
            "Execution": "Snakemake workflow"
            if mode == "snakemake"
            else "Single script",
            "Regions": ", ".join(regions) if regions else "Not configured",
            "Technologies": ", ".join(technologies)
            if technologies
            else "Not applicable",
            "Scenario": scenario or "Not configured",
            "Weather years": ", ".join(weather_years)
            if weather_years
            else "Not applicable",
            "Enabled stages": ", ".join(stage.replace("_", " ") for stage in stages)
            if stages
            else "None",
            "Core count": str(cores),
        }
        report["run_context"] = {
            "regions": regions,
            "technologies": technologies,
            "weather_years": weather_years,
            "stages": stages,
            "scenario": scenario,
        }
        severity_order = {"error": 0, "warning": 1}
        report["issues"].sort(
            key=lambda item: (severity_order.get(item["severity"], 2), item["message"])
        )
        return report

    def _cleanup_temp_snakefile(self) -> None:
        if self.temp_snakefile_path and self.temp_snakefile_path.exists():
            try:
                self.temp_snakefile_path.unlink()
            except OSError:
                pass
        self.temp_snakefile_path = None

    def _handle_process_output(self, level: str, message: str) -> None:
        self._update_run_context_from_output(message)
        self.add_log(self._classify_process_message(level, message), message)

    def _handle_process_exit(self, return_code: int) -> None:
        self.runner.cancel()
        self._stop_spinner()
        self._cancel_duration_timer()
        self.end_time = time.time()
        self._cleanup_temp_snakefile()
        if self.reset_requested:
            self.add_log(
                "error", f"Process reset after exiting with code {return_code}."
            )
            self._finish_run_record(return_code, "Reset")
            self.current_run_log_path = None
            self._finalize_reset()
            return
        if return_code == 0 and not self.stop_requested:
            self.status = "completed"
            self.completed_jobs = self.total_jobs
            self.progress.set(100)
            self._refresh_progress_feedback()
            self.add_log("success", "Process completed successfully.")
            self._update_results_tab_with_json()
            self._update_status_labels()
            self._finish_run_record(return_code, "Completed")
            messagebox.showinfo("Execution Complete", "Process finished successfully.")
        else:
            self.status = "error"
            if self.stop_requested:
                self.add_log(
                    "error",
                    f"Process exited with code {return_code} after stop request.",
                )
                self._finish_run_record(return_code, "Stopped")
                messagebox.showerror(
                    "Execution Stopped",
                    f"Process exited with code {return_code} after stop request.",
                )
            else:
                self.add_log("error", f"Process exited with code {return_code}.")
                self._finish_run_record(return_code, "Failed")
                messagebox.showerror(
                    "Execution Failed", f"Process exited with code {return_code}."
                )
            self._update_status_labels()
        self.current_run_log_path = None
        self.stop_requested = False
        self.reset_requested = False
        self.last_run_script_id = None
        self.expected_output_dir = None

    def _finalize_reset(self) -> None:
        self.runner.cancel()
        self._stop_spinner()
        self._cancel_duration_timer()
        self._cleanup_temp_snakefile()
        self.status = "idle"
        self.progress.set(0)
        self.start_time = None
        self.end_time = None
        self._clear_logs()
        self.current_stage = ""
        self.current_region = ""
        self.current_technology = ""
        self.completed_jobs = 0
        self.total_jobs = 0
        self._refresh_progress_feedback()
        self._update_status_labels()
        self.stop_requested = False
        self.reset_requested = False

    def handle_run(self) -> None:
        if self.runner.is_running():
            return
        self.expected_output_dir = None
        self.last_run_script_id = None
        report = self.build_preflight_report()
        dialog = PreflightDialog(self, report)
        self.wait_window(dialog)
        if not dialog.confirmed:
            errors = [
                item for item in report["issues"] if item.get("severity") == "error"
            ]
            if errors:
                self.add_log(
                    "error", f"Run blocked by {len(errors)} preflight error(s)."
                )
            else:
                self.add_log("info", "Run cancelled after preflight review.")
            return
        cmd = report.get("command")
        cwd = report.get("cwd")
        temp_path = report.get("temp_path")
        script_id = report.get("script_id")
        if not cmd or not cwd:
            self.add_log(
                "error",
                "Run blocked because the preflight did not produce a valid command.",
            )
            return
        self.expected_output_dir = cwd
        self.last_run_script_id = script_id
        if script_id == "results_analysis":
            self.results_tab.clear_aggregated_results()
        self.temp_snakefile_path = temp_path
        self.stop_requested = False
        self.reset_requested = False
        self.status = "running"
        self.progress.set(0)
        self._clear_logs()
        self._initialize_run_feedback(report)
        self.start_time = time.time()
        self.end_time = None
        self.last_command_text = self._format_command([str(part) for part in cmd])
        self.copy_command_button.configure(state="normal")
        self._begin_run_record(report, [str(part) for part in cmd], Path(cwd))
        self._start_spinner()
        self._start_duration_timer()
        self.add_log("info", f"Starting process: {self.last_command_text}")
        self._update_status_labels()
        try:
            self.runner.run(
                self,
                [str(part) for part in cmd],
                cwd=cwd,
                on_line=self._handle_process_output,
                on_exit=self._handle_process_exit,
            )
        except Exception as exc:
            self.runner.cancel()
            self._stop_spinner()
            self._cancel_duration_timer()
            self.status = "error"
            self.add_log("error", f"Failed to start process: {exc}")
            self._finish_run_record(None, "Start failed")
            self.current_run_log_path = None
            self.start_time = None
            self.end_time = None
            self._update_status_labels()
            messagebox.showerror("Execution Error", f"Failed to start process:\n{exc}")
            self._cleanup_temp_snakefile()
            self.stop_requested = False
            self.reset_requested = False
            self.last_run_script_id = None
            self.expected_output_dir = None

    def handle_stop(self) -> None:
        if not self.runner.is_running():
            return
        self.stop_requested = True
        self.runner.stop()
        self._stop_spinner()
        self._cancel_duration_timer()
        self.status = "error"
        self.end_time = time.time()
        self.add_log("error", "Execution stopped by user.")
        self._update_status_labels()

    def handle_reset(self) -> None:
        if self.runner.is_running():
            self.reset_requested = True
            self.stop_requested = True
            self.runner.stop()
            return
        self._finalize_reset()


class MapTab(ttk.Frame):
    MAX_LAYERS = 3
    FILETYPES = [
        ("Supported files", "*.tif *.tiff *.geojson"),
        ("GeoTIFF", "*.tif *.tiff"),
        ("GeoJSON", "*.geojson"),
    ]

    def __init__(self, master: tk.Widget):
        super().__init__(master)
        self.file_vars = [tk.StringVar() for _ in range(self.MAX_LAYERS)]
        self.layer_order = [
            tk.StringVar(value=str(i + 1)) for i in range(self.MAX_LAYERS)
        ]
        self.layer_opacity = [tk.DoubleVar(value=0.7) for _ in range(self.MAX_LAYERS)]
        self.layer_names = [tk.StringVar(value="") for _ in range(self.MAX_LAYERS)]
        self._map_dir: Optional[Path] = None
        self._map_view: Optional[Dict[str, Any]] = None
        self.status_var = tk.StringVar(value="")
        self._status_palette = {
            "info": "#0d5d9b",
            "warning": "#a66b00",
            "error": "#b42318",
            "success": "#1a7f37",
        }
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self._build_ui()
        self.bind("<Destroy>", self._on_destroy)

    def _build_ui(self) -> None:
        selection = ttk.LabelFrame(self, text="Layer Selection")
        selection.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        for col in (1, 5, 7):
            selection.columnconfigure(col, weight=1)
        for idx in range(self.MAX_LAYERS):
            ttk.Label(selection, text=f"Layer {idx + 1}:").grid(
                row=idx, column=0, sticky="w", pady=2, padx=(0, 6)
            )
            entry = ttk.Entry(selection, textvariable=self.file_vars[idx])
            entry.grid(row=idx, column=1, sticky="ew", pady=2)
            ttk.Button(
                selection, text="Browse", command=lambda i=idx: self._browse(i)
            ).grid(row=idx, column=2, padx=(6, 0), pady=2)
            ttk.Button(
                selection, text="Clear", command=lambda i=idx: self._clear(i)
            ).grid(row=idx, column=3, padx=(6, 0), pady=2)
            ttk.Label(selection, text="Display Name:").grid(
                row=idx, column=4, sticky="e", padx=(12, 4)
            )
            ttk.Entry(selection, textvariable=self.layer_names[idx], width=18).grid(
                row=idx, column=5, sticky="ew", pady=2
            )
            ttk.Label(selection, text="Opacity:").grid(
                row=idx, column=6, sticky="e", padx=(12, 4)
            )
            ttk.Scale(
                selection,
                variable=self.layer_opacity[idx],
                from_=0.1,
                to=1.0,
                orient="horizontal",
            ).grid(row=idx, column=7, sticky="ew", pady=2)
            ttk.Label(selection, text="Order:").grid(
                row=idx, column=8, sticky="e", padx=(12, 4)
            )
            order_combo = ttk.Combobox(
                selection,
                textvariable=self.layer_order[idx],
                values=[str(i) for i in range(1, self.MAX_LAYERS + 1)],
                state="readonly",
                width=5,
            )
            order_combo.grid(row=idx, column=9, sticky="w")
            order_combo.current(idx)

        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        ttk.Button(buttons, text="Load Map", command=self._load).pack(side="left")
        ttk.Button(buttons, text="Clear All", command=self._clear_all).pack(
            side="left", padx=(6, 0)
        )

        self.status_label = ttk.Label(
            self,
            textvariable=self.status_var,
            wraplength=540,
            justify="left",
            foreground="#0d5d9b",
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))

        map_and_legend = ttk.Frame(self)
        map_and_legend.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        map_and_legend.columnconfigure(0, weight=3)
        map_and_legend.columnconfigure(1, weight=1)
        map_and_legend.rowconfigure(0, weight=1)

        self.map_container = ttk.Frame(map_and_legend)
        self.map_container.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.map_container.columnconfigure(0, weight=1)
        self.map_container.rowconfigure(0, weight=1)

        legend_frame = ttk.LabelFrame(map_and_legend, text="Legend")
        legend_frame.grid(row=0, column=1, sticky="nsew")
        legend_frame.columnconfigure(0, weight=1)
        legend_frame.rowconfigure(0, weight=1)
        self.legend_text = tk.Text(legend_frame, height=10, wrap="word")
        self.legend_text.grid(row=0, column=0, sticky="nsew")
        legend_scroll = ttk.Scrollbar(
            legend_frame, orient="vertical", command=self.legend_text.yview
        )
        legend_scroll.grid(row=0, column=1, sticky="ns")
        self.legend_text.configure(yscrollcommand=legend_scroll.set)
        ttk.Label(
            legend_frame,
            text="Enter HTML or plain text for legend (optional).",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._set_status("Select up to three layers to display on the map.", "info")

    def _browse(self, idx: int) -> None:
        current_value = self.file_vars[idx].get().strip()
        initial_dir = None
        if current_value:
            current_path = Path(current_value)
            if current_path.exists():
                initial_dir = str(current_path.parent)
        path = filedialog.askopenfilename(
            title="Select Layer",
            filetypes=self.FILETYPES,
            initialdir=initial_dir or os.getcwd(),
        )
        if path:
            self.file_vars[idx].set(path)
            if not self.layer_names[idx].get().strip():
                self.layer_names[idx].set(Path(path).stem)
            self._set_status(f"Selected {Path(path).name}.", "info")

    def _clear(self, idx: int) -> None:
        if self.file_vars[idx].get():
            self.file_vars[idx].set("")
            self.layer_names[idx].set("")
            self._set_status(f"Cleared layer {idx + 1}.", "info")

    def _clear_all(self) -> None:
        any_cleared = False
        legend_present = bool(self.legend_text.get("1.0", "end").strip())
        for idx, var in enumerate(self.file_vars):
            if var.get():
                any_cleared = True
            var.set("")
            self.layer_names[idx].set("")
            self.layer_order[idx].set(str(idx + 1))
            self.layer_opacity[idx].set(0.7)
        if legend_present:
            any_cleared = True
        self.legend_text.delete("1.0", "end")
        self._clear_map_display()
        self._cleanup_temp_dir()
        if any_cleared:
            self._set_status("Cleared all layer selections.", "info")
        else:
            self._set_status("No layers to clear.", "info")

    def _load(self) -> None:
        self._set_status("Preparing map...", "info")
        self._clear_map_display()
        self._cleanup_temp_dir()
        entries: List[Tuple[int, Path]] = []
        for idx, var in enumerate(self.file_vars):
            raw = var.get().strip()
            if not raw:
                continue
            entries.append((idx, Path(raw)))
        if not entries:
            self._set_status(
                "Select at least one layer before loading the map.", "warning"
            )
            messagebox.showwarning(
                "Load Map", "Select at least one layer before loading the map."
            )
            return
        temp_dir = Path(tempfile.mkdtemp(prefix="map_tab_"))
        layers: List[Dict[str, Any]] = []
        for idx, path in entries:
            if not path.exists():
                self._set_status(f"File not found: {path}", "error")
                messagebox.showerror("Load Map", f"File not found:\n{path}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return
            display_name = self.layer_names[idx].get().strip() or path.stem
            try:
                order_value = int(self.layer_order[idx].get())
            except Exception:
                order_value = idx + 1
            order_value = max(1, min(self.MAX_LAYERS, order_value))
            try:
                opacity_value = float(self.layer_opacity[idx].get())
            except Exception:
                opacity_value = 0.7
            opacity_value = max(0.0, min(1.0, opacity_value))
            suffix = path.suffix.lower()
            try:
                if suffix in {".tif", ".tiff"}:
                    png_path, bounds = geotiff_to_png_with_bounds(
                        str(path), str(temp_dir)
                    )
                    layers.append(
                        {
                            "type": "raster",
                            "name": path.name,
                            "display_name": display_name,
                            "image_path": png_path,
                            "bounds": bounds,
                            "opacity": opacity_value,
                            "order": order_value,
                            "index": idx,
                        }
                    )
                elif suffix == ".geojson":
                    with path.open("r", encoding="utf-8") as handle:
                        geojson_data = json.load(handle)
                    layers.append(
                        {
                            "type": "geojson",
                            "name": path.name,
                            "display_name": display_name,
                            "data": geojson_data,
                            "bounds": _extract_geojson_bounds(geojson_data),
                            "opacity": opacity_value,
                            "order": order_value,
                            "index": idx,
                        }
                    )
                else:
                    raise ValueError(
                        "Unsupported file type. Choose .tif, .tiff, or .geojson."
                    )
            except Exception as exc:
                shutil.rmtree(temp_dir, ignore_errors=True)
                self._set_status(f"Failed to load {path.name}: {exc}", "error")
                messagebox.showerror("Load Map", f"Failed to load {path.name}:\n{exc}")
                return
        map_html = temp_dir / "map.html"
        legend_html = self.legend_text.get("1.0", "end").strip()
        try:
            build_map_html(layers, str(map_html), legend_html=legend_html)
        except Exception as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self._set_status(f"Could not build the map: {exc}", "error")
            messagebox.showerror("Load Map", f"Could not build the map:\n{exc}")
            return
        self._map_dir = temp_dir
        self._map_view = show_map_in_tk(str(map_html), self.map_container)
        embedded = bool(self._map_view.get("embedded")) if self._map_view else False
        if embedded:
            self._set_status(
                f"Loaded {len(layers)} layer(s) in the embedded map.", "success"
            )
        else:
            self._set_status(
                f"Loaded {len(layers)} layer(s). The map opened in your browser.",
                "warning",
            )

    def _clear_map_display(self) -> None:
        if self._map_view:
            cleanup = self._map_view.get("cleanup")
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    pass
            widget = self._map_view.get("widget")
            if widget and hasattr(widget, "winfo_exists") and widget.winfo_exists():
                try:
                    widget.destroy()
                except Exception:
                    pass
        for child in list(self.map_container.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self._map_view = None

    def _cleanup_temp_dir(self) -> None:
        if self._map_dir and self._map_dir.exists():
            shutil.rmtree(self._map_dir, ignore_errors=True)
        self._map_dir = None

    def _set_status(self, message: str, level: str = "info") -> None:
        color = self._status_palette.get(level, self._status_palette["info"])
        self.status_var.set(message)
        self.status_label.configure(foreground=color)

    def _on_destroy(self, _event: tk.Event) -> None:
        self._clear_map_display()
        self._cleanup_temp_dir()


class ResultsTab(ttk.Frame):
    """Run results_analysis and display the aggregated JSON output."""

    def __init__(self, master: tk.Widget, _initial_data: Dict[str, Any]):
        super().__init__(master)
        self.runner = ProcessRunner()
        self.delete_runner = ProcessRunner()
        self.status = "idle"
        self.stop_requested = False
        self.progress = tk.DoubleVar(value=0)
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.after_id: Optional[str] = None
        self.expected_output_dir: Optional[Path] = None
        self.delete_status = "idle"
        self.delete_expected_dir: Optional[Path] = None
        self.aggregated_columns = (
            "Scenario",
            "Technology",
            "Region",
            "eligibility_share_%",
            "available_area_km2",
            "power_potential_TW",
        )
        self.aggregated_tree: Optional[ttk.Treeview] = None
        self.aggregated_filters: Dict[str, tk.StringVar] = {}
        self.current_aggregated_rows: List[Dict[str, Any]] = []
        self.latest_aggregated_path: Optional[Path] = None
        self.delete_log_text: Optional[tk.Text] = None
        self.delete_input_var = tk.StringVar()
        self.delete_run_button: Optional[ttk.Button] = None
        self.delete_stop_button: Optional[ttk.Button] = None
        self.delete_status_label: Optional[ttk.Label] = None
        self.delete_input_entry: Optional[ttk.Entry] = None
        self.delete_send_button: Optional[ttk.Button] = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.analysis_tab = ttk.Frame(self.notebook)
        self.analysis_tab.columnconfigure(0, weight=1)
        self.analysis_tab.rowconfigure(0, weight=1)
        self.delete_tab = ttk.Frame(self.notebook)
        self.delete_tab.columnconfigure(0, weight=1)
        self.delete_tab.rowconfigure(0, weight=1)
        self.notebook.add(self.analysis_tab, text="Aggregated Results")
        self.notebook.add(self.delete_tab, text="Delete Scenario Results")
        self.map_tab = MapTab(self.notebook)
        self.notebook.add(self.map_tab, text="Map")
        self._build_analysis_tab()
        self._build_delete_tab()

    def _build_analysis_tab(self) -> None:
        frame = ttk.LabelFrame(self.analysis_tab, text="Results Analysis")
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(4, weight=2)

        ttk.Label(
            frame,
            text="Run results_analysis.py and review aggregated_available_land.json",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")

        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        controls.columnconfigure(3, weight=1)
        self.run_button = ttk.Button(
            controls, text="Run results_analysis.py", command=self.handle_run
        )
        self.run_button.grid(row=0, column=0, padx=(0, 6))
        self.stop_button = ttk.Button(
            controls, text="Stop", command=self.handle_stop, state="disabled"
        )
        self.stop_button.grid(row=0, column=1, padx=(0, 6))
        self.status_label = ttk.Label(controls, text="Status: Idle")
        self.status_label.grid(row=0, column=2, sticky="w")
        self.duration_label = ttk.Label(controls, text="Duration: --")
        self.duration_label.grid(row=0, column=3, sticky="e")

        progress_frame = ttk.Frame(frame)
        progress_frame.grid(row=2, column=0, sticky="ew", pady=(10, 10))
        ttk.Label(progress_frame, text="Progress").grid(row=0, column=0, sticky="w")
        self.progress_bar = ttk.Progressbar(
            progress_frame, maximum=100, variable=self.progress, mode="determinate"
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew")

        log_frame = ttk.LabelFrame(frame, text="Execution Log")
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame, height=8, wrap="none", state="disabled", font=("Consolas", 10)
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        for tag, color in {
            "info": "#333333",
            "success": "#1a7f37",
            "warning": "#a66b00",
            "error": "#b42318",
        }.items():
            self.log_text.tag_configure(tag, foreground=color)

        results_frame = ttk.LabelFrame(
            frame, text="Aggregated Results (aggregated_available_land.json)"
        )
        results_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(1, weight=1)
        headings = {
            "Scenario": "Scenario",
            "Technology": "Technology",
            "Region": "Region",
            "eligibility_share_%": "Eligibility Share (%)",
            "available_area_km2": "Available Area (km^2)",
            "power_potential_TW": "Power Potential (TW)",
        }
        filters_frame = ttk.Frame(results_frame)
        filters_frame.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(6, 4))
        for idx in range(len(self.aggregated_columns)):
            filters_frame.columnconfigure(idx, weight=1)
        for idx, col in enumerate(self.aggregated_columns):
            var = tk.StringVar()
            self.aggregated_filters[col] = var
            entry = ttk.Entry(filters_frame, textvariable=var)
            entry.grid(row=0, column=idx, sticky="ew", padx=2)
            entry.bind("<KeyRelease>", self._handle_filter_change)
            entry.configure(width=18)
        self.filter_notice = ttk.Label(
            results_frame,
            text="Type to filter (substring match, case-insensitive). Leave blank to clear.",
            foreground="#555555",
        )
        self.filter_notice.grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(4, 6))
        self.aggregated_tree = ttk.Treeview(
            results_frame, columns=self.aggregated_columns, show="headings", height=14
        )
        for col in self.aggregated_columns:
            header = headings.get(col, col.replace("_", " ").title())
            self.aggregated_tree.heading(col, text=header)
            self.aggregated_tree.column(col, anchor="w", width=160)
        self.aggregated_tree.grid(row=1, column=0, sticky="nsew")
        aggregated_scroll = ttk.Scrollbar(
            results_frame, orient="vertical", command=self.aggregated_tree.yview
        )
        aggregated_scroll.grid(row=1, column=1, sticky="ns")
        self.aggregated_tree.configure(yscrollcommand=aggregated_scroll.set)

    def _build_delete_tab(self) -> None:
        frame = ttk.LabelFrame(self.delete_tab, text="Delete Scenario Results")
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(
            frame,
            text="Run delete_scenario_results.py to remove generated files for a scenario.",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="Respond to prompts below when the script asks for scenario selection or confirmation.",
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(2, weight=1)
        self.delete_run_button = ttk.Button(
            controls,
            text="Run delete_scenario_results.py",
            command=self.handle_delete_run,
        )
        self.delete_run_button.grid(row=0, column=0, padx=(0, 6))
        self.delete_stop_button = ttk.Button(
            controls, text="Stop", command=self.handle_delete_stop, state="disabled"
        )
        self.delete_stop_button.grid(row=0, column=1, padx=(0, 6))
        self.delete_status_label = ttk.Label(controls, text="Status: Idle")
        self.delete_status_label.grid(row=0, column=2, sticky="w")

        log_frame = ttk.LabelFrame(frame, text="Script Output")
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.delete_log_text = tk.Text(
            log_frame, height=14, wrap="none", state="disabled", font=("Consolas", 10)
        )
        self.delete_log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.delete_log_text.yview
        )
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.delete_log_text.configure(yscrollcommand=log_scroll.set)
        for tag, color in {
            "info": "#333333",
            "success": "#1a7f37",
            "warning": "#a66b00",
            "error": "#b42318",
            "input": "#0d5d9b",
        }.items():
            self.delete_log_text.tag_configure(tag, foreground=color)

        input_row = ttk.Frame(frame)
        input_row.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        input_row.columnconfigure(1, weight=1)
        ttk.Label(input_row, text="Send Input:").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self.delete_input_entry = ttk.Entry(
            input_row, textvariable=self.delete_input_var, state="disabled"
        )
        self.delete_input_entry.grid(row=0, column=1, sticky="ew")
        self.delete_input_entry.bind("<Return>", self._handle_delete_send_event)
        self.delete_send_button = ttk.Button(
            input_row, text="Send", command=self.handle_delete_send, state="disabled"
        )
        self.delete_send_button.grid(row=0, column=2, padx=(6, 0))
        self._set_delete_running_state(False)

    def _format_command(self, cmd: List[str]) -> str:
        if hasattr(shlex, "join"):
            return shlex.join(cmd)
        return " ".join(cmd)

    def _set_running_state(self, running: bool) -> None:
        self.run_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def _update_status_labels(self) -> None:
        self.status_label.configure(text=f"Status: {self.status.capitalize()}")
        duration_text = "--"
        if self.start_time:
            end = self.end_time or time.time()
            duration_text = f"{int(end - self.start_time)}s"
        self.duration_label.configure(text=f"Duration: {duration_text}")

    def _append_log(self, level: str, message: str) -> None:
        tag = level if level in {"info", "success", "warning", "error"} else "info"
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n", tag)
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _start_spinner(self) -> None:
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(10)

    def _stop_spinner(self) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")

    def _start_duration_timer(self) -> None:
        self._cancel_duration_timer()
        if self.status == "running":
            self.after_id = self.after(1000, self._tick_duration)

    def _cancel_duration_timer(self) -> None:
        if self.after_id:
            try:
                self.after_cancel(self.after_id)
            except tk.TclError:
                pass
        self.after_id = None

    def _tick_duration(self) -> None:
        self.after_id = None
        if self.status == "running":
            self._update_status_labels()
            self.after_id = self.after(1000, self._tick_duration)

    def _resolve_script_path(self, script_name: str) -> Path:
        candidates = [
            PARENT_DIR / script_name,
            CURRENT_DIR / script_name,
            PARENT_DIR / "scripts" / script_name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError(
            f"Could not find {script_name} in the expected locations."
        )

    def _resolve_results_json_path(self) -> Path:
        base_dir = self.expected_output_dir or PARENT_DIR
        json_path = base_dir / "aggregated_available_land.json"
        try:
            return json_path.resolve()
        except Exception:
            return json_path

    def handle_run(self) -> None:
        if self.runner.is_running():
            return
        try:
            script_path = self._resolve_script_path("results_analysis.py")
        except FileNotFoundError as exc:
            message = str(exc)
            self._append_log("error", message)
            messagebox.showerror("Execution Error", message)
            return
        self.expected_output_dir = script_path.parent
        self.status = "running"
        self.stop_requested = False
        self.progress.set(0)
        self._clear_log()
        self.clear_aggregated_results()
        self.start_time = time.time()
        self.end_time = None
        self._set_running_state(True)
        self._update_status_labels()
        self._start_spinner()
        self._start_duration_timer()
        command = [sys.executable, "-u", str(script_path)]
        self._append_log("info", f"Starting process: {self._format_command(command)}")
        try:
            self.runner.run(
                self,
                [str(part) for part in command],
                cwd=self.expected_output_dir,
                on_line=self._handle_process_output,
                on_exit=self._handle_process_exit,
            )
        except Exception as exc:
            self.runner.cancel()
            self._stop_spinner()
            self._cancel_duration_timer()
            self.status = "error"
            self.start_time = None
            self.end_time = None
            self._append_log("error", f"Failed to start process: {exc}")
            self._set_running_state(False)
            self._update_status_labels()
            self.expected_output_dir = None
            messagebox.showerror("Execution Error", f"Failed to start process:\n{exc}")

    def handle_stop(self) -> None:
        if not self.runner.is_running():
            return
        self.stop_requested = True
        self.status = "stopping"
        self._append_log("warning", "Stop requested. Waiting for process to exit...")
        self._update_status_labels()
        self.runner.stop()

    def _handle_process_output(self, level: str, message: str) -> None:
        tag = level if level in {"info", "success", "warning", "error"} else "info"
        self._append_log(tag, message)

    def _handle_process_exit(self, return_code: int) -> None:
        self.runner.cancel()
        self._stop_spinner()
        self._cancel_duration_timer()
        self.end_time = time.time()
        if return_code == 0 and not self.stop_requested:
            self.status = "completed"
            self.progress.set(100)
            self._append_log("success", "Process completed successfully.")
            status, message, _ = self.display_aggregated_json(
                self._resolve_results_json_path()
            )
            if status == "success":
                self._append_log("success", message)
            elif status in {"missing", "empty"}:
                self._append_log("warning", message)
            else:
                self._append_log("error", message)
        else:
            self.status = "stopped" if self.stop_requested else "error"
            self.progress.set(0)
            if self.stop_requested:
                self._append_log(
                    "warning",
                    f"Process exited with code {return_code} after stop request.",
                )
            else:
                self._append_log("error", f"Process exited with code {return_code}.")
        self._set_running_state(False)
        self._update_status_labels()
        self.stop_requested = False
        self.expected_output_dir = None

    def clear_aggregated_results(self) -> None:
        self.current_aggregated_rows = []
        if self.aggregated_tree:
            for item in self.aggregated_tree.get_children():
                self.aggregated_tree.delete(item)
        self.latest_aggregated_path = None
        self._apply_aggregated_filters()

    def _populate_aggregated_tree(self, rows: List[Dict[str, Any]]) -> None:
        if not self.aggregated_tree:
            return
        self.aggregated_tree.delete(*self.aggregated_tree.get_children())
        for row in rows:
            values = [
                self._format_aggregated_value(row.get(col))
                for col in self.aggregated_columns
            ]
            self.aggregated_tree.insert("", "end", values=values)

    def _update_delete_status(self) -> None:
        if self.delete_status_label:
            self.delete_status_label.configure(
                text=f"Status: {self.delete_status.capitalize()}"
            )

    def _set_delete_running_state(self, running: bool) -> None:
        if self.delete_run_button:
            self.delete_run_button.configure(state="disabled" if running else "normal")
        if self.delete_stop_button:
            self.delete_stop_button.configure(state="normal" if running else "disabled")
        entry_state = "normal" if running else "disabled"
        if self.delete_input_entry:
            self.delete_input_entry.configure(state=entry_state)
            if running:
                self.delete_input_entry.focus_set()
            else:
                self.delete_input_var.set("")
        if self.delete_send_button:
            self.delete_send_button.configure(state=entry_state)

    def _delete_clear_log(self) -> None:
        if not self.delete_log_text:
            return
        self.delete_log_text.configure(state="normal")
        self.delete_log_text.delete("1.0", "end")
        self.delete_log_text.configure(state="disabled")

    def _delete_append_log(self, level: str, message: str) -> None:
        if not self.delete_log_text:
            return
        tag = level if level in {"info", "error", "warning", "input"} else "info"
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.delete_log_text.configure(state="normal")
        self.delete_log_text.insert("end", f"[{timestamp}] {message}\n", tag)
        self.delete_log_text.configure(state="disabled")
        self.delete_log_text.see("end")

    def handle_delete_run(self) -> None:
        if self.delete_runner.is_running():
            return
        try:
            script_path = self._resolve_script_path("delete_scenario_results.py")
        except FileNotFoundError as exc:
            message = str(exc)
            self._delete_append_log("error", message)
            messagebox.showerror("Execution Error", message)
            return
        self.delete_expected_dir = script_path.parent
        self.delete_status = "running"
        self._set_delete_running_state(True)
        self._update_delete_status()
        self._delete_clear_log()
        command = [sys.executable, "-u", str(script_path)]
        self._delete_append_log(
            "info", f"Starting process: {self._format_command(command)}"
        )
        try:
            self.delete_runner.run(
                self,
                [str(part) for part in command],
                cwd=self.delete_expected_dir,
                on_line=self._handle_delete_output,
                on_exit=self._handle_delete_exit,
            )
        except Exception as exc:
            self.delete_runner.cancel()
            self.delete_status = "error"
            self._update_delete_status()
            self._set_delete_running_state(False)
            self._delete_append_log("error", f"Failed to start process: {exc}")
            self.delete_expected_dir = None
            messagebox.showerror("Execution Error", f"Failed to start process:\n{exc}")

    def handle_delete_stop(self) -> None:
        if not self.delete_runner.is_running():
            return
        self.delete_status = "stopping"
        self._update_delete_status()
        self._delete_append_log(
            "warning", "Stop requested. Waiting for process to exit..."
        )
        self.delete_runner.stop()

    def handle_delete_send(self) -> None:
        if not self.delete_runner.is_running():
            return
        text = self.delete_input_var.get()
        if not text.strip():
            return
        try:
            self.delete_runner.send_input(text)
            self._delete_append_log("input", f">>> {text}")
        except RuntimeError as exc:
            self._delete_append_log("error", str(exc))
            messagebox.showerror("Send Input Failed", str(exc))
        finally:
            self.delete_input_var.set("")

    def _handle_delete_send_event(self, _event: tk.Event) -> str:
        self.handle_delete_send()
        return "break"

    def _handle_delete_output(self, level: str, message: str) -> None:
        self._delete_append_log(level, message)

    def _handle_delete_exit(self, return_code: int) -> None:
        self.delete_runner.cancel()
        if return_code == 0 and self.delete_status != "stopping":
            self.delete_status = "completed"
            self._delete_append_log("success", "Process completed successfully.")
        else:
            if self.delete_status == "stopping":
                self._delete_append_log(
                    "warning",
                    f"Process exited with code {return_code} after stop request.",
                )
                self.delete_status = "stopped"
            else:
                self._delete_append_log(
                    "error", f"Process exited with code {return_code}."
                )
                self.delete_status = "error"
        self._set_delete_running_state(False)
        self._update_delete_status()
        self.delete_expected_dir = None

    def _handle_filter_change(self, _event: tk.Event) -> None:
        self._apply_aggregated_filters()

    def _apply_aggregated_filters(self) -> None:
        filters = {
            col: var.get().strip().lower()
            for col, var in self.aggregated_filters.items()
            if var.get().strip()
        }
        if not filters:
            self._populate_aggregated_tree(self.current_aggregated_rows)
            return
        filtered_rows: List[Dict[str, Any]] = []
        for row in self.current_aggregated_rows:
            matches_all = True
            for col, term in filters.items():
                value = row.get(col)
                compare = "" if value is None else str(value)
                if term not in compare.lower():
                    matches_all = False
                    break
            if matches_all:
                filtered_rows.append(row)
        self._populate_aggregated_tree(filtered_rows)

    def _format_aggregated_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            formatted = f"{value:.4f}".rstrip("0").rstrip(".")
            return formatted if formatted else "0"
        return str(value)

    def _normalise_aggregated_rows(self, data: Any) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not isinstance(data, list):
            return rows
        for entry in data:
            if not isinstance(entry, dict):
                continue
            scenario_val = entry.get("scenario")
            tech_val = entry.get("technology")
            scenario = "" if scenario_val is None else str(scenario_val)
            technology = "" if tech_val is None else str(tech_val)
            aggregated = entry.get("aggregated")
            if isinstance(aggregated, dict):
                rows.append(
                    {
                        "Scenario": scenario,
                        "Technology": technology,
                        "Region": "ALL",
                        "eligibility_share_%": aggregated.get("eligibility_share_%"),
                        "available_area_km2": aggregated.get("available_area_km2"),
                        "power_potential_TW": aggregated.get("power_potential_TW"),
                    }
                )
            regions = entry.get("regions")
            if isinstance(regions, dict):
                for region_name, metrics in regions.items():
                    if not isinstance(metrics, dict):
                        continue
                    region = "" if region_name is None else str(region_name)
                    rows.append(
                        {
                            "Scenario": scenario,
                            "Technology": technology,
                            "Region": region,
                            "eligibility_share_%": metrics.get("eligibility_share_%"),
                            "available_area_km2": metrics.get("available_area_km2"),
                            "power_potential_TW": metrics.get("power_potential_TW"),
                        }
                    )
        return rows

    def _set_aggregated_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.current_aggregated_rows = rows
        self._apply_aggregated_filters()

    def display_aggregated_json(
        self, json_path: Optional[Path] = None
    ) -> Tuple[str, str, int]:
        if not self.aggregated_tree:
            return ("error", "Aggregated results view unavailable.", 0)
        target = json_path or (PARENT_DIR / "aggregated_available_land.json")
        try:
            resolved = target.resolve()
        except Exception:
            resolved = target
        self.clear_aggregated_results()
        self.latest_aggregated_path = resolved
        if not resolved.exists():
            return ("missing", f"Aggregated results JSON not found: {resolved}", 0)
        try:
            raw_data = resolved.read_text(encoding="utf-8")
            payload = json.loads(raw_data) if raw_data.strip() else []
        except (OSError, json.JSONDecodeError) as exc:
            self.clear_aggregated_results()
            return (
                "error",
                f"Failed to load aggregated results from {resolved}: {exc}",
                0,
            )
        rows = self._normalise_aggregated_rows(payload)
        if not rows:
            self.clear_aggregated_results()
            return ("empty", f"No aggregated entries found in {resolved}", 0)
        self._set_aggregated_rows(rows)
        return ("success", f"Loaded {len(rows)} rows from {resolved}", len(rows))


class ConfigurationSetupDialog(tk.Toplevel):
    """Initialize active configuration files before opening their editors."""

    def __init__(self, master: tk.Widget, on_complete: Callable[[], None]) -> None:
        super().__init__(master)
        self.title("Configuration Setup")
        self.geometry("760x540")
        self.minsize(680, 460)
        self.transient(master)
        self.on_complete = on_complete
        self.source_var = tk.StringVar(value="default")
        self.country_var = tk.StringVar()
        self.overwrite_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar()
        self.countries = available_example_countries(CONFIGS_DIR)
        if self.countries:
            self.country_var.set(self.countries[0])
        self._build_ui()
        self._refresh_preview()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _build_ui(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        ttk.Label(
            body, text="Initialize Configuration Files", font=("Segoe UI", 15, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "Choose the template set used to create active YAML files in configs/. "
                "You can edit those files after setup completes."
            ),
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        choices = ttk.LabelFrame(body, text="Template source", padding=10)
        choices.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        choices.columnconfigure(3, weight=1)
        ttk.Radiobutton(
            choices,
            text="Default (Odense, DK)",
            value="default",
            variable=self.source_var,
            command=self._on_source_changed,
        ).grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Radiobutton(
            choices,
            text="Country example",
            value="example",
            variable=self.source_var,
            command=self._on_source_changed,
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(choices, text="Country:").grid(
            row=0, column=2, sticky="e", padx=(20, 6)
        )
        self.country_combo = ttk.Combobox(
            choices,
            textvariable=self.country_var,
            values=self.countries,
            state="readonly",
            width=22,
        )
        self.country_combo.grid(row=0, column=3, sticky="w")
        self.country_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._refresh_preview()
        )

        preview_frame = ttk.LabelFrame(body, text="Files", padding=8)
        preview_frame.grid(row=3, column=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.preview_tree = ttk.Treeview(
            preview_frame,
            columns=("source", "target", "action"),
            show="headings",
            height=10,
        )
        self.preview_tree.heading("source", text="Template")
        self.preview_tree.heading("target", text="Active file")
        self.preview_tree.heading("action", text="Action")
        self.preview_tree.column("source", width=290, anchor="w")
        self.preview_tree.column("target", width=210, anchor="w")
        self.preview_tree.column("action", width=100, anchor="center")
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(
            preview_frame, orient="vertical", command=self.preview_tree.yview
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.preview_tree.configure(yscrollcommand=scroll.set)

        options = ttk.Frame(body)
        options.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            options,
            text="Replace existing active files",
            variable=self.overwrite_var,
            command=self._refresh_preview,
        ).pack(side="left")
        ttk.Label(
            options, textvariable=self.status_var, foreground="#8A5A00", wraplength=440
        ).pack(side="left", padx=(14, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(
            buttons, text="Initialize and Continue", command=self._initialize
        ).pack(side="right")
        self._on_source_changed()

    def _selected_country(self) -> Optional[str]:
        if self.source_var.get() != "example":
            return None
        return self.country_var.get().strip() or None

    def _on_source_changed(self) -> None:
        is_example = self.source_var.get() == "example"
        self.country_combo.configure(
            state="readonly" if is_example and self.countries else "disabled"
        )
        self._refresh_preview()

    def _template_pairs(self) -> List[Tuple[Path, Path]]:
        country = self._selected_country()
        if self.source_var.get() == "example" and not country:
            return []
        return preview_config_templates(CONFIGS_DIR, country=country)

    def _refresh_preview(self) -> None:
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        try:
            pairs = self._template_pairs()
        except OSError as exc:
            self.status_var.set(str(exc))
            return
        existing = 0
        for source, target in pairs:
            if target.exists():
                existing += 1
                action = "Replace" if self.overwrite_var.get() else "Skip"
            else:
                action = "Create"
            try:
                source_label = str(source.relative_to(CONFIGS_DIR))
                target_label = str(target.relative_to(CONFIGS_DIR))
            except ValueError:
                source_label, target_label = source.name, target.name
            self.preview_tree.insert(
                "", "end", values=(source_label, target_label, action)
            )
        if existing and not self.overwrite_var.get():
            self.status_var.set(
                f"{existing} existing file(s) will be kept; they may come from another template set."
            )
        elif existing:
            self.status_var.set(f"{existing} existing file(s) will be replaced.")
        else:
            self.status_var.set("")

    def _initialize(self) -> None:
        country = self._selected_country()
        if self.source_var.get() == "example" and not country:
            messagebox.showerror(
                "Configuration Setup", "Select a country example.", parent=self
            )
            return
        try:
            pairs = self._template_pairs()
        except OSError as exc:
            messagebox.showerror("Configuration Setup", str(exc), parent=self)
            return
        if not pairs:
            messagebox.showerror(
                "Configuration Setup",
                "No matching configuration templates were found.",
                parent=self,
            )
            return
        confirm_discard = getattr(self.master, "_confirm_discard_unsaved", None)
        if callable(confirm_discard) and not confirm_discard(
            "reinitializing configuration files"
        ):
            return
        existing = [target for _, target in pairs if target.exists()]
        overwrite = self.overwrite_var.get()
        if overwrite and existing:
            confirmed = messagebox.askyesno(
                "Replace Configuration Files",
                "Replace the existing active configuration files shown in the preview?",
                parent=self,
            )
            if not confirmed:
                return
        try:
            changed = initialize_config_templates(
                CONFIGS_DIR, overwrite=overwrite, country=country
            )
        except Exception as exc:
            messagebox.showerror(
                "Configuration Setup", f"Initialization failed:\n{exc}", parent=self
            )
            return
        missing = [target for _, target in pairs if not target.exists()]
        if missing:
            messagebox.showerror(
                "Configuration Setup",
                "Initialization did not create:\n"
                + "\n".join(str(path) for path in missing),
                parent=self,
            )
            return
        created_message = f"Created or replaced {len(changed)} file(s)."
        if not changed:
            created_message = "All selected active files already existed."
        messagebox.showinfo("Configuration Setup", created_message, parent=self)
        self.grab_release()
        self.destroy()
        self.on_complete()


class ConfigurationSetupRequiredTab(ttk.Frame):
    """Landing view displayed until initialization has produced active files."""

    def __init__(self, master: tk.Widget, open_setup: Callable[[], None]) -> None:
        super().__init__(master, padding=30)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        card = ttk.Frame(self, padding=24)
        card.grid(row=0, column=0)
        ttk.Label(
            card, text="Configuration setup required", font=("Segoe UI", 17, "bold")
        ).pack(anchor="center")
        ttk.Label(
            card,
            text=(
                "Create the active configuration files from the default templates or a country example. "
                "The configuration editor and run controls will become available afterwards."
            ),
            wraplength=620,
            justify="center",
        ).pack(pady=(10, 16))
        missing_names = ", ".join(path.name for path in missing_active_configs())
        ttk.Label(
            card, text=f"Missing: {missing_names}", foreground="#8A5A00", wraplength=620
        ).pack(pady=(0, 16))
        ttk.Button(card, text="Start Configuration Setup", command=open_setup).pack()


class PythonScriptManagerApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Python Script Manager (Tkinter)")
        self.geometry("1200x780")
        if HAVE_TTKBOOTSTRAP:
            try:
                self.style = Style(theme="litera", master=self)
            except Exception:  # pragma: no cover - optional dependency
                self.style = None
        self.sections = load_initial_sections()
        self.sample_results = load_sample_results()
        self._setup_dialog: Optional[ConfigurationSetupDialog] = None
        self._setup_prompted = False
        self._optional_config_warning_shown = False
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text="Python Script Manager", font=("Segoe UI", 16, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            header,
            text="Configuration Setup...",
            command=self._open_configuration_setup,
        ).grid(row=0, column=1, sticky="e", padx=(0, 8))
        ttk.Button(header, text="Reload UI", command=self.reload_ui).grid(
            row=0, column=2, sticky="e"
        )

        self.notebook = ttk.Notebook(outer)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self._build_tabs()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_tabs(self) -> None:
        self.notebook_tabs = []
        if missing_active_configs():
            setup_tab = ConfigurationSetupRequiredTab(
                self.notebook, self._open_configuration_setup
            )
            self.notebook.add(setup_tab, text="Setup")
            self.notebook_tabs.append(setup_tab)
            if not self._setup_prompted:
                self._setup_prompted = True
                self.after(150, self._open_configuration_setup)
            return
        self.sections = load_initial_sections()
        self.sample_results = load_sample_results()
        self.config_tab = ConfigurationTab(self.notebook, self.sections)
        self.notebook.add(self.config_tab, text="Configuration")
        self.notebook_tabs.append(self.config_tab)
        self.results_tab = ResultsTab(self.notebook, self.sample_results)
        self.run_tab = RunTab(self.notebook, self.config_tab, self.results_tab)
        self.notebook.add(self.run_tab, text="Run")
        self.notebook.add(self.results_tab, text="Results")
        self.notebook_tabs.extend([self.run_tab, self.results_tab])
        self.after(150, self._warn_about_missing_optional_configs)

    def _warn_about_missing_optional_configs(self) -> None:
        if self._optional_config_warning_shown:
            return
        missing = missing_optional_configs()
        if not missing:
            return
        self._optional_config_warning_shown = True
        missing_names = ", ".join(path.name for path in missing)
        messagebox.showwarning(
            "Optional Configuration Not Created",
            "The following optional configuration file(s) have not been created: "
            f"{missing_names}. They are not required for initial setup, but may be "
            "required later for suitability analysis, energy profiles, or Snakemake "
            "workflows.",
            parent=self,
        )

    def _has_unsaved_configuration_changes(self) -> bool:
        tab = getattr(self, "config_tab", None)
        if tab is None:
            return False
        if hasattr(tab, "has_unsaved_changes"):
            return bool(tab.has_unsaved_changes())
        if any(
            bool(getattr(tab, attr, False))
            for attr in ("config_dirty", "snakefile_dirty", "advanced_dirty")
        ):
            return True
        return any(
            bool(info.get("dirty")) for info in getattr(tab, "extra_files", {}).values()
        )

    def _confirm_discard_unsaved(self, action: str) -> bool:
        tab = getattr(self, "config_tab", None)
        if tab is None or not self._has_unsaved_configuration_changes():
            return True
        names = (
            tab.dirty_document_names() if hasattr(tab, "dirty_document_names") else []
        )
        details = "\n".join(f"- {name}" for name in names)
        return messagebox.askyesno(
            "Unsaved Configuration Changes",
            f"The following files have unsaved changes:\n\n{details}\n\n"
            f"Discard those changes before {action}?",
            parent=self,
        )

    def _on_close(self) -> None:
        if self._confirm_discard_unsaved("closing the application"):
            self.destroy()

    def _open_configuration_setup(self) -> None:
        if self._setup_dialog is not None and self._setup_dialog.winfo_exists():
            self._setup_dialog.lift()
            self._setup_dialog.focus_force()
            return
        dialog = ConfigurationSetupDialog(self, self._configuration_setup_complete)
        self._setup_dialog = dialog
        dialog.bind(
            "<Destroy>", lambda _event: self._clear_setup_dialog(dialog), add="+"
        )

    def _clear_setup_dialog(self, dialog: ConfigurationSetupDialog) -> None:
        if self._setup_dialog is dialog:
            self._setup_dialog = None

    def _configuration_setup_complete(self) -> None:
        self._setup_dialog = None
        self.reload_ui(confirm=False)

    def reload_ui(self, confirm: bool = True) -> None:
        if confirm and not self._confirm_discard_unsaved("reloading the interface"):
            return
        current_index = (
            self.notebook.index(self.notebook.select()) if self.notebook.tabs() else 0
        )
        for tab in getattr(self, "notebook_tabs", []):
            try:
                self.notebook.forget(tab)
            except Exception:
                pass
            try:
                tab.destroy()
            except Exception:
                pass
        self._build_tabs()
        if self.notebook.tabs():
            restored_index = min(current_index, len(self.notebook.tabs()) - 1)
            self.notebook.select(restored_index)


def main() -> None:
    app = PythonScriptManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
