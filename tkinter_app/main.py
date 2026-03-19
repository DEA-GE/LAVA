"""Tkinter-based translation of the Python Script Manager interface."""
from __future__ import annotations
import ast
import html
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
CONFIG_ADVANCED_SETTINGS_PATH = CONFIGS_DIR / "config_advanced_settings.yaml"
SNAKEMAKE_GLOBAL_PATH = PARENT_DIR / "snakemake"/ "Snakefile"
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))
if str(PARENT_DIR) not in sys.path:
    sys.path.append(str(PARENT_DIR))
from flag_mapper import make_path, ui_bool_to_numeric, yaml_numeric_to_ui_bool  # type: ignore  # noqa: E402
from data_loader import (  # type: ignore  # noqa: E402
    DEFAULT_RESULTS_DATA,
    CONFIG_SNAKEMAKE_STAGE_FLAGS,
    cast_value,
    round_trip_available,
    load_initial_sections,
    load_onshore_sections,
    load_solar_sections,
    load_config_snakemake_sections,
    load_sample_results,
    save_sections_round_trip,
    stringify_list_value,
)
try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None
try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # type: ignore
    from matplotlib.figure import Figure  # type: ignore
    MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    MATPLOTLIB_AVAILABLE = False
SNAKEFILE_TEMPLATE = """"""
SNAKEMAKE_STAGE_KEYS = [stage["key"] for stage in CONFIG_SNAKEMAKE_STAGE_FLAGS]


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
        for sequence in ("<KeyRelease>", "<<Paste>>", "<<Cut>>", "<<Undo>>", "<<Redo>>"):
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


def sections_to_yaml(sections: List[Dict[str, Any]]) -> str:
    """Return a YAML representation that mirrors the React implementation."""
    lines: List[str] = ["# Configuration File", ""]
    for section in sections:
        display_name = section.get("displayName", section["name"])
        lines.append(f"# {display_name}")
        description = section.get("description")
        if description:
            lines.append(f"# {description}")
        lines.append(f"{section['name']}:")
        for param in section.get("parameters", []):
            if param.get("description"):
                lines.append(f"  # {param['description']}")
            path = make_path(section["name"], param["key"])
            value_type = param.get("type", "string")
            value = param.get("value")
            if value_type == "boolean":
                value = ui_bool_to_numeric(path, bool(value))
            elif value_type.startswith("list:"):
                value = _coerce_list_value(value_type, value)
            elif value_type == "mapping":
                mapping_value = cast_value("mapping", value)
                if isinstance(mapping_value, MappingABC):
                    if not mapping_value:
                        lines.append(f"  {param['key']}: {{}}")
                    else:
                        lines.append(f"  {param['key']}:")
                        for sub_key, sub_value in mapping_value.items():
                            indent = "    "
                            if isinstance(sub_value, list):
                                if not sub_value:
                                    lines.append(f"{indent}{sub_key}: []")
                                else:
                                    joined = ", ".join(repr(item) for item in sub_value)
                                    lines.append(f"{indent}{sub_key}: [{joined}]")
                            elif sub_value is None:
                                lines.append(f"{indent}{sub_key}: null")
                            elif isinstance(sub_value, str):
                                lines.append(f"{indent}{sub_key}: {repr(sub_value)}")
                            else:
                                lines.append(f"{indent}{sub_key}: {sub_value}")
                    continue
                value = mapping_value
            if isinstance(value, bool):
                value_str = "true" if value else "false"
            elif isinstance(value, (list, dict)):
                value_str = json.dumps(value, ensure_ascii=False)
            elif value is None:
                value_str = "null"
            elif isinstance(value, str):
                escaped = value.replace('"', '\\"')
                value_str = f'"{escaped}"'
            else:
                value_str = str(value)
            lines.append(f"  {param['key']}: {value_str}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def rebuild_from_widgets(original: Any, registry: Dict[str, tk.Variable], path: str = "") -> Any:
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
        return None, "PyYAML is required for raw YAML editing. Install with `pip install PyYAML`."
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
            continue
        for param in section.get("parameters", []):
            key = param["key"]
            if key not in section_data:
                continue
            raw_value = section_data[key]
            path = make_path(section["name"], key)
            value_type = param.get("type", "string")
            if value_type == "boolean":
                param["value"] = bool(yaml_numeric_to_ui_bool(path, raw_value))
            elif value_type == "number":
                if raw_value in (None, ""):
                    param["value"] = None
                else:
                    try:
                        param["value"] = float(raw_value)
                    except (TypeError, ValueError):
                        param["value"] = None
            elif value_type.startswith("list:"):
                param["value"] = _coerce_list_value(value_type, raw_value)
            elif value_type == "mapping":
                param["value"] = cast_value("mapping", raw_value)
            elif value_type == "array":
                if isinstance(raw_value, (list, dict)):
                    param["value"] = json.dumps(raw_value)
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


def _percentile_stretch(arr: np.ndarray, pmin: float = 2, pmax: float = 98) -> np.ndarray:
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
                src.crs, "EPSG:4326", bounds.left, bounds.bottom, bounds.right, bounds.top
            )
        else:
            west, south, east, north = bounds.left, bounds.bottom, bounds.right, bounds.top

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
                    arr = np.stack([_percentile_stretch(arr[i]) for i in range(3)], axis=0)
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
    fmap = folium.Map(location=default_center, zoom_start=default_zoom, control_scale=True)

    def update_union(
        current: Optional[List[List[float]]], new_bounds: Optional[List[List[float]]]
    ) -> Optional[List[List[float]]]:
        if not new_bounds:
            return current
        if current is None:
            return [[new_bounds[0][0], new_bounds[0][1]], [new_bounds[1][0], new_bounds[1][1]]]
        south = min(current[0][0], new_bounds[0][0])
        west = min(current[0][1], new_bounds[0][1])
        north = max(current[1][0], new_bounds[1][0])
        east = max(current[1][1], new_bounds[1][1])
        return [[south, west], [north, east]]

    sorted_layers = sorted(layers, key=lambda item: (item.get("order", 0), item.get("index", 0)))
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
                highlighted["fillOpacity"] = min(1.0, style.get("fillOpacity", opacity * 0.6) + 0.1)
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
            legend_content = "<br>".join(html.escape(part) for part in legend_content.splitlines())
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


def _show_map_fallback(html_path: Path, parent: tk.Widget, reason: Optional[str] = None) -> Dict[str, Any]:
    info = "Interactive map opened in your default browser."
    if reason:
        info = f"{info} ({reason})"
    label = ttk.Label(parent, text=info, foreground="#a66b00", wraplength=420, justify="left")
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
        return _show_map_fallback(target, parent, f"Unable to initialise WebView2: {exc}")

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
        for method_name in ("load_html", "load_html_string", "set_html", "load_html_content"):
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
            return _show_map_fallback(target, parent, "Unable to display map in embedded viewer.")

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
    return {"embedded": True, "widget": container, "cleanup": cleanup, "browser": widget}


class ConfigurationTab(ttk.Frame):
    """Configuration management tab."""
    def __init__(self, master: tk.Widget, sections: List[Dict[str, Any]]):
        super().__init__(master)
        self.sections_baseline = deepcopy(sections)
        self.sections = deepcopy(sections)
        self.config_save_path: Optional[Path] = None
        self._config_source_text: Optional[str] = None
        self.snakefile_save_path: Optional[Path] = None
        self.config_dirty = False
        self.snakefile_dirty = False
        self.raw_dirty = False
        self.advanced_save_path: Optional[Path] = None
        self._advanced_source_text: str = ""
        self.advanced_dirty = False
        self.enable_visual_editor = True
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.config_mode = tk.StringVar(value="visual")
        self.param_vars: Dict[Tuple[int, int], Any] = {}
        self.mapping_registries: Dict[Tuple[int, int], Dict[str, tk.StringVar]] = {}
        self.extra_files = self._load_additional_files()
        self._build_ui()
        self._refresh_config_view()
        if self.sections:
            self.section_listbox.selection_set(0)
        self._load_existing_config()
    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.config_tab = ttk.Frame(notebook)
        self.config_tab.columnconfigure(0, weight=1)
        self.config_tab.rowconfigure(1, weight=1)
        notebook.add(self.config_tab, text="config.yaml")
        mode_frame = ttk.Frame(self.config_tab)
        mode_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ttk.Label(mode_frame, text="Edit Mode:").pack(side="left")
        self.visual_button = ttk.Radiobutton(
            mode_frame, text="Visual Editor", value="visual", variable=self.config_mode, command=self._on_mode_change
        )
        self.visual_button.pack(side="left", padx=6)
        self.raw_button = ttk.Radiobutton(
            mode_frame, text="Raw YAML", value="raw", variable=self.config_mode, command=self._on_mode_change
        )
        self.raw_button.pack(side="left")
        self.config_status = ttk.Label(mode_frame, text="")
        self.config_status.pack(side="right")
        self.visual_container = ttk.Frame(self.config_tab)
        self.visual_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.visual_container.columnconfigure(1, weight=1)
        self.visual_container.columnconfigure(0, minsize=260)  # widen left pane
        self.visual_container.rowconfigure(0, weight=1)
        self.section_list_var = tk.StringVar(value=[sec.get("displayName", sec["name"]) for sec in self.sections])
        self.section_listbox = tk.Listbox(
            self.visual_container, listvariable=self.section_list_var, exportselection=False, height=20
        )
        self.section_listbox.grid(row=0, column=0, sticky="nsew")
        self.section_listbox.bind("<<ListboxSelect>>", self._on_section_select)
        section_scroll = ttk.Scrollbar(self.visual_container, orient="vertical", command=self.section_listbox.yview)
        section_scroll.grid(row=0, column=0, sticky="nse")
        self.section_listbox.configure(yscrollcommand=section_scroll.set)
        self.param_canvas = tk.Canvas(self.visual_container, highlightthickness=0)
        self.param_canvas.grid(row=0, column=1, sticky="nsew")
        params_scroll = ttk.Scrollbar(self.visual_container, orient="vertical", command=self.param_canvas.yview)
        params_scroll.grid(row=0, column=2, sticky="ns")
        self.param_canvas.configure(yscrollcommand=params_scroll.set)
        self.param_inner = ttk.Frame(self.param_canvas)
        self.param_inner.bind("<Configure>", lambda e: self.param_canvas.configure(scrollregion=self.param_canvas.bbox("all")))
        self.param_canvas.create_window((0, 0), window=self.param_inner, anchor="nw")
        self.raw_container = ttk.Frame(self.config_tab)
        self.raw_container.columnconfigure(0, weight=1)
        self.raw_container.rowconfigure(0, weight=1)
        self.config_text = tk.Text(self.raw_container, wrap="none", font=("Courier New", 10))
        self.config_text.grid(row=0, column=0, sticky="nsew")
        self.config_text.bind("<KeyRelease>", lambda _: self._mark_config_dirty(raw=True))
        text_scroll_y = ttk.Scrollbar(self.raw_container, orient="vertical", command=self.config_text.yview)
        text_scroll_y.grid(row=0, column=1, sticky="ns")
        self.config_text.configure(yscrollcommand=text_scroll_y.set)
        text_scroll_x = ttk.Scrollbar(self.raw_container, orient="horizontal", command=self.config_text.xview)
        text_scroll_x.grid(row=1, column=0, sticky="ew")
        self.config_text.configure(xscrollcommand=text_scroll_x.set)
        self.config_highlighter = TextSyntaxHighlighter(self.config_text, "yaml")
        button_row = ttk.Frame(self.config_tab)
        button_row.grid(row=2, column=0, sticky="e", padx=10, pady=(5, 10))
        ttk.Button(button_row, text="Discard Changes", command=self._reset_config).pack(side="right", padx=6)
        ttk.Button(button_row, text="Save", command=self._save_config).pack(side="right")
        self.snakefile_tab = ttk.Frame(notebook)
        self.snakefile_tab.columnconfigure(0, weight=1)
        self.snakefile_tab.rowconfigure(0, weight=1)
        notebook.add(self.snakefile_tab, text="Snakefile")
        self.snakefile_text = tk.Text(self.snakefile_tab, wrap="none", font=("Courier New", 10))
        self.snakefile_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.snakefile_text.insert("1.0", SNAKEFILE_TEMPLATE)
        self.snakefile_text.bind("<KeyRelease>", lambda _: self._mark_snakefile_dirty())
        snake_scroll_y = ttk.Scrollbar(self.snakefile_tab, orient="vertical", command=self.snakefile_text.yview)
        snake_scroll_y.grid(row=0, column=1, sticky="ns", pady=10)
        self.snakefile_text.configure(yscrollcommand=snake_scroll_y.set)
        snake_scroll_x = ttk.Scrollbar(self.snakefile_tab, orient="horizontal", command=self.snakefile_text.xview)
        snake_scroll_x.grid(row=1, column=0, sticky="ew", padx=10)
        self.snakefile_text.configure(xscrollcommand=snake_scroll_x.set)
        self.snakefile_highlighter = TextSyntaxHighlighter(self.snakefile_text, "python")
        snake_buttons = ttk.Frame(self.snakefile_tab)
        snake_buttons.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        self.snakefile_status = ttk.Label(snake_buttons, text="")
        self.snakefile_status.pack(side="left", padx=(0, 10))
        ttk.Button(snake_buttons, text="Discard Changes", command=self._reset_snakefile).pack(side="right", padx=6)
        ttk.Button(snake_buttons, text="Save", command=self._save_snakefile).pack(side="right")
        if SNAKEMAKE_GLOBAL_PATH.exists():
            try:
                snake_content = SNAKEMAKE_GLOBAL_PATH.read_text(encoding="utf-8")
            except OSError:
                self.snakefile_status.configure(text=f"Could not read {SNAKEMAKE_GLOBAL_PATH.name}")
            else:
                self.snakefile_text.delete("1.0", "end")
                self.snakefile_text.insert("1.0", snake_content)
                self.snakefile_status.configure(text=f"Loaded from {SNAKEMAKE_GLOBAL_PATH.name}")
                self.snakefile_save_path = SNAKEMAKE_GLOBAL_PATH
                self.snakefile_dirty = False
                self._refresh_snakefile_highlight()
        self.advanced_tab = ttk.Frame(notebook)
        self.advanced_tab.columnconfigure(0, weight=1)
        self.advanced_tab.rowconfigure(0, weight=1)
        notebook.add(self.advanced_tab, text="config_advanced_settings.yaml")
        self.advanced_text = tk.Text(self.advanced_tab, wrap="none", font=("Courier New", 10))
        self.advanced_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.advanced_text.bind("<KeyRelease>", lambda _: self._mark_advanced_dirty())
        advanced_scroll_y = ttk.Scrollbar(self.advanced_tab, orient="vertical", command=self.advanced_text.yview)
        advanced_scroll_y.grid(row=0, column=1, sticky="ns", pady=10)
        self.advanced_text.configure(yscrollcommand=advanced_scroll_y.set)
        advanced_scroll_x = ttk.Scrollbar(self.advanced_tab, orient="horizontal", command=self.advanced_text.xview)
        advanced_scroll_x.grid(row=1, column=0, sticky="ew", padx=10)
        self.advanced_text.configure(xscrollcommand=advanced_scroll_x.set)
        self.advanced_highlighter = TextSyntaxHighlighter(self.advanced_text, "yaml")
        advanced_buttons = ttk.Frame(self.advanced_tab)
        advanced_buttons.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        self.advanced_status = ttk.Label(advanced_buttons, text="")
        self.advanced_status.pack(side="left", padx=(0, 10))
        ttk.Button(advanced_buttons, text="Discard Changes", command=self._reset_advanced_settings).pack(
            side="right", padx=6
        )
        ttk.Button(advanced_buttons, text="Save", command=self._save_advanced_settings).pack(side="right")
        self._load_advanced_settings()
        for label, info in self.extra_files.items():
            file_frame = ttk.Frame(notebook)
            file_frame.columnconfigure(0, weight=1)
            file_frame.rowconfigure(0, weight=1)
            notebook.add(file_frame, text=label)
            if info.get("sections"):
                self._build_structured_extra_editor(label, info, file_frame)
            else:
                self._build_raw_extra_editor(label, info, file_frame)
        for info in self.extra_files.values():
            info.setdefault("dirty", False)
    def _load_existing_config(self) -> None:
        config_path = PARENT_DIR / "config.yaml"
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
            self._refresh_config_highlight()
        else:
            self._populate_raw_editor()
        self._update_config_status()

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

    def _load_advanced_settings(self) -> None:
        candidates = [
            PARENT_DIR / "config_advanced_settings.yaml",
            CONFIG_ADVANCED_SETTINGS_PATH,
        ]
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
            self.advanced_save_path = candidate
            self._advanced_source_text = text
            self.advanced_dirty = False
            self.advanced_status.configure(text=f"Loaded from {candidate.name}")
            self._refresh_advanced_highlight()
            return
        self.advanced_save_path = CONFIG_ADVANCED_SETTINGS_PATH
        self._advanced_source_text = ""
        self.advanced_text.delete("1.0", "end")
        self.advanced_status.configure(text=f"{CONFIG_ADVANCED_SETTINGS_PATH.name} not found")
        self._refresh_advanced_highlight()
    def _load_additional_files(self) -> Dict[str, Dict[str, Any]]:
        entries: Dict[str, Dict[str, Any]] = {}
        specs = [
            ("onshorewind.yaml", (CONFIGS_DIR / "onshorewind.yaml", PARENT_DIR / "onshorewind.yaml"), load_onshore_sections, "generic"),
            ("solar.yaml", (CONFIGS_DIR / "solar.yaml", PARENT_DIR / "solar.yaml"), load_solar_sections, "generic"),
            ("config_snakemake.yaml", (CONFIGS_DIR / "config_snakemake.yaml", PARENT_DIR / "config_snakemake.yaml"), load_config_snakemake_sections, "config_snakemake"),
        ]
        for label, candidate_paths, section_loader, kind in specs:
            existing_path: Optional[Path] = None
            content = ""
            expected_path = candidate_paths[0]
            for candidate in candidate_paths:
                if candidate.exists():
                    existing_path = candidate
                    try:
                        content = candidate.read_text(encoding="utf-8")
                    except OSError:
                        content = ""
                    break
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
    def _build_raw_extra_editor(self, label: str, info: Dict[str, Any], parent: tk.Widget) -> None:
        text_widget = tk.Text(parent, wrap="none", font=("Courier New", 10))
        text_widget.grid(row=0, column=0, sticky="nsew", padx=8, pady=(4, 6))
        text_widget.insert("1.0", info.get("baseline", ""))
        text_widget.bind("<KeyRelease>", lambda _event, name=label: self._mark_extra_dirty(name))
        info["highlighter"] = TextSyntaxHighlighter(
            text_widget, self._detect_language_for_label(label)
        )
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
        ttk.Button(buttons, text="Discard Changes", command=lambda name=label: self._reset_extra_file(name)).pack(
            side="right", padx=6
        )
        ttk.Button(buttons, text="Save", command=lambda name=label: self._save_extra_file(name)).pack(side="right")
        info["text_widget"] = text_widget
        info["status_label"] = status_label
    def _build_structured_extra_editor(self, label: str, info: Dict[str, Any], parent: tk.Widget) -> None:
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
        editor_stack.grid(row=1, column=0, sticky="nsew", padx=8, pady=0 )
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

        vsb = ttk.Scrollbar(visual_container, orient="vertical", command=visual_canvas.yview)
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

        text_widget = tk.Text(raw_frame, wrap="none", font=("Courier New", 10))
        text_widget.grid(row=0, column=0, sticky="nsew")
        raw_frame.rowconfigure(0, weight=1)
        raw_frame.columnconfigure(0, weight=1)

        baseline = info.get("baseline") or self._serialize_sections_for_kind(info.get("kind"), info.get("sections"))
        text_widget.insert("1.0", baseline)
        text_widget.bind("<KeyRelease>", lambda _event, name=label: self._mark_extra_dirty(name))
        info["highlighter"] = TextSyntaxHighlighter(
            text_widget, self._detect_language_for_label(label)
        )
        info["text_widget"] = text_widget

        scroll_y = ttk.Scrollbar(raw_frame, orient="vertical", command=text_widget.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        text_widget.configure(yscrollcommand=scroll_y.set)
        scroll_x = ttk.Scrollbar(raw_frame, orient="horizontal", command=text_widget.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        text_widget.configure(xscrollcommand=scroll_x.set)

        # --- Bottom buttons (outside the stack, fixed position) ---
        buttons = ttk.Frame(parent)
        buttons.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        status_text = f"Loaded from {info['path'].name}" if info["path"] else f"Saving to {info['expected_path'].name}"
        status_label = ttk.Label(buttons, text=status_text)
        status_label.pack(side="left", padx=(0, 10))
        info["status_label"] = status_label
        ttk.Button(buttons, text="Discard Changes", command=lambda name=label: self._reset_extra_file(name)).pack(
            side="right", padx=6
        )
        ttk.Button(buttons, text="Save", command=lambda name=label: self._save_extra_file(name)).pack(side="right")

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
        for s_index, section in enumerate(info.get("sections", [])):
            section_frame = ttk.LabelFrame(
                frame, text=section.get("displayName", section.get("name", f"Section {s_index + 1}"))
            )
            section_frame.pack(fill="x", pady=(6, 6))
            section_frame.configure(padding=(6, 4))
            for p_index, param in enumerate(section.get("parameters", [])):
                label_text = param.get("label") or param["key"].replace("_", " ")
                desc_text = (param.get("description") or "").strip()
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
                    frame = ttk.LabelFrame(section_frame, text=label_text)
                    frame.pack(fill="x", padx=6, pady=2)
                    frame.columnconfigure(0, weight=1)
                    if desc_text:
                        ttk.Label(frame, text=desc_text, wraplength=240, justify="left").pack(
                            anchor="w", padx=4, pady=(0, 4)
                        )
                    registry: Dict[str, tk.StringVar] = {}
                    self._render_mapping_fields(
                        frame,
                        mapping_value,
                        param["key"],
                        registry,
                        lambda name=label, info_ref=ctrl_info: self._on_extra_mapping_changed(name, info_ref),
                        row_width=100,
                    )
                    ctrl_info["mapping_registry"] = registry
                    ctrl_info["mapping_template"] = template
                    ctrl_info["mapping_base_path"] = param["key"]
                    info["param_controls"].append(ctrl_info)
                    continue

                row = ttk.Frame(section_frame)
                row.pack(fill="x", pady=2, padx=6)
                row.columnconfigure(1, weight=0)
                row.columnconfigure(2, weight=1)
                ttk.Label(row, text=label_text).grid(row=0, column=0, sticky="w", padx=(0, 6))
                if param_type == "boolean":
                    var = tk.BooleanVar(value=bool(param.get("value")))
                    ctrl_info["var"] = var
                    widget = ttk.Checkbutton(
                        row,
                        variable=var,
                        command=lambda name=label: self._on_extra_param_changed(name),
                    )
                    widget.grid(row=0, column=1, sticky="ew", padx=(0, 6))
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
                    value = display_value
                    var = tk.StringVar(value=value)
                    ctrl_info["var"] = var
                    entry = ttk.Entry(row, textvariable=var, width=20)
                    entry.grid(row=0, column=1, sticky="w", padx=(0, 6))
                    var.trace_add("write", lambda *_args, name=label: self._on_extra_param_changed(name))
                    ctrl_info["widget"] = entry
                if desc_text:
                    ttk.Label(row, text=desc_text, wraplength=240, justify="left").grid(
                        row=0, column=2, sticky="nw", padx=(6, 0)
                    )
                info["param_controls"].append(ctrl_info)
        canvas = info.get("visual_canvas")
        if canvas:
            canvas.update_idletasks()
            canvas.yview_moveto(0.0)
    def _on_extra_param_changed(self, label: str) -> None:
        self._update_extra_sections_from_controls(label)
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
            elif param_type == "number":
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
                            param["value"] = int(numeric) if numeric.is_integer() else numeric
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
        for ctrl in info.get("param_controls", []):
            param = ctrl["param"]
            param_type = ctrl.get("type", "string")
            value = param.get("value")
            if param_type == "boolean":
                var = ctrl.get("var")
                if var is not None:
                    var.set(bool(value))
            elif param_type == "array":
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
                    relative = full_path[len(base_key):].lstrip(".") if full_path.startswith(base_key) else full_path
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
    def _sync_extra_visual_to_text(self, label: str) -> None:
        info = self.extra_files.get(label)
        if not info:
            return
        text_widget: Optional[tk.Text] = info.get("text_widget")
        if not text_widget:
            return
        self._update_extra_sections_from_controls(label)
        yaml_text = self._serialize_sections_for_kind(info.get("kind"), info.get("sections"))
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", yaml_text)
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
            sections = info.get("sections") or load_config_snakemake_sections()
            sections, error = self._config_snakemake_sections_from_yaml(yaml_text, sections)
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
            self._sync_extra_visual_to_text(label)

            if raw_frame is not None:
                raw_frame.grid(row=0, column=0, sticky="nsew")
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
                data[param["key"]] = value
        if yaml is not None:
            try:
                return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
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
        snakefile_value = _stringify(flat.get("snakefile", "snakemake_global")) or "snakemake_global"
        study_region = _stringify(flat.get("study_region_name", ""))
        scenario = _stringify(flat.get("scenario", ""))
        technologies = [str(item) for item in self._coerce_sequence_value(flat.get("technologies", []))]
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
            key: self._coerce_boolean_value(flat.get(key, True), default=True) for key in SNAKEMAKE_STAGE_KEYS
        }
        data: Dict[str, Any] = {
            "study_region_name": study_region,
            "scenario": scenario,
            "technologies": technologies,
            "cores": cores_value,
            "snakefile": snakefile_value,
            "weather_years": weather_years,
            "stages": stages,
        }
        if yaml is not None:
            try:
                return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
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
            "study_region_name": data.get("study_region_name", ""),
            "scenario": data.get("scenario", ""),
            "technologies": self._coerce_sequence_value(data.get("technologies", [])),
            "weather_years": self._coerce_sequence_value(data.get("weather_years", [])),
        }
        stages = data.get("stages") or {}
        if isinstance(stages, MappingABC):
            for key in SNAKEMAKE_STAGE_KEYS:
                flat[key] = self._coerce_boolean_value(stages.get(key, True), default=True)
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
                    param["value"] = self._coerce_integer_value(value, default=default_val)
                elif param_type == "boolean":
                    param["value"] = self._coerce_boolean_value(value)
                elif param_type == "array":
                    param["value"] = self._coerce_sequence_value(value)
                elif key == "weather_years":
                    param["value"] = self._stringify_weather_years_field(value)
                else:
                    param["value"] = "" if value is None else str(value)
        return sections, None

    def _mark_extra_dirty(self, label: str) -> None:
        info = self.extra_files.get(label)
        if not info:
            return
        info["dirty"] = True
        status_label = info.get("status_label")
        if status_label:
            status_label.configure(text="Unsaved changes")
    def _save_extra_file(self, label: str) -> None:
        info = self.extra_files.get(label)
        if not info:
            return
        kind = info.get("kind")
        sections_data: Optional[List[Dict[str, Any]]] = info.get("sections")
        has_structured_sections = sections_data is not None
        text_widget: Optional[tk.Text] = info.get("text_widget")

        if has_structured_sections:
            mode_var: Optional[tk.StringVar] = info.get("mode_var")
            if mode_var is not None and mode_var.get() == "raw":
                if not self._sync_extra_text_to_visual(label):
                    return
            else:
                self._update_extra_sections_from_controls(label)
            sections_list: List[Dict[str, Any]] = info.get("sections") or []
            serialized_content = self._serialize_sections_for_kind(kind, sections_list)
        else:
            if text_widget is None:
                return
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
                return
            save_path = Path(filename)
        final_content = serialized_content
        used_round_trip = False
        if has_structured_sections and round_trip_available():
            try:
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
                return

        if text_widget is not None:
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", final_content)
            highlighter = info.get("highlighter")
            if isinstance(highlighter, TextSyntaxHighlighter):
                highlighter.refresh()

        info["baseline"] = final_content
        info["dirty"] = False
        info["save_path"] = save_path
        info["path"] = save_path
        info["expected_path"] = save_path
        if has_structured_sections:
            self._render_extra_visual_sections(label, info)
            self._update_extra_visual_controls(label)
        if kind == "config_snakemake":
            app = self.master.master
            if hasattr(app, "run_tab"):
                app.run_tab._refresh_snakemake_settings_display()
        status_label = info.get("status_label")
        if status_label:
            status_label.configure(text=f"Saved to {save_path.name}")
        messagebox.showinfo("File Saved", f"Saved to {save_path}")
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
                updated_sections, error = self._config_snakemake_sections_from_yaml(baseline, sections)
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
            highlighter = info.get("highlighter")
            if isinstance(highlighter, TextSyntaxHighlighter):
                highlighter.refresh()
        info["dirty"] = False
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
    def _on_mode_change(self) -> None:
        if self.config_mode.get() == "visual" and self.raw_dirty:
            updated, error = yaml_to_sections(self.sections, self.config_text.get("1.0", "end-1c"))
            if error:
                messagebox.showerror("Invalid YAML", error)
                self.config_mode.set("raw")
                return
            if updated is not None:
                self.sections = updated
                self.sections_baseline = deepcopy(updated)
                names = [sec.get("displayName", sec["name"]) for sec in self.sections]
                self.section_list_var.set(names)
                self.section_listbox.selection_clear(0, tk.END)
                if self.sections:
                    self.section_listbox.selection_set(0)
                self.raw_dirty = False
        self._refresh_config_view()
    def _refresh_config_view(self) -> None:
        mode = self.config_mode.get()
        if mode == "visual":
            self.raw_container.grid_remove()
            self.visual_container.grid()
            current = self.section_listbox.curselection()
            index = current[0] if current else 0
            self._render_parameters(index)
        else:
            self.visual_container.grid_remove()
            self.raw_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
            if self.enable_visual_editor:
                self._populate_raw_editor()
        self._update_config_status()
    def _populate_raw_editor(self) -> None:
        if not self.enable_visual_editor:
            return
        text = sections_to_yaml(self.sections)
        current = self.config_text.get("1.0", "end-1c")
        if current.strip() != text.strip():
            self.config_text.delete("1.0", "end")
            self.config_text.insert("1.0", text)
            self.raw_dirty = False
            self._refresh_config_highlight()
    def _on_section_select(self, _event: tk.Event) -> None:
        if not self.section_listbox.curselection():
            return
        index = self.section_listbox.curselection()[0]
        self._render_parameters(index)
    def _render_parameters(self, section_index: int) -> None:
        for child in self.param_inner.winfo_children():
            child.destroy()
        self.param_vars.clear()
        if section_index >= len(self.sections):
            return
        section = self.sections[section_index]
        header = section.get("displayName", section["name"])
        ttk.Label(self.param_inner, text=header, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.param_inner.columnconfigure(1, weight=1)
        row_pointer = 1
        for idx, param in enumerate(section.get("parameters", [])):
            description = param.get("description")
            if description:
                ttk.Label(
                    self.param_inner,
                    text=description,
                    foreground="#555555",
                    wraplength=420,
                    anchor="w",
                    justify="left",
                ).grid(row=row_pointer, column=0, columnspan=3, sticky="w", padx=(0, 8), pady=(0, 2))
                row_pointer += 1
            key = param["key"]
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
                frame.grid(row=row_pointer, column=0, columnspan=2, sticky="ew", padx=(0, 10), pady=2)
                frame.columnconfigure(0, weight=1)
                if description:
                    ttk.Label(
                        frame,
                        text=description,
                        foreground="#555555",
                        wraplength=600,
                        anchor="w",
                        justify="left",
                    ).pack(anchor="w", padx=6, pady=(2, 2))
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
                row_pointer += 1
                continue
            ttk.Label(self.param_inner, text=key).grid(row=row_pointer, column=0, sticky="w", padx=(0, 10), pady=2)
            if value_type == "boolean":
                var = tk.BooleanVar(value=bool(param.get("value")))
                widget = ttk.Checkbutton(
                    self.param_inner,
                    variable=var,
                    command=lambda idx=idx: self._on_param_toggle(section_index, idx),
                )
                widget.grid(row=row_pointer, column=1, sticky="w")
                self.param_vars[(section_index, idx)] = var
            elif value_type == "array":
                widget = tk.Text(self.param_inner, height=4, width=40, wrap="word")
                current_value = param.get("value")
                if isinstance(current_value, (list, dict)):
                    display_text = json.dumps(current_value, ensure_ascii=False, indent=2)
                else:
                    display_text = "" if current_value is None else str(current_value)
                widget.insert("1.0", display_text)
                widget.grid(row=row_pointer, column=1, sticky="ew")
                widget.bind(
                    "<KeyRelease>",
                    lambda _event, s_index=section_index, p_index=idx, v_type=value_type, control=widget: self._on_text_param_change(
                        s_index, p_index, v_type, control
                    ),
                )
                self.param_vars[(section_index, idx)] = widget
            else:
                if value_type == "number":
                    raw_initial = param.get("value")
                    initial = "" if raw_initial in (None, "") else str(raw_initial)
                elif value_type.startswith("list:"):
                    initial = stringify_list_value(param.get("value"))
                else:
                    raw_initial = param.get("value", "")
                    initial = "" if raw_initial is None else str(raw_initial)
                var = tk.StringVar(value=initial)
                entry = ttk.Entry(self.param_inner, textvariable=var, width=40)
                entry.grid(row=row_pointer, column=1, sticky="ew")
                var.trace_add(
                    "write",
                    lambda *_,
                    s_index=section_index,
                    p_index=idx,
                    v_type=value_type,
                    variable=var: self._on_param_change(s_index, p_index, v_type, variable),
                )
                self.param_vars[(section_index, idx)] = var
            row_pointer += 1

    def _lookup_nested_value(self, mapping: Mapping[str, Any], relative_path: str) -> Any:
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
        base_key = param.get("_base_path", make_path(self.sections[section_index]["name"], param["key"]))
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
        self.sections[section_index]["parameters"][param_index]["value"] = bool(var.get())
        self._mark_config_dirty()
    def _on_param_change(
        self, section_index: int, param_index: int, value_type: str, variable: tk.Variable
    ) -> None:
        raw_value = variable.get()
        if value_type == "number":
            text = raw_value.strip()
            if not text:
                value = None
            else:
                try:
                    value = float(text)
                except ValueError:
                    value = None
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
        self.config_dirty = True
        if raw:
            self.raw_dirty = True
        self._update_config_status()
    def _update_config_status(self) -> None:
        if self.config_dirty:
            status = "Unsaved changes"
        elif self.config_save_path:
            status = f"Saved ({self.config_save_path.name})"
        else:
            status = "Saved"
        self.config_status.configure(text=status)
    def _save_config(self) -> None:
        saving_raw = self.config_mode.get() == "raw" or not self.enable_visual_editor
        if saving_raw:
            yaml_text = self.config_text.get("1.0", "end-1c")
            if self.enable_visual_editor:
                updated, error = yaml_to_sections(self.sections, yaml_text)
                if error:
                    messagebox.showerror("Invalid YAML", error)
                    return
                if updated is not None:
                    self.sections = updated
                    self.sections_baseline = deepcopy(updated)
                    self.raw_dirty = False
        else:
            yaml_text = sections_to_yaml(self.sections)
        if not yaml_text.endswith("\n"):
            yaml_text += "\n"
        if not self.config_save_path:
            filename = filedialog.asksaveasfilename(
                title="Save config.yaml",
                defaultextension=".yaml",
                initialfile="config.yaml",
                filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
            )
            if not filename:
                return
            self.config_save_path = Path(filename)
        try:
            self.config_save_path.write_text(yaml_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return
        self._config_source_text = yaml_text
        self.config_dirty = False
        self.raw_dirty = False
        self.sections_baseline = deepcopy(self.sections)
        self._update_config_status()
        messagebox.showinfo("Configuration Saved", f"Saved to {self.config_save_path}")
    def _reset_config(self) -> None:
        self.sections = deepcopy(self.sections_baseline)
        names = [sec.get("displayName", sec["name"]) for sec in self.sections]
        self.section_list_var.set(names)
        if self.config_mode.get() == "visual":
            selection = self.section_listbox.curselection()
            index = selection[0] if selection else 0
            self.section_listbox.selection_clear(0, tk.END)
            if self.sections:
                self.section_listbox.selection_set(index)
            self._render_parameters(index)
        else:
            if self.enable_visual_editor:
                self._populate_raw_editor()
            else:
                source_text = self._config_source_text
                if source_text is None and self.config_save_path and self.config_save_path.exists():
                    try:
                        source_text = self.config_save_path.read_text(encoding="utf-8")
                    except OSError:
                        source_text = None
                if source_text is not None:
                    self.config_text.delete("1.0", "end")
                    self.config_text.insert("1.0", source_text)
                    self._refresh_config_highlight()
        self.config_dirty = False
        self.raw_dirty = False
        self._update_config_status()
    def _mark_snakefile_dirty(self) -> None:
        self.snakefile_dirty = True
        self.snakefile_status.configure(text="Unsaved changes")
    def _save_snakefile(self) -> None:
        content = self.snakefile_text.get("1.0", "end-1c")
        if not self.snakefile_save_path:
            filename = filedialog.asksaveasfilename(
                title="Save Snakefile",
                defaultextension=".smk",
                initialfile="Snakefile",
                filetypes=[("Snakefile", "Snakefile"), ("All files", "*.*")],
            )
            if not filename:
                return
            self.snakefile_save_path = Path(filename)
        try:
            self.snakefile_save_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return
        self.snakefile_dirty = False
        self.snakefile_status.configure(text=f"Saved to {self.snakefile_save_path.name}")
        messagebox.showinfo("Snakefile Saved", f"Saved to {self.snakefile_save_path}")
    def _reset_snakefile(self) -> None:
        self.snakefile_text.delete("1.0", "end")
        self.snakefile_text.insert("1.0", SNAKEFILE_TEMPLATE)
        self.snakefile_dirty = False
        self.snakefile_status.configure(text="Reset to template")
        self._refresh_snakefile_highlight()

    def _mark_advanced_dirty(self) -> None:
        self.advanced_dirty = True
        self.advanced_status.configure(text="Unsaved changes")

    def _save_advanced_settings(self) -> None:
        content = self.advanced_text.get("1.0", "end-1c")
        save_path = self.advanced_save_path
        if not save_path:
            initial_dir = CONFIG_ADVANCED_SETTINGS_PATH.parent if CONFIG_ADVANCED_SETTINGS_PATH.parent.exists() else CONFIGS_DIR
            filename = filedialog.asksaveasfilename(
                title="Save config_advanced_settings.yaml",
                defaultextension=".yaml",
                initialdir=str(initial_dir),
                initialfile="config_advanced_settings.yaml",
                filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
            )
            if not filename:
                return
            save_path = Path(filename)
            self.advanced_save_path = save_path
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return
        self._advanced_source_text = content
        self.advanced_dirty = False
        self.advanced_status.configure(text=f"Saved to {save_path.name}")
        messagebox.showinfo("config_advanced_settings.yaml Saved", f"Saved to {save_path}")

    def _reset_advanced_settings(self) -> None:
        self.advanced_text.delete("1.0", "end")
        self.advanced_text.insert("1.0", self._advanced_source_text)
        self.advanced_dirty = False
        self._refresh_advanced_highlight()
        if self.advanced_save_path and self._advanced_source_text:
            self.advanced_status.configure(text=f"Reverted to {self.advanced_save_path.name}")
        else:
            self.advanced_status.configure(text="Advanced settings cleared")
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
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
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
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
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
class RunTab(ttk.Frame):
    """Execution tab that runs real commands and streams output."""
    def __init__(self, master: tk.Widget, config_tab: ConfigurationTab, results_tab: ResultsTab):
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
            {"id": "spatial_data_prep", "name": "spatial_data_prep.py", "description": "Prepare spatial datasets"},
            {"id": "weather_data_prep", "name": "weather_data_prep.py", "description": "Download weather data"},
            {"id": "exclusion", "name": "exclusion.py", "description": "Run exclusion analysis"},
            {"id": "suitability", "name": "suitability.py", "description": "Perform resource grade modeling"},
            {"id": "weather_bias_adjust", "name": "weather_bias_adjust.py", "description": "Adjust weather data biases"},
            {"id": "energy_profiles", "name": "energy_profiles.py", "description": "Generate energy production profiles"},
        ]
        self.expected_output_dir: Optional[Path] = None
        self.last_run_script_id: Optional[str] = None
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
        ttk.Label(self.script_frame, text="Select script:").grid(row=0, column=0, sticky="w")
        script_names = [script["name"] for script in self.available_scripts]
        self.script_combo = ttk.Combobox(self.script_frame, values=script_names, state="readonly")
        self.script_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.script_combo.current(0)
        self.script_frame.columnconfigure(1, weight=1)
        self.script_combo.bind("<<ComboboxSelected>>", self._on_script_change)
        self.snakemake_options_frame = ttk.Frame(body)
        self.snakemake_options_frame.grid(row=1, column=0, sticky="ew", pady=10)
        self.snakemake_options_frame.columnconfigure(1, weight=1)
        ttk.Label(self.snakemake_options_frame, text="Snakefile:").grid(row=0, column=0, sticky="w")
        self.snakemake_file_display = ttk.Label(
            self.snakemake_options_frame,
            textvariable=self.snakemake_file_var,
            anchor="w",
            relief="sunken",
        )
        self.snakemake_file_display.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(self.snakemake_options_frame, text="Cores:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.snakemake_cores_display = ttk.Label(
            self.snakemake_options_frame,
            textvariable=self.snakemake_cores_var,
            width=6,
            relief="sunken",
            anchor="w",
        )
        self.snakemake_cores_display.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        self.info_label = ttk.Label(
            body,
            text="Runs all rules defined in the Snakefile",
            wraplength=500,
            foreground="#555555",
        )
        controls = ttk.Frame(body)
        controls.grid(row=3, column=0, sticky="ew", pady=10)
        controls.columnconfigure((0, 1, 2), weight=1)
        ttk.Button(controls, text="Run", command=self.handle_run).grid(row=0, column=0, sticky="ew", padx=4)
        ttk.Button(controls, text="Stop", command=self.handle_stop).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(controls, text="Reset", command=self.handle_reset).grid(row=0, column=2, sticky="ew", padx=4)
        progress_frame = ttk.Frame(body)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=10)
        ttk.Label(progress_frame, text="Progress").pack(anchor="w")
        self.progress_bar = ttk.Progressbar(progress_frame, maximum=100, variable=self.progress)
        self.progress_bar.pack(fill="x")
        status_frame = ttk.Frame(body)
        status_frame.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        status_frame.columnconfigure((0, 1, 2), weight=1)
        self.start_label = ttk.Label(status_frame, text="Started: --")
        self.start_label.grid(row=0, column=0, sticky="w")
        self.state_label = ttk.Label(status_frame, text="Status: Idle")
        self.state_label.grid(row=0, column=1, sticky="w")
        self.duration_label = ttk.Label(status_frame, text="Duration: --")
        self.duration_label.grid(row=0, column=2, sticky="w")
        log_frame = ttk.LabelFrame(body, text="Console Output")
        log_frame.grid(row=6, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=16, wrap="none", state="disabled", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        for tag, color in {
            "info": "#333333",
            "success": "#1a7f37",
            "warning": "#a66b00",
            "error": "#b42318",
        }.items():
            self.log_text.tag_configure(tag, foreground=color)
        body.rowconfigure(6, weight=1)
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
    def add_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n", level)
        self.log_text.configure(state="disabled")
        self.log_text.see("end")
    def _update_status_labels(self) -> None:
        self.status_badge.configure(text=f"Status: {self.status.capitalize()}")
        start_display = datetime.fromtimestamp(self.start_time).strftime("%H:%M:%S") if self.start_time else "--"
        self.start_label.configure(text=f"Started: {start_display}")
        duration_text = "--"
        if self.start_time:
            end = self.end_time or time.time()
            duration_text = f"{int(end - self.start_time)}s"
        self.duration_label.configure(text=f"Duration: {duration_text}")
        self.state_label.configure(text=f"Status: {self.status.capitalize()}")
    def _clear_logs(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
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
    def _start_spinner(self) -> None:
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
        raise FileNotFoundError(f"Could not find {script_name} in the expected locations.")
    def _load_snakemake_settings(self) -> Tuple[str, int]:
        default_snakefile = "Snakefile"
        default_cores = 4
        path = PARENT_DIR / "config_snakemake.yaml"
        if yaml is None or not path.exists():
            return default_snakefile, default_cores
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return default_snakefile, default_cores
        if not isinstance(data, dict):
            return default_snakefile, default_cores
        snakefile = str(data.get("snakefile", default_snakefile)).strip() or default_snakefile
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
        script = next((item for item in self.available_scripts if item["id"] == script_id), None)
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
        command = self._assemble_snakemake_command(str(snakefile_path), cores_value, snakemake_exec)
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
    def _cleanup_temp_snakefile(self) -> None:
        if self.temp_snakefile_path and self.temp_snakefile_path.exists():
            try:
                self.temp_snakefile_path.unlink()
            except OSError:
                pass
        self.temp_snakefile_path = None
    def _handle_process_output(self, level: str, message: str) -> None:
        tag = level if level in {"info", "error", "success"} else "info"
        self.add_log(tag, message)
    def _handle_process_exit(self, return_code: int) -> None:
        self.runner.cancel()
        self._stop_spinner()
        self._cancel_duration_timer()
        self.end_time = time.time()
        self._cleanup_temp_snakefile()
        if self.reset_requested:
            self._finalize_reset()
            return
        if return_code == 0 and not self.stop_requested:
            self.status = "completed"
            self.progress.set(100)
            self.add_log("success", "Process completed successfully.")
            self._update_results_tab_with_json()
            self._update_status_labels()
            messagebox.showinfo("Execution Complete", "Process finished successfully.")
        else:
            self.status = "error"
            self.progress.set(0)
            if self.stop_requested:
                self.add_log("error", f"Process exited with code {return_code} after stop request.")
                messagebox.showerror("Execution Stopped", f"Process exited with code {return_code} after stop request.")
            else:
                self.add_log("error", f"Process exited with code {return_code}.")
                messagebox.showerror("Execution Failed", f"Process exited with code {return_code}.")
            self._update_status_labels()
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
        self._update_status_labels()
        self.stop_requested = False
        self.reset_requested = False
    def handle_run(self) -> None:
        if self.runner.is_running():
            return
        self.expected_output_dir = None
        self.last_run_script_id = None
        mode = self.execution_mode.get()
        script_id: Optional[str] = None
        try:
            if mode == "snakemake":
                cmd, cwd, temp_path = self._build_snakemake_command()
                script_id = "snakemake"
            else:
                script_id = self.selected_script.get()
                cmd, cwd = self._build_single_command()
                temp_path = None
        except (FileNotFoundError, RuntimeError) as exc:
            message = str(exc)
            self.add_log("error", message)
            messagebox.showerror("Execution Error", message)
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
        self.start_time = time.time()
        self.end_time = None
        self._start_spinner()
        self._start_duration_timer()
        self.add_log("info", f"Starting process: {self._format_command(cmd)}")
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
            self.start_time = None
            self.end_time = None
            self.add_log("error", f"Failed to start process: {exc}")
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
        self.progress.set(0)
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
        self.layer_order = [tk.StringVar(value=str(i + 1)) for i in range(self.MAX_LAYERS)]
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
            ttk.Button(selection, text="Browse", command=lambda i=idx: self._browse(i)).grid(
                row=idx, column=2, padx=(6, 0), pady=2
            )
            ttk.Button(selection, text="Clear", command=lambda i=idx: self._clear(i)).grid(
                row=idx, column=3, padx=(6, 0), pady=2
            )
            ttk.Label(selection, text="Display Name:").grid(
                row=idx, column=4, sticky="e", padx=(12, 4)
            )
            ttk.Entry(selection, textvariable=self.layer_names[idx], width=18).grid(
                row=idx, column=5, sticky="ew", pady=2
            )
            ttk.Label(selection, text="Opacity:").grid(
                row=idx, column=6, sticky="e", padx=(12, 4)
            )
            ttk.Scale(selection, variable=self.layer_opacity[idx], from_=0.1, to=1.0, orient="horizontal").grid(
                row=idx, column=7, sticky="ew", pady=2
            )
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
        ttk.Button(buttons, text="Clear All", command=self._clear_all).pack(side="left", padx=(6, 0))

        self.status_label = ttk.Label(
            self, textvariable=self.status_var, wraplength=540, justify="left", foreground="#0d5d9b"
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
        legend_scroll = ttk.Scrollbar(legend_frame, orient="vertical", command=self.legend_text.yview)
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
            self._set_status("Select at least one layer before loading the map.", "warning")
            messagebox.showwarning("Load Map", "Select at least one layer before loading the map.")
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
                    png_path, bounds = geotiff_to_png_with_bounds(str(path), str(temp_dir))
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
                    raise ValueError("Unsupported file type. Choose .tif, .tiff, or .geojson.")
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
            self._set_status(f"Loaded {len(layers)} layer(s) in the embedded map.", "success")
        else:
            self._set_status(
                f"Loaded {len(layers)} layer(s). The map opened in your browser.", "warning"
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
        self.run_button = ttk.Button(controls, text="Run results_analysis.py", command=self.handle_run)
        self.run_button.grid(row=0, column=0, padx=(0, 6))
        self.stop_button = ttk.Button(controls, text="Stop", command=self.handle_stop, state="disabled")
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
        self.log_text = tk.Text(log_frame, height=8, wrap="none", state="disabled", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
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
        aggregated_scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.aggregated_tree.yview)
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
        self.delete_run_button = ttk.Button(controls, text="Run delete_scenario_results.py", command=self.handle_delete_run)
        self.delete_run_button.grid(row=0, column=0, padx=(0, 6))
        self.delete_stop_button = ttk.Button(controls, text="Stop", command=self.handle_delete_stop, state="disabled")
        self.delete_stop_button.grid(row=0, column=1, padx=(0, 6))
        self.delete_status_label = ttk.Label(controls, text="Status: Idle")
        self.delete_status_label.grid(row=0, column=2, sticky="w")

        log_frame = ttk.LabelFrame(frame, text="Script Output")
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.delete_log_text = tk.Text(log_frame, height=14, wrap="none", state="disabled", font=("Consolas", 10))
        self.delete_log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.delete_log_text.yview)
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
        ttk.Label(input_row, text="Send Input:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.delete_input_entry = ttk.Entry(input_row, textvariable=self.delete_input_var, state="disabled")
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
        raise FileNotFoundError(f"Could not find {script_name} in the expected locations.")
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
            status, message, _ = self.display_aggregated_json(self._resolve_results_json_path())
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
                self._append_log("warning", f"Process exited with code {return_code} after stop request.")
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
            values = [self._format_aggregated_value(row.get(col)) for col in self.aggregated_columns]
            self.aggregated_tree.insert("", "end", values=values)
    def _update_delete_status(self) -> None:
        if self.delete_status_label:
            self.delete_status_label.configure(text=f"Status: {self.delete_status.capitalize()}")
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
        self._delete_append_log("info", f"Starting process: {self._format_command(command)}")
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
        self._delete_append_log("warning", "Stop requested. Waiting for process to exit...")
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
                self._delete_append_log("warning", f"Process exited with code {return_code} after stop request.")
                self.delete_status = "stopped"
            else:
                self._delete_append_log("error", f"Process exited with code {return_code}.")
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
    def display_aggregated_json(self, json_path: Optional[Path] = None) -> Tuple[str, str, int]:
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
            return ("error", f"Failed to load aggregated results from {resolved}: {exc}", 0)
        rows = self._normalise_aggregated_rows(payload)
        if not rows:
            self.clear_aggregated_results()
            return ("empty", f"No aggregated entries found in {resolved}", 0)
        self._set_aggregated_rows(rows)
        return ("success", f"Loaded {len(rows)} rows from {resolved}", len(rows))
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
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Python Script Manager", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(header, text="Reload UI", command=self.reload_ui).grid(row=0, column=1, sticky="e")

        self.notebook = ttk.Notebook(outer)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self._build_tabs()

    def _build_tabs(self) -> None:
        self.notebook_tabs = []
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

    def reload_ui(self) -> None:
        current_index = self.notebook.index(self.notebook.select()) if self.notebook.tabs() else 0
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

