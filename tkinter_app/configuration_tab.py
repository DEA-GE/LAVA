"""Configuration editing, YAML conversion, and validation UI."""

from __future__ import annotations

import ast
import json
import re
import sys
import tkinter as tk
import webbrowser
from collections.abc import Mapping as MappingABC
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from ruamel.yaml.comments import CommentedMap, CommentedSeq

if __package__:
    from .data_loader import (
        CONFIG_SNAKEMAKE_STAGE_FLAGS, GADM_SOURCE_OPTIONS, INPUT_AREA_OPTIONS,
        LANDCOVER_SOURCE_OPTIONS, OSM_SOURCE_OPTIONS, POPULATION_SOURCE_OPTIONS,
        PROTECTED_AREAS_SOURCE_OPTIONS, WEATHER_DATA_EXTEND_OPTIONS, cast_value,
        load_custom_study_area_names, load_offshore_sections,
        load_onshore_sections, load_snakemake_sections, load_solar_sections,
        round_trip_available, save_mapping_round_trip, save_sections_round_trip,
        stringify_list_value, validate_configuration_documents,
    )
    from .flag_mapper import make_path, ui_bool_to_numeric, yaml_numeric_to_ui_bool
    from .widgets import TextSyntaxHighlighter, Tooltip
else:
    from data_loader import (  # type: ignore
        CONFIG_SNAKEMAKE_STAGE_FLAGS, GADM_SOURCE_OPTIONS, INPUT_AREA_OPTIONS,
        LANDCOVER_SOURCE_OPTIONS, OSM_SOURCE_OPTIONS, POPULATION_SOURCE_OPTIONS,
        PROTECTED_AREAS_SOURCE_OPTIONS, WEATHER_DATA_EXTEND_OPTIONS, cast_value,
        load_custom_study_area_names, load_offshore_sections,
        load_onshore_sections, load_snakemake_sections, load_solar_sections,
        round_trip_available, save_mapping_round_trip, save_sections_round_trip,
        stringify_list_value, validate_configuration_documents,
    )
    from flag_mapper import make_path, ui_bool_to_numeric, yaml_numeric_to_ui_bool  # type: ignore
    from widgets import TextSyntaxHighlighter, Tooltip  # type: ignore

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
CONFIGS_DIR = PARENT_DIR / "configs"
CONFIG_ADVANCED_SETTINGS_PATH = CONFIGS_DIR / "advanced_settings" / "advanced_data_prep_settings.yaml"
SNAKEMAKE_GLOBAL_PATH = PARENT_DIR / "snakemake" / "Snakefile"
SNAKEFILE_TEMPLATE = """"""
SNAKEMAKE_STAGE_KEYS = [stage["key"] for stage in CONFIG_SNAKEMAKE_STAGE_FLAGS]
CONFIGURATION_CATEGORIES = (
    "General", "Technology exclusions", "Suitability", "Workflow",
    "Advanced settings", "Snakefile",
)
DOCUMENT_CATEGORIES = {
    "config.yaml": "General", "onshorewind.yaml": "Technology exclusions",
    "solar.yaml": "Technology exclusions", "offshorewind.yaml": "Technology exclusions",
    "suitability.yaml": "Suitability", "config_snakemake.yaml": "Workflow",
    "advanced_data_prep_settings.yaml": "Advanced settings", "Snakefile": "Snakefile",
}
PARAMETER_CHOICES: Dict[str, List[str]] = {
    "GADM_source": list(GADM_SOURCE_OPTIONS), "landcover_source": list(LANDCOVER_SOURCE_OPTIONS),
    "OSM_source": list(OSM_SOURCE_OPTIONS), "population_source": list(POPULATION_SOURCE_OPTIONS),
    "protected_areas_source": list(PROTECTED_AREAS_SOURCE_OPTIONS),
    "input_area": list(INPUT_AREA_OPTIONS), "weather_data_extend": list(WEATHER_DATA_EXTEND_OPTIONS),
    "technology": ["onshorewind", "solar", "offshorewind"],
}
PARAMETER_PICKERS: Dict[str, str] = {
    "custom_study_area_filename": "custom_study_area_file",
    "landcover_filename": "filename",
    "DEM_filename": "filename", "buildings_filename": "filename",
    "protected_areas_filename": "filename",
    "forest_density_filename": "filename", "model_areas_filename": "filename",
    "weather_data_extend": "filename", "weather_external_data_path": "directory",
    "additional_exclusion_polygons_folder_name": "folder_name",
    "additional_exclusion_rasters_folder_name": "folder_name",
    "OSM_folder_name": "folder_name", "snakefile": "project_file",
}
PARAMETER_UNITS: Dict[str, str] = {
    "deployment_density": "MW/km2", "resolution_manual": "m", "resolution_landcover": "degrees",
    "max_elevation": "m", "max_slope": "degrees", "max_buildings_footprint": "sqm",
    "buildings_buffer": "m", "max_population": "people/pixel", "max_forest_density": "%",
    "railways_buffer": "m",
    "roads_buffer": "m", "airports_buffer": "m", "waterbodies_buffer": "m",
    "military_buffer": "m", "coastlines_buffer": "m", "protectedAreas_buffer": "m",
    "transmission_lines_buffer": "m", "generators_buffer": "m", "plants_buffer": "m",
    "substations_inclusion_buffer": "m", "transmission_inclusion_buffer": "m",
    "roads_inclusion_buffer": "m", "min_wind_speed": "m/s", "max_wind_speed": "m/s",
    "min_solar_production": "kWh/kW/year", "max_solar_production": "kWh/kW/year",
    "min_area_distributed": "km2", "min_area_rg": "km2", "weather_year": "year",
    "population_year": "year",
}


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


def _mousewheel_scroll_units(event: tk.Event) -> int:
    """Translate a cross-platform mouse-wheel event into canvas scroll units."""
    button = getattr(event, "num", None)
    if button == 4:
        return -1
    if button == 5:
        return 1

    delta = int(getattr(event, "delta", 0) or 0)
    if delta == 0:
        return 0
    if sys.platform == "darwin":
        return -1 if delta > 0 else 1
    steps = max(1, abs(delta) // 120)
    return -steps if delta > 0 else steps




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
            elif value_type in {"integer", "source", "nullable_string"}:
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
        self.expand_validation_button = ttk.Button(
            validation_frame,
            text="Open larger...",
            command=self._show_validation_results_dialog,
            state="disabled",
        )
        self.expand_validation_button.grid(
            row=0, column=3, sticky="e", padx=(6, 0)
        )
        ttk.Label(
            validation_frame,
            text="Errors block saving and running; warnings are advisory.",
            foreground="#555555",
            wraplength=980,
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(3, 0))
        self.validation_results_frame = ttk.Frame(validation_frame)
        self.validation_results_frame.grid(
            row=2, column=0, columnspan=4, sticky="ew", pady=(5, 0)
        )
        self.validation_results_frame.columnconfigure(0, weight=1)
        self.validation_tree = ttk.Treeview(
            self.validation_results_frame,
            columns=("severity", "file", "setting", "message"),
            show="headings",
            height=2,
        )
        for column, heading, width in (
            ("severity", "Level", 70),
            ("file", "File", 135),
            ("setting", "Setting", 180),
            ("message", "Issue", 620),
        ):
            self.validation_tree.heading(column, text=heading)
            self.validation_tree.column(column, width=width, anchor="w")
        self.validation_tree.grid(row=0, column=0, sticky="ew")
        validation_scroll_y = ttk.Scrollbar(
            self.validation_results_frame,
            orient="vertical",
            command=self.validation_tree.yview,
        )
        validation_scroll_y.grid(row=0, column=1, sticky="ns")
        validation_scroll_x = ttk.Scrollbar(
            self.validation_results_frame,
            orient="horizontal",
            command=self.validation_tree.xview,
        )
        validation_scroll_x.grid(row=1, column=0, sticky="ew")
        self.validation_tree.configure(
            yscrollcommand=validation_scroll_y.set,
            xscrollcommand=validation_scroll_x.set,
        )
        self.validation_tree.bind("<Double-1>", self._on_validation_issue_open)
        self.validation_tree.bind("<Return>", self._on_validation_issue_open)
        self.validation_results_frame.grid_remove()
        self.save_summary_status = ttk.Label(
            validation_frame, text="", foreground="#2E6B3A"
        )
        self.save_summary_status.grid(
            row=3, column=0, columnspan=4, sticky="e", pady=(3, 0)
        )
        self.save_summary_status.grid_remove()

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
        param_window = self.param_canvas.create_window(
            (0, 0), window=self.param_inner, anchor="nw"
        )
        self.param_canvas.bind(
            "<Configure>",
            lambda event: self.param_canvas.itemconfigure(
                param_window, width=event.width
            ),
        )
        self._enable_mousewheel(self.param_canvas)
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
            selectbackground="#315A85",
            selectforeground="#FFFFFF",
            inactiveselectbackground="#4A6782",
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
            self.validation_results_frame.grid_remove()
            self.expand_validation_button.configure(state="disabled")
            return
        self.validation_status.configure(
            text=(
                f"Validated at {validated_at} — {errors} error(s), {warnings} warning(s); "
                "double-click an issue to open it"
            ),
            foreground="#B42318" if errors else "#8A5A00",
        )
        self.validation_tree.configure(
            height=max(1, min(2, len(self.validation_issues)))
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
        self.validation_results_frame.grid()
        self.expand_validation_button.configure(state="normal")

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

    def _show_validation_results_dialog(self) -> None:
        if not self.validation_issues:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Configuration Validation Results")
        dialog.geometry("1050x520")
        dialog.minsize(760, 360)
        dialog.transient(self.winfo_toplevel())
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        errors = sum(
            issue.get("severity") == "error" for issue in self.validation_issues
        )
        warnings = sum(
            issue.get("severity") == "warning" for issue in self.validation_issues
        )
        ttk.Label(
            dialog,
            text=f"{errors} error(s), {warnings} warning(s)",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        results_frame = ttk.Frame(dialog)
        results_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        results_tree = ttk.Treeview(
            results_frame,
            columns=("severity", "file", "setting", "message"),
            show="headings",
        )
        for column, heading, width, stretch in (
            ("severity", "Level", 80, False),
            ("file", "File", 170, False),
            ("setting", "Setting", 210, False),
            ("message", "Issue", 560, True),
        ):
            results_tree.heading(column, text=heading)
            results_tree.column(column, width=width, anchor="w", stretch=stretch)
        results_tree.grid(row=0, column=0, sticky="nsew")
        results_scroll_y = ttk.Scrollbar(
            results_frame, orient="vertical", command=results_tree.yview
        )
        results_scroll_y.grid(row=0, column=1, sticky="ns")
        results_scroll_x = ttk.Scrollbar(
            results_frame, orient="horizontal", command=results_tree.xview
        )
        results_scroll_x.grid(row=1, column=0, sticky="ew")
        results_tree.configure(
            yscrollcommand=results_scroll_y.set,
            xscrollcommand=results_scroll_x.set,
        )
        results_tree.tag_configure("error", foreground="#B42318")
        results_tree.tag_configure("warning", foreground="#8A5A00")
        dialog_items: Dict[str, Dict[str, str]] = {}
        for issue in self.validation_issues:
            item = results_tree.insert(
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
            dialog_items[item] = issue

        def _open_selected(_event: Optional[tk.Event] = None) -> None:
            selected = results_tree.selection()
            if not selected:
                return
            issue = dialog_items.get(selected[0])
            if issue is None:
                return
            dialog.destroy()
            self._open_validation_issue(issue)

        results_tree.bind("<Double-1>", _open_selected)
        results_tree.bind("<Return>", _open_selected)
        footer = ttk.Frame(dialog)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        ttk.Label(
            footer,
            text="Double-click an issue to open the affected setting.",
            foreground="#555555",
        ).pack(side="left")
        ttk.Button(footer, text="Close", command=dialog.destroy).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        results_tree.focus_set()

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
            excluded = {"config", "snakemake", "config_snakemake", "suitability"}
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

    def _study_area_choices(self, current_value: Any = None) -> List[str]:
        choices = load_custom_study_area_names()
        for item in self._coerce_sequence_value(current_value):
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
        custom_study_area_root = PARENT_DIR / "Raw_Spatial_Data" / "custom_study_area"
        initial_dir = (
            custom_study_area_root
            if picker == "custom_study_area_file"
            else PARENT_DIR
        )
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
        if picker == "custom_study_area_file":
            try:
                relative_path = selected_path.resolve().relative_to(
                    custom_study_area_root.resolve()
                )
            except ValueError:
                messagebox.showerror(
                    "Custom study area",
                    "Select a GeoJSON inside a collection folder under:\n"
                    f"{custom_study_area_root}",
                    parent=self,
                )
                return
            if relative_path.parent == Path("."):
                messagebox.showerror(
                    "Custom study area",
                    "Place the GeoJSON in a named collection folder below:\n"
                    f"{custom_study_area_root}",
                    parent=self,
                )
                return
            rendered = relative_path.as_posix()
        elif picker in {"filename", "folder_name"}:
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
        editable_choices: bool = False,
    ) -> Tuple[ttk.Frame, tk.Listbox]:
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        current = self._coerce_sequence_value(value)
        available = list(choices or [])
        for item in current:
            text = str(item)
            if text not in available:
                available.append(text)
        choice_mode = bool(choices) and not editable_choices
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
        list_scroll = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
        list_scroll.grid(row=0, column=3, sticky="ns")
        listbox.configure(yscrollcommand=list_scroll.set)

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
            if editable_choices:
                add_entry = ttk.Combobox(
                    frame,
                    textvariable=add_var,
                    values=available,
                    state="normal",
                )
            else:
                add_entry = ttk.Entry(frame, textvariable=add_var)
            add_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))

            def add_item() -> None:
                text = add_var.get().strip()
                existing = {
                    str(listbox.get(index)) for index in range(listbox.size())
                }
                if text and text not in existing:
                    listbox.insert("end", text)
                    add_var.set("")
                    emit_selection()

            def remove_selected() -> None:
                for index in reversed(listbox.curselection()):
                    listbox.delete(index)
                emit_selection()

            def add_all_items() -> None:
                existing = {
                    str(listbox.get(index)) for index in range(listbox.size())
                }
                for item in available:
                    text = str(item).strip()
                    if text and text not in existing:
                        listbox.insert("end", text)
                        existing.add(text)
                emit_selection()

            ttk.Button(frame, text="Add", command=add_item).grid(
                row=1, column=1, padx=(4, 0), pady=(4, 0)
            )
            ttk.Button(frame, text="Remove", command=remove_selected).grid(
                row=1, column=2, padx=(4, 0), pady=(4, 0)
            )
            if editable_choices:
                ttk.Button(frame, text="Add all", command=add_all_items).grid(
                    row=1, column=3, padx=(4, 0), pady=(4, 0)
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
        scroll_canvas = info.get("visual_canvas")
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
                    mapping_frame = ttk.LabelFrame(
                        section_frame, text=label_text, padding=(8, 6)
                    )
                    mapping_frame.pack(fill="x", padx=6, pady=(3, 7))
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

                row = ttk.LabelFrame(
                    section_frame, text=label_text, padding=(8, 6)
                )
                row.pack(fill="x", pady=(3, 7), padx=6)
                row.columnconfigure(0, weight=1)
                if desc_text:
                    self._attach_tooltip(row, desc_text)
                if param_type == "boolean":
                    var = tk.BooleanVar(value=bool(param.get("value")))
                    ctrl_info["var"] = var
                    widget = ttk.Checkbutton(
                        row,
                        variable=var,
                        command=lambda name=label: self._on_extra_param_changed(name),
                    )
                    widget.grid(row=0, column=0, sticky="w")
                    ctrl_info["widget"] = widget
                elif param_type == "array" and self._is_simple_sequence(
                    param.get("value")
                ):
                    editable_choices = False
                    if param["key"] == "technologies":
                        choices = self._choices_for_parameter(
                            param["key"], param.get("value")
                        )
                    elif (
                        label == "config_snakemake.yaml"
                        and param["key"] == "study_region_name"
                    ):
                        choices = self._study_area_choices(param.get("value"))
                        editable_choices = True
                    else:
                        choices = None
                    editor, listbox = self._create_list_editor(
                        row,
                        param.get("value"),
                        lambda values, name=label, parameter=param: (
                            self._on_extra_list_changed(name, parameter, values)
                        ),
                        choices=choices,
                        editable_choices=editable_choices,
                    )
                    editor.grid(row=0, column=0, sticky="ew")
                    widget = listbox
                    ctrl_info["widget"] = listbox
                    ctrl_info["listbox"] = listbox
                    ctrl_info["list_choice_mode"] = (
                        bool(choices) and not editable_choices
                    )
                elif param_type == "array":
                    widget = tk.Text(row, height=3, width=32, wrap="word")
                    value = param.get("value")
                    if isinstance(value, (list, dict)):
                        display = json.dumps(value, ensure_ascii=False, indent=2)
                    else:
                        display = "" if value is None else str(value)
                    widget.insert("1.0", display)
                    widget.grid(row=0, column=0, sticky="w")
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
                    input_frame.grid(row=0, column=0, sticky="ew")
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
                        if scroll_canvas is not None:
                            self._redirect_mousewheel_to_canvas(widget, scroll_canvas)
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
                        if scroll_canvas is not None:
                            self._redirect_mousewheel_to_canvas(widget, scroll_canvas)
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
                    help_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
                    if desc_text:
                        help_label = ttk.Label(
                            help_frame,
                            text=self._short_help_text(desc_text),
                            wraplength=700,
                            justify="left",
                        )
                        help_label.pack(anchor="w")
                        self._attach_tooltip(help_label, desc_text)
                    if comment_hint:
                        ttk.Label(
                            help_frame,
                            text=format_yaml_comment_hint(comment_hint),
                            foreground="#5B4A00",
                            wraplength=700,
                            justify="left",
                        ).pack(anchor="w", pady=(2, 0))
                    for issue in inline_issues:
                        ttk.Label(
                            help_frame,
                            text=f"{issue['severity'].title()}: {issue['message']}",
                            foreground=self._issue_colour(issue["severity"]),
                            wraplength=700,
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
            elif param_type == "nullable_string":
                var = ctrl.get("var")
                param["value"] = cast_value(
                    "nullable_string", "" if var is None else var.get()
                )
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
                elif param_type in {"integer", "source", "nullable_string"}:
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
        technologies = [
            str(item)
            for item in self._coerce_sequence_value(flat.get("technologies", []))
            if str(item).strip()
        ]
        scenarios = [
            str(item).strip()
            for item in self._coerce_sequence_value(flat.get("scenarios", []))
            if str(item).strip()
        ]
        raw_technology_scenarios = flat.get("technology_scenarios", {})
        technology_scenarios: Dict[str, List[str]] = {}
        if isinstance(raw_technology_scenarios, MappingABC):
            for technology, selected in raw_technology_scenarios.items():
                technology_name = str(technology).strip()
                scenario_names = [
                    str(item).strip()
                    for item in self._coerce_sequence_value(selected)
                    if str(item).strip()
                ]
                if technology_name:
                    technology_scenarios[technology_name] = scenario_names
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
            "technologies": technologies,
            "technology_scenarios": technology_scenarios,
            "scenarios": scenarios,
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
            f"technologies: {technologies}\n"
            f"technology_scenarios: {data['technology_scenarios']}\n"
            f"scenarios: {data['scenarios']}\n"
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
            "technologies": self._coerce_sequence_value(data.get("technologies", [])),
            "scenarios": self._coerce_sequence_value(data.get("scenarios", [])),
            "technology_scenarios": data.get("technology_scenarios", {}),
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
                elif param_type == "mapping":
                    parsed_mapping = cast_value("mapping", value)
                    param["value"] = (
                        parsed_mapping
                        if isinstance(parsed_mapping, MappingABC)
                        else {}
                    )
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
            self.save_summary_status.grid_remove()
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
            self.save_summary_status.grid()

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
                        save_path,
                        structured_content,
                        remove_keys=("scenario",),
                        replace_keys=("technology_scenarios",),
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
        self.param_inner.columnconfigure(0, weight=1)
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
                frame = ttk.LabelFrame(
                    self.param_inner, text=key, padding=(8, 6)
                )
                frame.grid(
                    row=row_pointer,
                    column=0,
                    columnspan=2,
                    sticky="ew",
                    padx=(0, 10),
                    pady=(3, 7),
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
            setting_frame = ttk.LabelFrame(
                self.param_inner, text=key, padding=(8, 6)
            )
            setting_frame.grid(
                row=row_pointer,
                column=0,
                columnspan=3,
                sticky="ew",
                padx=(0, 10),
                pady=(3, 7),
            )
            setting_frame.columnconfigure(0, weight=1)
            if description:
                self._attach_tooltip(setting_frame, description)
            if value_type == "boolean":
                var = tk.BooleanVar(value=bool(param.get("value")))
                widget = ttk.Checkbutton(
                    setting_frame,
                    variable=var,
                    command=lambda idx=idx: self._on_param_toggle(section_index, idx),
                )
                widget.grid(row=0, column=0, sticky="w")
                self.param_vars[(section_index, idx)] = var
            elif value_type == "array" and self._is_simple_sequence(param.get("value")):
                choices = (
                    self._choices_for_parameter(key, param.get("value"))
                    if key == "technologies"
                    else None
                )
                editor, listbox = self._create_list_editor(
                    setting_frame,
                    param.get("value"),
                    lambda values, s_index=section_index, p_index=idx: (
                        self._on_list_param_change(s_index, p_index, values)
                    ),
                    choices=choices,
                )
                editor.grid(row=0, column=0, sticky="ew")
                widget = listbox
                self.param_vars[(section_index, idx)] = listbox
            elif value_type == "array":
                widget = tk.Text(setting_frame, height=4, width=40, wrap="word")
                current_value = param.get("value")
                if isinstance(current_value, (list, dict)):
                    display_text = json.dumps(
                        current_value, ensure_ascii=False, indent=2
                    )
                else:
                    display_text = "" if current_value is None else str(current_value)
                widget.insert("1.0", display_text)
                widget.grid(row=0, column=0, sticky="ew")
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
                control_frame = ttk.Frame(setting_frame)
                control_frame.grid(row=0, column=0, sticky="ew")
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
                    self._redirect_mousewheel_to_canvas(widget, self.param_canvas)
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
                    self._redirect_mousewheel_to_canvas(widget, self.param_canvas)
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
                help_frame = ttk.Frame(setting_frame)
                help_frame.grid(
                    row=1, column=0, sticky="ew", pady=(6, 0)
                )
                if description:
                    help_label = ttk.Label(
                        help_frame,
                        text=self._short_help_text(description),
                        foreground="#555555",
                        wraplength=700,
                        justify="left",
                    )
                    help_label.pack(anchor="w")
                    self._attach_tooltip(help_label, description)
                if comment_hint:
                    ttk.Label(
                        help_frame,
                        text=format_yaml_comment_hint(comment_hint),
                        foreground="#5B4A00",
                        wraplength=700,
                        justify="left",
                    ).pack(anchor="w", pady=(2, 0))
                for issue in inline_issues:
                    ttk.Label(
                        help_frame,
                        text=f"{issue['severity'].title()}: {issue['message']}",
                        foreground=self._issue_colour(issue["severity"]),
                        wraplength=700,
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
        elif value_type == "nullable_string":
            value = cast_value("nullable_string", raw_value)
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
        def _on_mousewheel(event):
            units = _mousewheel_scroll_units(event)
            if units:
                canvas.yview_scroll(units, "units")

        # Bindings for Windows/macOS
        canvas.bind(
            "<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel)
        )
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Bindings for Linux (X11)
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

    @staticmethod
    def _redirect_mousewheel_to_canvas(
        widget: tk.Widget, canvas: tk.Canvas
    ) -> None:
        """Scroll the pane without letting input widgets alter their values."""

        def _on_mousewheel(event: tk.Event) -> str:
            units = _mousewheel_scroll_units(event)
            if units:
                canvas.yview_scroll(units, "units")
            return "break"

        widget.bind("<MouseWheel>", _on_mousewheel, add="+")
        widget.bind("<Button-4>", _on_mousewheel, add="+")
        widget.bind("<Button-5>", _on_mousewheel, add="+")
