"""Tkinter-based translation of the Python Script Manager interface."""
from __future__ import annotations
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
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
SNAKEMAKE_GLOBAL_PATH = PARENT_DIR / "snakemake"/ "Snakefile_global"
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))
if str(PARENT_DIR) not in sys.path:
    sys.path.append(str(PARENT_DIR))
from flag_mapper import make_path, ui_bool_to_numeric, yaml_numeric_to_ui_bool  # type: ignore  # noqa: E402
from data_loader import (  # type: ignore  # noqa: E402
    DEFAULT_RESULTS_DATA,
    load_initial_sections,
    load_onshore_sections,
    load_solar_sections,
    load_config_snakemake_sections,
    load_sample_results,
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
            value = param.get("value")
            if param.get("type") == "boolean":
                value = ui_bool_to_numeric(path, bool(value))
            if isinstance(value, bool):
                value_str = "true" if value else "false"
            elif param.get("type") == "array":
                value_str = str(value)
            elif isinstance(value, str):
                escaped = value.replace('"', '\\"')
                value_str = f'"{escaped}"'
            else:
                value_str = str(value)
            lines.append(f"  {param['key']}: {value_str}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
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
                try:
                    param["value"] = float(raw_value)
                except (TypeError, ValueError):
                    param["value"] = 0.0
            elif value_type == "array":
                if isinstance(raw_value, (list, dict)):
                    param["value"] = json.dumps(raw_value)
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
        self.config_dirty = False
        self.snakefile_dirty = False
        self.raw_dirty = False
        self.enable_visual_editor = True
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.config_mode = tk.StringVar(value="visual")
        self.param_vars: Dict[Tuple[int, int], tk.Variable] = {}
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
        else:
            self._populate_raw_editor()
        self._update_config_status()
    def _load_additional_files(self) -> Dict[str, Dict[str, Any]]:
        entries: Dict[str, Dict[str, Any]] = {}
        specs = [
            ("onshorewind.yaml", ("onshorewind.yaml",), load_onshore_sections, "generic"),
            ("solar.yaml", ("solar.yaml",), load_solar_sections, "generic"),
            ("config_snakemake.yaml", ("config_snakemake.yaml",), load_config_snakemake_sections, "config_snakemake"),
        ]
        for label, candidates, section_loader, kind in specs:
            existing_path: Optional[Path] = None
            content = ""
            expected_path = PARENT_DIR / candidates[0]
            for name in candidates:
                candidate = PARENT_DIR / name
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
                "save_path": expected_path,
                "expected_path": expected_path,
                "sections": sections,
                "mode_var": None,
                "visual_frame": None,
                "raw_frame": None,
                "param_controls": [],
                "kind": kind,
            }
        return entries
    def _build_raw_extra_editor(self, label: str, info: Dict[str, Any], parent: tk.Widget) -> None:
        text_widget = tk.Text(parent, wrap="none", font=("Courier New", 10))
        text_widget.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        text_widget.insert("1.0", info.get("baseline", ""))
        text_widget.bind("<KeyRelease>", lambda _event, name=label: self._mark_extra_dirty(name))
        scroll_y = ttk.Scrollbar(parent, orient="vertical", command=text_widget.yview)
        scroll_y.grid(row=0, column=1, sticky="ns", pady=10)
        text_widget.configure(yscrollcommand=scroll_y.set)
        scroll_x = ttk.Scrollbar(parent, orient="horizontal", command=text_widget.xview)
        scroll_x.grid(row=1, column=0, sticky="ew", padx=10)
        text_widget.configure(xscrollcommand=scroll_x.set)
        buttons = ttk.Frame(parent)
        buttons.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        if info["path"]:
            status_text = f"Loaded from {info['path'].name}"
        else:
            status_text = f"New file (will save to {info['expected_path'].name})"
        status_label = ttk.Label(buttons, text=status_text)
        status_label.pack(side="left", padx=(0, 10))
        ttk.Button(buttons, text="Discard Changes", command=lambda name=label: self._reset_extra_file(name)).pack(
            side="right", padx=6
        )
        ttk.Button(buttons, text="Save", command=lambda name=label: self._save_extra_file(name)).pack(side="right")
        info["text_widget"] = text_widget
        info["status_label"] = status_label
    def _build_structured_extra_editor(self, label: str, info: Dict[str, Any], parent: tk.Widget) -> None:
        parent.rowconfigure(1, weight=1)
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
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
        visual_frame = ttk.Frame(parent)
        visual_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        visual_frame.columnconfigure(0, weight=1)
        info["visual_frame"] = visual_frame
        raw_frame = ttk.Frame(parent)
        raw_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        info["raw_frame"] = raw_frame
        text_widget = tk.Text(raw_frame, wrap="none", font=("Courier New", 10))
        text_widget.grid(row=0, column=0, sticky="nsew")
        raw_frame.rowconfigure(0, weight=1)
        raw_frame.columnconfigure(0, weight=1)
        baseline = info.get("baseline") or self._serialize_sections_for_kind(info.get("kind"), info.get("sections"))
        text_widget.insert("1.0", baseline)
        text_widget.bind("<KeyRelease>", lambda _event, name=label: self._mark_extra_dirty(name))
        info["text_widget"] = text_widget
        scroll_y = ttk.Scrollbar(raw_frame, orient="vertical", command=text_widget.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        text_widget.configure(yscrollcommand=scroll_y.set)
        scroll_x = ttk.Scrollbar(raw_frame, orient="horizontal", command=text_widget.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        text_widget.configure(xscrollcommand=scroll_x.set)
        buttons = ttk.Frame(parent)
        buttons.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        status_text = f"Loaded from {info['path'].name}" if info["path"] else f"New file (will save to {info['expected_path'].name})"
        status_label = ttk.Label(buttons, text=status_text)
        status_label.pack(side="left", padx=(0, 10))
        info["status_label"] = status_label
        ttk.Button(buttons, text="Discard Changes", command=lambda name=label: self._reset_extra_file(name)).pack(
            side="right", padx=6
        )
        ttk.Button(buttons, text="Save", command=lambda name=label: self._save_extra_file(name)).pack(side="right")
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
            section_frame.pack(fill="x", pady=5)
            for p_index, param in enumerate(section.get("parameters", [])):
                row = ttk.Frame(section_frame)
                row.pack(fill="x", pady=2, padx=6)
                ttk.Label(row, text=param.get("description") or param["key"]).pack(side="left")
                param_type = param.get("type", "string")
                ctrl_info: Dict[str, Any] = {
                    "section_index": s_index,
                    "param_index": p_index,
                    "param": param,
                    "type": param_type,
                }
                if param_type == "boolean":
                    var = tk.BooleanVar(value=bool(param.get("value")))
                    ctrl_info["var"] = var
                    widget = ttk.Checkbutton(
                        row,
                        variable=var,
                        command=lambda name=label: self._on_extra_param_changed(name),
                    )
                    widget.pack(side="right")
                elif param_type == "array":
                    widget = tk.Text(row, height=4, width=60, wrap="word")
                    value = param.get("value")
                    if isinstance(value, (list, dict)):
                        display = json.dumps(value, ensure_ascii=False, indent=2)
                    else:
                        display = "" if value is None else str(value)
                    widget.insert("1.0", display)
                    widget.pack(side="right", fill="x", expand=True)
                    widget.bind(
                        "<KeyRelease>",
                        lambda _event, name=label: self._on_extra_param_changed(name),
                    )
                    ctrl_info["widget"] = widget
                else:
                    value = "" if param.get("value") is None else str(param.get("value"))
                    var = tk.StringVar(value=value)
                    ctrl_info["var"] = var
                    entry = ttk.Entry(row, textvariable=var, width=40)
                    entry.pack(side="right", fill="x", expand=True)
                    var.trace_add("write", lambda *_args, name=label: self._on_extra_param_changed(name))
                    ctrl_info["widget"] = entry
                info["param_controls"].append(ctrl_info)
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
                        param["value"] = 0
                    else:
                        try:
                            numeric = float(text)
                        except ValueError:
                            numeric = 0.0
                        param["value"] = int(numeric) if numeric.is_integer() else numeric
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
        visual_frame = info.get("visual_frame")
        raw_frame = info.get("raw_frame")
        if mode == "visual":
            if raw_frame is not None:
                raw_frame.grid_remove()
            if not initial:
                if not self._sync_extra_text_to_visual(label):
                    mode_var.set("raw")
                    return
            if visual_frame is not None:
                visual_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        else:
            if visual_frame is not None:
                visual_frame.grid_remove()
            self._sync_extra_visual_to_text(label)
            if raw_frame is not None:
                raw_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
    def _extra_sections_to_yaml(self, sections: Optional[List[Dict[str, Any]]]) -> str:
        data: Dict[str, Any] = {}
        if not sections:
            return ""
        for section in sections:
            for param in section.get("parameters", []):
                data[param["key"]] = param.get("value")
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
        try:
            cores_value = int(flat.get("cores", 4))
        except (TypeError, ValueError):
            cores_value = 4
        snakefile_value = str(flat.get("snakefile", "snakemake_global")).strip() or "snakemake_global"
        data = {
            "snakefile": snakefile_value,
            "cores": cores_value,
        }
        if yaml is not None:
            try:
                return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            except Exception:
                pass
        return f"snakefile: {data['snakefile']}\ncores: {data['cores']}\n"

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
        flat = {
            "snakefile": data.get("snakefile", "snakemake_global"),
            "cores": data.get("cores", 4),
        }
        for section in sections:
            for param in section.get("parameters", []):
                key = param["key"]
                value = flat.get(key, param.get("value"))
                if param.get("type") == "number":
                    try:
                        numeric = int(value)
                    except (TypeError, ValueError):
                        numeric = 0
                    param["value"] = numeric
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
        sections = info.get("sections")
        if sections:
            mode_var: Optional[tk.StringVar] = info.get("mode_var")
            if mode_var is not None and mode_var.get() == "raw":
                if not self._sync_extra_text_to_visual(label):
                    return
            else:
                self._update_extra_sections_from_controls(label)
            content = self._serialize_sections_for_kind(kind, info.get("sections"))
            text_widget: Optional[tk.Text] = info.get("text_widget")
            if text_widget is not None:
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", content)
        else:
            text_widget = info.get("text_widget")
            if text_widget is None:
                return
            content = text_widget.get("1.0", "end-1c")
        save_path: Optional[Path] = info.get("save_path")
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
        try:
            save_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return
        info["baseline"] = content
        info["dirty"] = False
        info["save_path"] = save_path
        info["path"] = save_path
        info["expected_path"] = save_path
        if sections:
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
        info["dirty"] = False
        status_label = info.get("status_label")
        if status_label:
            source = info.get("path")
            if source:
                status_label.configure(text=f"Loaded from {source.name}")
            else:
                expected = info.get("expected_path")
                name = expected.name if isinstance(expected, Path) else "file"
                status_label.configure(text=f"New file (will save to {name})")
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
        for row_index, param in enumerate(section.get("parameters", []), start=1):
            key = param["key"]
            value_type = param.get("type", "string")
            ttk.Label(self.param_inner, text=key).grid(row=row_index, column=0, sticky="w", padx=(0, 10), pady=2)
            if value_type == "boolean":
                var = tk.BooleanVar(value=bool(param.get("value")))
                widget = ttk.Checkbutton(
                    self.param_inner,
                    variable=var,
                    command=lambda idx=row_index - 1: self._on_param_toggle(section_index, idx),
                )
                widget.grid(row=row_index, column=1, sticky="w")
                self.param_vars[(section_index, row_index - 1)] = var
            else:
                initial = str(param.get("value", "")) if value_type != "number" else str(param.get("value", 0))
                var = tk.StringVar(value=initial)
                entry = ttk.Entry(self.param_inner, textvariable=var, width=40)
                entry.grid(row=row_index, column=1, sticky="ew")
                self.param_inner.columnconfigure(1, weight=1)
                var.trace_add(
                    "write",
                    lambda *_,
                    s_index=section_index,
                    p_index=row_index - 1,
                    v_type=value_type,
                    variable=var: self._on_param_change(s_index, p_index, v_type, variable),
                )
                self.param_vars[(section_index, row_index - 1)] = var
            description = param.get("description")
            if description:
                ttk.Label(self.param_inner, text=description, foreground="#555555").grid(
                    row=row_index, column=2, sticky="w", padx=6
                )
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
            try:
                value = float(raw_value)
            except ValueError:
                value = 0.0
        else:
            value = raw_value
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
        for stream in (proc.stdout, proc.stderr):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass
class RunTab(ttk.Frame):
    """Execution tab that runs real commands and streams output."""
    def __init__(self, master: tk.Widget, config_tab: ConfigurationTab):
        super().__init__(master)
        self.config_tab = config_tab
        self.status = "idle"
        self.progress = tk.DoubleVar(value=0)
        self.execution_mode = tk.StringVar(value="single")
        self.selected_script = tk.StringVar(value="spatial_data_prep")
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
            {"id": "exclusion", "name": "exclusion.py", "description": "Run exclusion analysis"},
        ]
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
        default_snakefile = "snakemake_global"
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
        mode = self.execution_mode.get()
        try:
            if mode == "snakemake":
                cmd, cwd, temp_path = self._build_snakemake_command()
            else:
                cmd, cwd = self._build_single_command()
                temp_path = None
        except (FileNotFoundError, RuntimeError) as exc:
            message = str(exc)
            self.add_log("error", message)
            messagebox.showerror("Execution Error", message)
            return
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
class ResultsTab(ttk.Frame):
    """Results visualization tab."""
    def __init__(self, master: tk.Widget, initial_data: Dict[str, Any]):
        super().__init__(master)
        self.results_data = deepcopy(initial_data) if initial_data else deepcopy(DEFAULT_RESULTS_DATA)
        self.json_visible = False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_controls()
        self._build_tabs()
        self._populate_all()
    def _build_controls(self) -> None:
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Results Explorer", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        button_row = ttk.Frame(header)
        button_row.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(button_row, text="Load JSON...", command=self._load_json_file).pack(side="left", padx=(0, 6))
        ttk.Button(button_row, text="Paste JSON", command=self._toggle_json_input).pack(side="left", padx=(0, 6))
        ttk.Button(button_row, text="Reset to defaults", command=self._reset_results).pack(side="left")
        self.json_frame = ttk.Frame(self)
        self.json_frame.grid(row=1, column=0, sticky="ew", padx=10)
        self.json_frame.columnconfigure(0, weight=1)
        self.json_text = tk.Text(self.json_frame, height=6, wrap="word")
        self.json_text.grid(row=0, column=0, sticky="ew")
        ttk.Button(self.json_frame, text="Apply JSON", command=self._apply_json_text).grid(row=0, column=1, padx=(6, 0))
        self.json_frame.grid_remove()
    def _build_tabs(self) -> None:
        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.summary_tab = ttk.Frame(self.tabs)
        self.summary_tab.columnconfigure(0, weight=1)
        self.tabs.add(self.summary_tab, text="Summary")
        columns = ("metric", "value", "change")
        self.summary_tree = ttk.Treeview(self.summary_tab, columns=columns, show="headings", height=8)
        for col in columns:
            self.summary_tree.heading(col, text=col.title())
            self.summary_tree.column(col, anchor="w", width=200)
        self.summary_tree.grid(row=0, column=0, sticky="nsew")
        summary_scroll = ttk.Scrollbar(self.summary_tab, orient="vertical", command=self.summary_tree.yview)
        summary_scroll.grid(row=0, column=1, sticky="ns")
        self.summary_tree.configure(yscrollcommand=summary_scroll.set)
        self.charts_tab = ttk.Frame(self.tabs)
        self.charts_tab.columnconfigure(0, weight=1)
        self.charts_tab.rowconfigure(0, weight=1)
        self.tabs.add(self.charts_tab, text="Charts")
        if MATPLOTLIB_AVAILABLE:
            self.figure = Figure(figsize=(6, 4), dpi=100)
            self.ax_bar = self.figure.add_subplot(211)
            self.ax_line = self.figure.add_subplot(212)
            self.figure.tight_layout(pad=2.0)
            self.chart_canvas = FigureCanvasTkAgg(self.figure, master=self.charts_tab)
            self.chart_canvas.draw()
            self.chart_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        else:
            ttk.Label(
                self.charts_tab,
                text="Install matplotlib to view charts.\nRun `pip install matplotlib`.",
                foreground="#555555",
                justify="center",
            ).grid(row=0, column=0, sticky="nsew", pady=40)
        self.details_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.details_tab, text="Details")
        self.details_tab.columnconfigure(0, weight=1)
        self.details_tab.rowconfigure(0, weight=1)
        self.details_tree = ttk.Treeview(self.details_tab, show="headings")
        self.details_tree.grid(row=0, column=0, sticky="nsew")
        details_scroll = ttk.Scrollbar(self.details_tab, orient="vertical", command=self.details_tree.yview)
        details_scroll.grid(row=0, column=1, sticky="ns")
        self.details_tree.configure(yscrollcommand=details_scroll.set)
        self.files_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.files_tab, text="Output Files")
        self.files_tab.columnconfigure(0, weight=1)
        self.files_container = ttk.Frame(self.files_tab)
        self.files_container.grid(row=0, column=0, sticky="nsew")
        self.files_tab.rowconfigure(0, weight=1)
        self.custom_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.custom_tab, text="Custom Graphs")
        self.custom_tab.columnconfigure(0, weight=1)
        self.custom_tab.rowconfigure(0, weight=1)
        self.custom_canvas: Optional[FigureCanvasTkAgg] = None
        if MATPLOTLIB_AVAILABLE:
            self.custom_figure = Figure(figsize=(6, 4), dpi=100)
            self.custom_ax = self.custom_figure.add_subplot(111)
            self.custom_canvas = FigureCanvasTkAgg(self.custom_figure, master=self.custom_tab)
            self.custom_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        else:
            ttk.Label(
                self.custom_tab,
                text="Install matplotlib to display custom graphs.",
                foreground="#555555",
            ).grid(row=0, column=0, sticky="nsew", pady=40)
    def _populate_all(self) -> None:
        self._populate_summary()
        self._populate_charts()
        self._populate_details()
        self._populate_files()
        self._populate_custom_graphs()
    def _populate_summary(self) -> None:
        self.summary_tree.delete(*self.summary_tree.get_children())
        for row in self.results_data.get("summary", []):
            self.summary_tree.insert("", "end", values=(row.get("metric"), row.get("value"), row.get("change", "")))
    def _populate_charts(self) -> None:
        if not MATPLOTLIB_AVAILABLE:
            return
        chart_data = self.results_data.get("chartData", [])
        names = [item.get("name", "") for item in chart_data]
        processed = [item.get("processed", 0) for item in chart_data]
        time_values = [item.get("time", 0) for item in chart_data]
        self.ax_bar.clear()
        self.ax_line.clear()
        self.ax_bar.bar(names, processed, color="#2e6f9e")
        self.ax_bar.set_ylabel("Processed")
        self.ax_bar.set_title("Processed Records by Batch")
        self.ax_bar.grid(axis="y", linestyle=":", alpha=0.5)
        self.ax_line.plot(names, time_values, marker="o", color="#a23c3d")
        self.ax_line.set_ylabel("Time (s)")
        self.ax_line.set_title("Processing Time")
        self.ax_line.grid(axis="both", linestyle=":", alpha=0.5)
        self.figure.tight_layout(pad=2.0)
        self.chart_canvas.draw()
    def _populate_details(self) -> None:
        self.details_tree.delete(*self.details_tree.get_children())
        columns = self.results_data.get("detailedResultsColumns", [])
        if not columns:
            self.details_tree["columns"] = ("message",)
            self.details_tree.heading("message", text="Message")
            self.details_tree.column("message", width=400, anchor="w")
            self.details_tree.insert("", "end", values=("No detailed results available.",))
            return
        self.details_tree["columns"] = columns
        for col in columns:
            self.details_tree.heading(col, text=col.title())
            self.details_tree.column(col, width=120, anchor="center")
        for row in self.results_data.get("detailedResults", []):
            values = [row.get(col, "") for col in columns]
            self.details_tree.insert("", "end", values=values)
    def _populate_files(self) -> None:
        for child in self.files_container.winfo_children():
            child.destroy()
        files = self.results_data.get("outputFiles", [])
        if not files:
            ttk.Label(self.files_container, text="No output files available.", foreground="#555555").pack(pady=20)
            return
        for file in files:
            card = ttk.Frame(self.files_container, padding=10, relief="groove")
            card.pack(fill="x", pady=4)
            ttk.Label(card, text=file.get("name"), font=("Segoe UI", 11, "bold")).pack(anchor="w")
            meta = f"{file.get('size')} • {file.get('records')} records • Created {file.get('created')}"
            ttk.Label(card, text=meta, foreground="#555555").pack(anchor="w", pady=(2, 4))
            ttk.Button(card, text="Download", command=lambda name=file.get("name"): self._simulate_download(name)).pack(
                anchor="e"
            )
    def _populate_custom_graphs(self) -> None:
        if not MATPLOTLIB_AVAILABLE or not self.custom_canvas:
            return
        self.custom_ax.clear()
        graphs = self.results_data.get("customGraphs", [])
        if not graphs:
            self.custom_ax.text(0.5, 0.5, "No custom graph data", ha="center", va="center")
            self.custom_canvas.draw()
            return
        graph = graphs[0]
        graph_type = graph.get("type")
        data = graph.get("data", [])
        x_key = graph.get("xKey")
        self.custom_ax.set_title(graph.get("title", "Custom Graph"))
        if graph_type == "bar":
            y_keys = graph.get("yKeys", [])
            for idx, y_key in enumerate(y_keys):
                values = [item.get(y_key, 0) for item in data]
                positions = [i + idx * 0.2 for i in range(len(data))]
                self.custom_ax.bar(positions, values, width=0.2, label=y_key)
            self.custom_ax.set_xticks(range(len(data)))
            self.custom_ax.set_xticklabels([item.get(x_key, "") for item in data])
        elif graph_type == "line":
            for y_key in graph.get("yKeys", []):
                values = [item.get(y_key, 0) for item in data]
                self.custom_ax.plot([item.get(x_key, "") for item in data], values, marker="o", label=y_key)
        elif graph_type == "pie":
            labels = [item.get(graph.get("nameKey", ""), "") for item in data]
            values = [item.get(graph.get("dataKey", ""), 0) for item in data]
            self.custom_ax.pie(values, labels=labels, autopct="%1.1f%%")
        else:  # default to area
            y_key = (graph.get("yKeys") or ["value"])[0]
            values = [item.get(y_key, 0) for item in data]
            self.custom_ax.fill_between(range(len(values)), values, alpha=0.3)
            self.custom_ax.plot(range(len(values)), values, marker="o")
            self.custom_ax.set_xticks(range(len(data)))
            self.custom_ax.set_xticklabels([item.get(x_key, "") for item in data])
        if graph_type in ("bar", "line"):
            self.custom_ax.legend()
        self.custom_ax.grid(True, linestyle=":", alpha=0.4)
        self.custom_canvas.draw()
    def _toggle_json_input(self) -> None:
        self.json_visible = not self.json_visible
        if self.json_visible:
            self.json_frame.grid()
        else:
            self.json_frame.grid_remove()
    def _load_json_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select JSON results file", filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Invalid JSON", f"Could not load JSON:\n{exc}")
            return
        if not isinstance(data, dict):
            messagebox.showerror("Invalid JSON", "Expected an object at the top level.")
            return
        self.results_data = data
        self._populate_all()
        messagebox.showinfo("Results Loaded", f"Loaded results from {filename}")
    def _apply_json_text(self) -> None:
        raw_text = self.json_text.get("1.0", "end-1c")
        if not raw_text.strip():
            return
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            messagebox.showerror("Invalid JSON", f"Could not parse JSON:\n{exc}")
            return
        if not isinstance(data, dict):
            messagebox.showerror("Invalid JSON", "Expected an object at the top level.")
            return
        self.results_data = data
        self._populate_all()
        messagebox.showinfo("Results Updated", "Results updated from JSON input.")
    def _reset_results(self) -> None:
        self.results_data = deepcopy(DEFAULT_RESULTS_DATA)
        self._populate_all()
    def _simulate_download(self, filename: Optional[str]) -> None:
        if not filename:
            messagebox.showinfo("Download", "File ready for download.")
        else:
            messagebox.showinfo("Download", f"Pretending to download {filename}.")
class PythonScriptManagerApp(tk.Tk):
    """Main application window."""
    def __init__(self) -> None:
        super().__init__()
        self.title("Python Script Manager (Tkinter)")
        self.geometry("1200x780")
        self.sections = load_initial_sections()
        self.sample_results = load_sample_results()
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        self.config_tab = ConfigurationTab(notebook, self.sections)
        notebook.add(self.config_tab, text="Configuration")
        self.run_tab = RunTab(notebook, self.config_tab)
        notebook.add(self.run_tab, text="Run")
        self.results_tab = ResultsTab(notebook, self.sample_results)
        notebook.add(self.results_tab, text="Results")
def main() -> None:
    app = PythonScriptManagerApp()
    app.mainloop()
if __name__ == "__main__":
    main()
