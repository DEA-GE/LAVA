"""Workflow preflight, execution controls, logging, and run summaries."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from collections.abc import Mapping as MappingABC
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

if __package__:
    from .configuration_tab import (
        CONFIGS_DIR,
        CONFIG_ADVANCED_SETTINGS_PATH,
        PARAMETER_CHOICES,
        ConfigurationTab,
    )
    from .data_loader import (
        LEGACY_WEATHER_DATA_EXTEND_OPTIONS,
        WEATHER_DATA_EXTEND_OPTIONS,
        resolve_technology_scenarios,
    )
    from .process_runner import ProcessRunner
    from .results_tab import ResultsTab
else:
    from configuration_tab import (  # type: ignore
        CONFIGS_DIR,
        CONFIG_ADVANCED_SETTINGS_PATH,
        PARAMETER_CHOICES,
        ConfigurationTab,
    )
    from data_loader import (  # type: ignore
        LEGACY_WEATHER_DATA_EXTEND_OPTIONS,
        WEATHER_DATA_EXTEND_OPTIONS,
        resolve_technology_scenarios,
    )
    from process_runner import ProcessRunner  # type: ignore
    from results_tab import ResultsTab  # type: ignore

from utils.region_names import canonical_region_name
from utils.spatial_prep_plan import (
    build_spatial_prep_plan,
    format_spatial_prep_plan,
    resolve_custom_study_area_path,
)

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
RUN_HISTORY_PATH = PARENT_DIR / "logs" / "ui_run_history.json"
RUN_LOG_DIR = PARENT_DIR / "logs" / "ui_runs"


class PreflightDialog(tk.Toplevel):
    """Modal review of the exact run inputs and blocking preflight checks."""

    def __init__(self, master: tk.Widget, report: Mapping[str, Any]):
        super().__init__(master)
        self.report = report
        self.confirmed = False
        is_dry_run = bool(report.get("dry_run"))
        action_name = "dry run" if is_dry_run else "run"
        self.title("Dry-run preflight" if is_dry_run else "Run preflight")
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
            detail = f"Resolve the errors below before starting this {action_name}."
        elif warnings:
            heading = (
                f"Ready to start the dry run with {len(warnings)} warning(s)"
                if is_dry_run
                else f"Ready to start with {len(warnings)} warning(s)"
            )
            color = "#8A5A00"
            detail = "Review the warnings, then start when ready."
        else:
            heading = "Ready to start dry run" if is_dry_run else "Ready to start"
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

        summary_frame = ttk.LabelFrame(
            self,
            text="Dry-run summary" if is_dry_run else "Run summary",
            padding=8,
        )
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
        treeview_style = ttk.Style(self)
        checks_text = tk.Text(
            checks_frame,
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=8,
            pady=6,
            background=treeview_style.lookup("Treeview", "background") or "white",
            foreground=treeview_style.lookup("Treeview", "foreground") or "black",
            font=("Segoe UI", 9),
            cursor="arrow",
        )
        checks_text.grid(row=0, column=0, sticky="nsew")
        checks_scroll = ttk.Scrollbar(
            checks_frame, orient="vertical", command=checks_text.yview
        )
        checks_scroll.grid(row=0, column=1, sticky="ns")
        checks_text.configure(yscrollcommand=checks_scroll.set)
        checks_text.tag_configure(
            "error", foreground="#B42318", font=("Segoe UI", 9, "bold")
        )
        checks_text.tag_configure(
            "warning", foreground="#8A5A00", font=("Segoe UI", 9, "bold")
        )
        checks_text.tag_configure(
            "passed", foreground="#1A7F37", font=("Segoe UI", 9, "bold")
        )
        issues = report.get("issues", [])
        if issues:
            for index, issue in enumerate(issues):
                severity = str(issue.get("severity", "warning"))
                if index:
                    checks_text.insert("end", "\n\n")
                checks_text.insert(
                    "end", f"{severity.title()}: ", (severity,)
                )
                checks_text.insert("end", str(issue.get("message", "")))
        else:
            checks_text.insert("end", "Passed: ", ("passed",))
            checks_text.insert(
                "end", "No problems found by the available checks."
            )
        checks_text.configure(state="disabled")
        if issues:
            details.select(checks_frame)

        footer = ttk.Frame(self, padding=(14, 6, 14, 14))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Cancel", command=self.destroy).grid(
            row=0, column=1, padx=(6, 0)
        )
        self.start_button = ttk.Button(
            footer,
            text="Start dry run" if is_dry_run else "Start run",
            command=self._confirm,
        )
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


class RunSummaryDialog(tk.Toplevel):
    """Concise post-run report with direct access to logs and outputs."""

    def __init__(
        self,
        master: tk.Widget,
        summary: Mapping[str, Any],
        *,
        open_log: Callable[[], None],
        open_output: Callable[[], None],
    ):
        super().__init__(master)
        self.title(str(summary.get("title", "Run summary")))
        self.geometry("760x570")
        self.minsize(620, 440)
        self.transient(master.winfo_toplevel())
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        header = ttk.Frame(self, padding=(16, 14, 16, 6))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            header,
            text=str(summary.get("heading", "Run finished")),
            foreground=str(summary.get("color", "#333333")),
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        subtitle = str(summary.get("subtitle", "")).strip()
        if subtitle:
            ttk.Label(
                header,
                text=subtitle,
                foreground="#555555",
                wraplength=700,
                justify="left",
            ).pack(anchor="w", pady=(4, 0))

        facts = ttk.LabelFrame(self, text="Run details", padding=8)
        facts.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 8))
        facts.columnconfigure(1, weight=1)
        for row, (label, value) in enumerate(summary.get("facts", [])):
            ttk.Label(facts, text=f"{label}:", font=("Segoe UI", 9, "bold")).grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=2
            )
            ttk.Label(
                facts,
                text=str(value),
                wraplength=580,
                justify="left",
            ).grid(row=row, column=1, sticky="w", pady=2)

        detail_frame = ttk.Frame(self, padding=(16, 0, 16, 0))
        detail_frame.grid(row=2, column=0, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        detail_text = tk.Text(
            detail_frame,
            wrap="word",
            state="normal",
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        )
        detail_text.grid(row=0, column=0, sticky="nsew")
        detail_scroll = ttk.Scrollbar(
            detail_frame, orient="vertical", command=detail_text.yview
        )
        detail_scroll.grid(row=0, column=1, sticky="ns")
        detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_text.tag_configure("section", font=("Segoe UI", 10, "bold"))
        for index, (section, items) in enumerate(summary.get("sections", [])):
            if index:
                detail_text.insert("end", "\n")
            detail_text.insert("end", f"{section}\n", ("section",))
            for item in items:
                detail_text.insert("end", f"• {item}\n")
        detail_text.configure(state="disabled")

        footer = ttk.Frame(self, padding=(16, 10, 16, 14))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Close", command=self.destroy).grid(
            row=0, column=1, padx=(6, 0)
        )
        ttk.Button(footer, text="Open full log", command=open_log).grid(
            row=0, column=2, padx=(6, 0)
        )
        ttk.Button(footer, text="Open output folder", command=open_output).grid(
            row=0, column=3, padx=(6, 0)
        )

        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        parent = master.winfo_toplevel()
        x = parent.winfo_rootx() + max(
            0, (parent.winfo_width() - self.winfo_width()) // 2
        )
        y = parent.winfo_rooty() + max(
            0, (parent.winfo_height() - self.winfo_height()) // 2
        )
        self.geometry(f"+{x}+{y}")
        self.grab_set()


class RunTab(ttk.Frame):
    """Execution tab that runs real commands and streams output."""

    STAGE_LABELS = {
        "spatial_data_prep": "Spatial data preparation",
        "exclusion": "Technology exclusion",
        "suitability": "Suitability",
        "results_analysis": "Results analysis",
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
        self.run_region_var = tk.StringVar()
        self.run_technology_var = tk.StringVar()
        self.run_scenario_var = tk.StringVar()
        self.run_weather_year_var = tk.StringVar()
        self.script_description_var = tk.StringVar()
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.after_id: Optional[str] = None
        self.runner = ProcessRunner()
        self.stop_requested = False
        self.reset_requested = False
        self.current_run_is_dry_run = False
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
                "id": "exclusion",
                "name": "Exclusion.py",
                "description": "Create a technology- and scenario-specific available-land raster.",
            },
            {
                "id": "suitability",
                "name": "suitability.py",
                "description": "Perform resource grade modeling",
            },
            {
                "id": "weather_data_prep",
                "name": "weather_data_prep.py",
                "description": "Download weather data",
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
        self.url_link_counter = 0
        self.output_url_targets: Dict[str, str] = {}
        self.issue_link_targets: Dict[str, Tuple[str, str]] = {}
        self.run_feedback_dialog: Optional[tk.Toplevel] = None
        self.expanded_feedback_notebook: Optional[ttk.Notebook] = None
        self.expanded_log_text: Optional[tk.Text] = None
        self.expanded_issue_text: Optional[tk.Text] = None
        self.expanded_run_history_tree: Optional[ttk.Treeview] = None
        self.traceback_active = False
        self.current_run_log_path: Optional[Path] = None
        self.last_log_folder: Optional[Path] = None
        self.current_run_record_id: Optional[str] = None
        self.current_run_context: Dict[str, Any] = {}
        self.current_run_diagnostics: List[Dict[str, str]] = []
        self.current_run_missing_optional_data: set[str] = set()
        self.capture_missing_optional_data = False
        self.current_run_overpass_retries: set[str] = set()
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
        ttk.Label(
            self.script_frame,
            textvariable=self.script_description_var,
            foreground="#555555",
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
        self.single_inputs_frame = ttk.LabelFrame(
            self.script_frame,
            text="Run inputs (from the documented command line)",
            padding=(8, 6),
        )
        self.single_inputs_frame.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        self.single_inputs_frame.columnconfigure(1, weight=1)
        self.single_input_rows: Dict[str, Tuple[tk.Widget, tk.Widget]] = {}
        for row_index, (name, label_text, variable) in enumerate(
            (
                ("region", "Region:", self.run_region_var),
                ("technology", "Technology:", self.run_technology_var),
                ("scenario", "Scenario:", self.run_scenario_var),
                ("weather_year", "Weather year:", self.run_weather_year_var),
            )
        ):
            input_label = ttk.Label(self.single_inputs_frame, text=label_text)
            input_label.grid(row=row_index, column=0, sticky="w", pady=2)
            input_widget = ttk.Combobox(
                self.single_inputs_frame,
                textvariable=variable,
                state="normal",
            )
            input_widget.grid(
                row=row_index, column=1, sticky="ew", padx=(8, 0), pady=2
            )
            self.single_input_rows[name] = (input_label, input_widget)
        technology_widget = self.single_input_rows["technology"][1]
        technology_widget.bind(
            "<<ComboboxSelected>>", lambda _event: self._refresh_scenario_choices()
        )
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
            text="Runs the stages enabled in config_snakemake.yaml using the selected Snakefile.",
            wraplength=500,
            foreground="#555555",
        )
        controls = ttk.Frame(body)
        controls.grid(row=3, column=0, sticky="ew", pady=10)
        controls.columnconfigure((0, 1, 2, 3, 4, 5, 6, 7), weight=1)
        self.run_button = ttk.Button(controls, text="Run", command=self.handle_run)
        self.run_button.grid(row=0, column=0, sticky="ew", padx=4)
        self.dry_run_button = ttk.Button(
            controls,
            text="Dry run",
            command=self.handle_dry_run,
        )
        self.dry_run_button.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(controls, text="Stop", command=self.handle_stop).grid(
            row=0, column=2, sticky="ew", padx=4
        )
        ttk.Button(controls, text="Reset", command=self.handle_reset).grid(
            row=0, column=3, sticky="ew", padx=4
        )
        self.copy_command_button = ttk.Button(
            controls,
            text="Copy command",
            command=self._copy_last_command,
            state="disabled",
        )
        self.copy_command_button.grid(row=0, column=4, sticky="ew", padx=4)
        self.open_log_button = ttk.Button(
            controls, text="Open full log", command=self._open_full_log
        )
        self.open_log_button.grid(row=0, column=5, sticky="ew", padx=4)
        if not self.last_log_folder:
            self.open_log_button.configure(state="disabled")
        self.open_output_button = ttk.Button(
            controls, text="Open output folder", command=self._open_output_folder
        )
        self.open_output_button.grid(row=0, column=6, sticky="ew", padx=4)
        if not self.run_history and not (PARENT_DIR / "data").is_dir():
            self.open_output_button.configure(state="disabled")
        ttk.Button(
            controls,
            text="Open larger...",
            command=self._show_run_feedback_dialog,
        ).grid(row=0, column=7, sticky="ew", padx=4)
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
        self._refresh_single_run_inputs()
        self._on_mode_change()
        self._update_status_labels()
        self._refresh_snakemake_settings_display()

    def _on_mode_change(self) -> None:
        is_single = self.execution_mode.get() == "single"
        if is_single:
            self._refresh_single_run_inputs()
            self.script_frame.grid()
            self.snakemake_options_frame.grid_remove()
            self.info_label.grid_remove()
        else:
            self.script_frame.grid_remove()
            self.snakemake_options_frame.grid(row=1, column=0, sticky="ew", pady=10)
            self.info_label.grid(row=2, column=0, sticky="ew", pady=(0, 10))
            self._refresh_snakemake_settings_display()
        self._update_run_button_states()
        self._update_status_labels()

    def _update_run_button_states(self) -> None:
        """Keep execution buttons consistent with the selected mode and runner."""
        is_running = self.status == "running" or self.runner.is_running()
        self.results_tab.set_workflow_active(is_running)
        self.run_button.configure(state="disabled" if is_running else "normal")
        dry_run_enabled = not is_running and self.execution_mode.get() == "snakemake"
        self.dry_run_button.configure(
            state="normal" if dry_run_enabled else "disabled"
        )

    def _on_script_change(self, _event: tk.Event) -> None:
        index = self.script_combo.current()
        if index >= 0:
            self.selected_script.set(self.available_scripts[index]["id"])
        self._refresh_scenario_choices()
        self._update_single_argument_visibility()

    @staticmethod
    def _load_run_input_mapping(path: Path) -> Dict[str, Any]:
        """Load a YAML mapping for run-input defaults without changing UI state."""
        if yaml is None or not path.is_file():
            return {}
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
        return document if isinstance(document, dict) else {}

    @staticmethod
    def _set_run_input_choices(
        widget: tk.Widget,
        variable: tk.StringVar,
        values: List[str],
        *,
        preferred: Any = None,
    ) -> None:
        unique_values = list(dict.fromkeys(value for value in values if value))
        widget.configure(values=unique_values)
        current = variable.get().strip()
        preferred_text = "" if preferred is None else str(preferred).strip()
        if not current:
            variable.set(preferred_text or (unique_values[0] if unique_values else ""))

    def _technology_scenarios(self, technology: str) -> List[str]:
        if not technology:
            return []
        document = self._load_run_input_mapping(CONFIGS_DIR / f"{technology}.yaml")
        reference = str(document.get("reference_scenario") or "ref").strip()
        additional = document.get("additional_scenarios") or {}
        additional_names = (
            [str(name).strip() for name in additional]
            if isinstance(additional, MappingABC)
            else []
        )
        return list(dict.fromkeys([reference, *additional_names]))

    def _refresh_scenario_choices(self) -> None:
        script_id = self.selected_script.get()
        scenarios: List[str] = []
        if script_id == "suitability":
            technologies = self.single_input_rows["technology"][1].cget("values")
            for technology in technologies:
                scenarios.extend(self._technology_scenarios(str(technology)))
        else:
            scenarios = self._technology_scenarios(self.run_technology_var.get().strip())
        config = self._load_run_input_mapping(
            self.config_tab.get_config_path() or (CONFIGS_DIR / "config.yaml")
        )
        configured_scenario = str(config.get("scenario") or "").strip()
        if configured_scenario:
            scenarios.insert(0, configured_scenario)
        self._set_run_input_choices(
            self.single_input_rows["scenario"][1],
            self.run_scenario_var,
            scenarios,
            preferred=configured_scenario or "ref",
        )

    def _refresh_single_run_inputs(self) -> None:
        """Populate documented CLI inputs from active general/workflow configs."""
        config_path = self.config_tab.get_config_path() or (CONFIGS_DIR / "config.yaml")
        config = self._load_run_input_mapping(Path(config_path))
        workflow = self._load_run_input_mapping(CONFIGS_DIR / "config_snakemake.yaml")

        regions = self._preflight_values(config.get("study_region_name"))
        regions.extend(self._preflight_values(workflow.get("study_region_name")))
        self._set_run_input_choices(
            self.single_input_rows["region"][1],
            self.run_region_var,
            regions,
            preferred=config.get("study_region_name"),
        )

        technologies = self._preflight_values(config.get("technology"))
        technologies.extend(self._preflight_values(workflow.get("technologies")))
        technologies.extend(
            technology
            for technology in PARAMETER_CHOICES["technology"]
            if (CONFIGS_DIR / f"{technology}.yaml").is_file()
        )
        self._set_run_input_choices(
            self.single_input_rows["technology"][1],
            self.run_technology_var,
            technologies,
            preferred=config.get("technology"),
        )

        raw_years = config.get("weather_years")
        if isinstance(raw_years, MappingABC):
            raw_years = raw_years.get("years")
        weather_years = self._preflight_values(config.get("weather_year"))
        weather_years.extend(self._preflight_values(raw_years))
        weather_years.extend(self._preflight_values(workflow.get("weather_years")))
        self._set_run_input_choices(
            self.single_input_rows["weather_year"][1],
            self.run_weather_year_var,
            weather_years,
            preferred=config.get("weather_year"),
        )
        self._refresh_scenario_choices()
        self._update_single_argument_visibility()

    def _update_single_argument_visibility(self) -> None:
        script_id = self.selected_script.get()
        required_inputs = {
            "spatial_data_prep": {"region"},
            "weather_data_prep": {"region", "weather_year"},
            "exclusion": {"region", "technology", "scenario"},
            "suitability": {"region", "scenario"},
            "weather_bias_adjust": set(),
            "energy_profiles": {
                "region",
                "technology",
                "scenario",
                "weather_year",
            },
        }.get(script_id, set())
        for name, (label, widget) in self.single_input_rows.items():
            if name in required_inputs:
                label.grid()
                widget.grid()
            else:
                label.grid_remove()
                widget.grid_remove()
        if required_inputs:
            self.single_inputs_frame.grid()
        else:
            self.single_inputs_frame.grid_remove()
        script = next(
            (item for item in self.available_scripts if item["id"] == script_id), None
        )
        self.script_description_var.set(str(script.get("description", "")) if script else "")

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
        trees = [self.run_history_tree]
        if (
            self.expanded_run_history_tree is not None
            and self.expanded_run_history_tree.winfo_exists()
        ):
            trees.append(self.expanded_run_history_tree)
        for tree in trees:
            self._populate_run_history_tree(tree)

    def _populate_run_history_tree(self, tree: ttk.Treeview) -> None:
        tree.delete(*tree.get_children())
        for record in self.run_history:
            duration = record.get("duration_seconds")
            duration_text = (
                f"{int(duration)}s" if isinstance(duration, (int, float)) else "--"
            )
            stages = record.get("stages") or [record.get("script_id", "")]
            regions = record.get("regions") or []
            tree.insert(
                "",
                "end",
                iid=str(record.get("id", len(tree.get_children()))),
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
        is_dry_run = bool(report.get("dry_run"))
        log_script_id = f"{script_id}_dry_run" if is_dry_run else script_id
        safe_script = re.sub(r"[^A-Za-z0-9_.-]+", "_", log_script_id)
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
            "mode": (
                "dry run" if is_dry_run else self.execution_mode.get()
            ),
            "dry_run": is_dry_run,
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
        self.open_output_button.configure(state="normal")
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

    def _history_record_for_tree(
        self, tree: Optional[ttk.Treeview]
    ) -> Optional[Dict[str, Any]]:
        if tree is None or not tree.winfo_exists():
            return None
        selection = tree.selection()
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

    def _history_record_for_selection(self) -> Optional[Dict[str, Any]]:
        tree = self.run_history_tree if hasattr(self, "run_history_tree") else None
        return self._history_record_for_tree(tree)

    def _open_path_in_file_manager(self, path: Path) -> None:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _selected_or_latest_run_record(self) -> Optional[Dict[str, Any]]:
        return self._history_record_for_selection() or (
            self.run_history[0] if self.run_history else None
        )

    def _open_full_log(self) -> None:
        self._open_full_log_for_record(self._selected_or_latest_run_record())

    def _open_full_log_for_record(
        self, record: Optional[Mapping[str, Any]]
    ) -> None:
        log_path = (
            self._resolve_preflight_path(record.get("log_file")) if record else None
        )
        if not log_path or not log_path.is_file():
            messagebox.showwarning(
                "Full Log", "No complete run log is available yet.", parent=self
            )
            return
        try:
            self._open_path_in_file_manager(log_path)
        except OSError as exc:
            messagebox.showerror(
                "Full Log", f"Could not open the run log:\n{exc}", parent=self
            )

    def _output_folder_for_record(
        self, record: Optional[Mapping[str, Any]]
    ) -> Optional[Path]:
        cwd = self._resolve_preflight_path(record.get("cwd")) if record else None
        cwd = cwd or PARENT_DIR
        stages = {
            str(stage)
            for stage in (record.get("stages", []) if record else [])
            if str(stage)
        }
        regions = [
            str(region).strip()
            for region in (record.get("regions", []) if record else [])
            if str(region).strip()
        ]
        regional_stages = {
            "spatial_data_prep",
            "exclusion",
            "suitability",
            "energy_profiles",
        }
        data_root = cwd / "data"
        if stages & regional_stages or not stages:
            if len(regions) == 1:
                region_folder = data_root / canonical_region_name(regions[0])
                if region_folder.is_dir():
                    return region_folder
            if data_root.is_dir():
                return data_root

        if stages & {"weather_data_prep", "weather_bias_adjust"}:
            config = self._load_run_input_mapping(CONFIGS_DIR / "config.yaml")
            configured_weather_folder = (
                config.get("weather_external_data_path")
                or config.get("weather_data_folder")
                or PARENT_DIR / "Raw_Spatial_Data" / "Weather_data"
            )
            weather_folder = self._resolve_preflight_path(configured_weather_folder)
            if weather_folder and weather_folder.is_dir():
                return weather_folder
        return cwd if cwd.is_dir() else None

    def _open_output_folder(self) -> None:
        self._open_output_folder_for_record(self._selected_or_latest_run_record())

    def _open_output_folder_for_record(
        self, record: Optional[Mapping[str, Any]]
    ) -> None:
        folder = self._output_folder_for_record(record)
        if not folder:
            messagebox.showwarning(
                "Output Folder", "No output folder is available yet.", parent=self
            )
            return
        try:
            self._open_path_in_file_manager(folder)
        except OSError as exc:
            messagebox.showerror(
                "Output Folder", f"Could not open the output folder:\n{exc}", parent=self
            )

    def _open_selected_history_log(self, _event: Optional[tk.Event] = None) -> None:
        self._open_history_log_from_tree(self.run_history_tree)

    def _open_history_log_from_tree(self, tree: ttk.Treeview) -> None:
        record = self._history_record_for_tree(tree)
        if not record:
            return
        log_path = self._resolve_preflight_path(record.get("log_file"))
        if log_path and log_path.is_file():
            self.last_log_folder = log_path.parent
            self._open_full_log_for_record(record)

    def _show_run_summary(
        self,
        record: Mapping[str, Any],
        *,
        return_code: int,
        outcome: str,
        is_dry_run: bool,
    ) -> None:
        summary = self._build_run_summary(
            record,
            return_code=return_code,
            outcome=outcome,
            is_dry_run=is_dry_run,
        )
        RunSummaryDialog(
            self,
            summary,
            open_log=lambda selected=record: self._open_full_log_for_record(selected),
            open_output=lambda selected=record: self._open_output_folder_for_record(
                selected
            ),
        )

    @staticmethod
    def _configure_run_text_tags(widget: tk.Text) -> None:
        for tag, color in {
            "info": "#333333",
            "success": "#1a7f37",
            "warning": "#a66b00",
            "error": "#b42318",
        }.items():
            widget.tag_configure(tag, foreground=color)

    def _bind_output_url_tag(self, widget: tk.Text, tag: str, url: str) -> None:
        widget.tag_configure(tag, foreground="#0D5D9B", underline=True)
        widget.tag_bind(
            tag,
            "<Button-1>",
            lambda _event, target=url: self._open_output_url(target),
        )
        widget.tag_bind(
            tag,
            "<Enter>",
            lambda _event, target_widget=widget: target_widget.configure(
                cursor="hand2"
            ),
        )
        widget.tag_bind(
            tag,
            "<Leave>",
            lambda _event, target_widget=widget: target_widget.configure(cursor=""),
        )

    def _bind_issue_setting_tag(
        self, widget: tk.Text, tag: str, target: Tuple[str, str]
    ) -> None:
        widget.tag_configure(tag, foreground="#0D5D9B", underline=True)
        widget.tag_bind(
            tag,
            "<Button-1>",
            lambda _event, file_name=target[0], key=target[1]: (
                self._open_failure_setting(file_name, key)
            ),
        )
        widget.tag_bind(
            tag,
            "<Enter>",
            lambda _event, target_widget=widget: target_widget.configure(
                cursor="hand2"
            ),
        )
        widget.tag_bind(
            tag,
            "<Leave>",
            lambda _event, target_widget=widget: target_widget.configure(cursor=""),
        )

    def _copy_run_text_widget(self, source: tk.Text, target: tk.Text) -> None:
        """Copy run text, colors, and hyperlink behavior into an expanded view."""
        target.configure(state="normal")
        target.delete("1.0", "end")
        content = source.get("1.0", "end-1c")
        if content:
            target.insert("1.0", content)
        self._configure_run_text_tags(target)
        for tag in source.tag_names():
            if tag == "sel":
                continue
            ranges = source.tag_ranges(tag)
            for start, end in zip(ranges[0::2], ranges[1::2]):
                target.tag_add(tag, str(start), str(end))
            if tag in self.output_url_targets:
                self._bind_output_url_tag(
                    target, tag, self.output_url_targets[tag]
                )
            elif tag in self.issue_link_targets:
                self._bind_issue_setting_tag(
                    target, tag, self.issue_link_targets[tag]
                )
        target.configure(state="disabled")
        target.see("end")

    def _close_run_feedback_dialog(self) -> None:
        dialog = self.run_feedback_dialog
        self.run_feedback_dialog = None
        self.expanded_feedback_notebook = None
        self.expanded_log_text = None
        self.expanded_issue_text = None
        self.expanded_run_history_tree = None
        if dialog is not None:
            try:
                dialog.destroy()
            except tk.TclError:
                pass

    def _show_run_feedback_dialog(self) -> None:
        dialog = self.run_feedback_dialog
        if dialog is not None:
            try:
                if dialog.winfo_exists():
                    dialog.deiconify()
                    dialog.lift()
                    dialog.focus_force()
                    return
            except tk.TclError:
                pass

        dialog = tk.Toplevel(self)
        self.run_feedback_dialog = dialog
        dialog.title("Run Output and History")
        dialog.geometry("1100x700")
        dialog.minsize(760, 420)
        dialog.transient(self.winfo_toplevel())
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        dialog.protocol("WM_DELETE_WINDOW", self._close_run_feedback_dialog)
        dialog.bind("<Escape>", lambda _event: self._close_run_feedback_dialog())

        notebook = ttk.Notebook(dialog)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        self.expanded_feedback_notebook = notebook

        output_frame = ttk.Frame(notebook)
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        notebook.add(output_frame, text="Output")
        expanded_log = tk.Text(
            output_frame,
            wrap="none",
            state="disabled",
            font=("Consolas", 10),
        )
        expanded_log.grid(row=0, column=0, sticky="nsew")
        output_scroll_y = ttk.Scrollbar(
            output_frame, orient="vertical", command=expanded_log.yview
        )
        output_scroll_y.grid(row=0, column=1, sticky="ns")
        output_scroll_x = ttk.Scrollbar(
            output_frame, orient="horizontal", command=expanded_log.xview
        )
        output_scroll_x.grid(row=1, column=0, sticky="ew")
        expanded_log.configure(
            yscrollcommand=output_scroll_y.set,
            xscrollcommand=output_scroll_x.set,
        )
        self.expanded_log_text = expanded_log

        issues_frame = ttk.Frame(notebook)
        issues_frame.columnconfigure(0, weight=1)
        issues_frame.rowconfigure(1, weight=1)
        notebook.add(issues_frame, text=f"Warnings & Errors ({self.issue_count})")
        ttk.Label(
            issues_frame,
            text=(
                "Warnings and errors are separated from normal output. "
                "Blue links open a web page or the related setting."
            ),
            foreground="#555555",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 3))
        expanded_issues = tk.Text(
            issues_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
        )
        expanded_issues.grid(row=1, column=0, sticky="nsew")
        issues_scroll = ttk.Scrollbar(
            issues_frame, orient="vertical", command=expanded_issues.yview
        )
        issues_scroll.grid(row=1, column=1, sticky="ns")
        expanded_issues.configure(yscrollcommand=issues_scroll.set)
        self.expanded_issue_text = expanded_issues

        history_frame = ttk.Frame(notebook)
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)
        notebook.add(history_frame, text="Run history")
        expanded_history = ttk.Treeview(
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
            ("work", "Stage(s)", 240),
            ("regions", "Region(s)", 190),
            ("status", "Exit status", 130),
            ("duration", "Duration", 80),
        ):
            expanded_history.heading(column, text=heading)
            expanded_history.column(
                column, width=width, stretch=column in {"work", "regions"}
            )
        expanded_history.grid(row=0, column=0, sticky="nsew")
        history_scroll_y = ttk.Scrollbar(
            history_frame, orient="vertical", command=expanded_history.yview
        )
        history_scroll_y.grid(row=0, column=1, sticky="ns")
        history_scroll_x = ttk.Scrollbar(
            history_frame, orient="horizontal", command=expanded_history.xview
        )
        history_scroll_x.grid(row=1, column=0, sticky="ew")
        expanded_history.configure(
            yscrollcommand=history_scroll_y.set,
            xscrollcommand=history_scroll_x.set,
        )
        expanded_history.bind(
            "<Double-1>",
            lambda _event: self._open_history_log_from_tree(expanded_history),
        )
        self.expanded_run_history_tree = expanded_history

        footer = ttk.Frame(dialog)
        footer.grid(row=1, column=0, sticky="ew", padx=10, pady=(4, 10))
        ttk.Label(
            footer,
            text="This is a live view. Closing it does not stop the current run.",
            foreground="#555555",
        ).pack(side="left")
        ttk.Button(
            footer, text="Close", command=self._close_run_feedback_dialog
        ).pack(side="right")

        self._copy_run_text_widget(self.log_text, expanded_log)
        self._copy_run_text_widget(self.issue_text, expanded_issues)
        self._populate_run_history_tree(expanded_history)
        try:
            notebook.select(self.run_feedback_notebook.index("current"))
        except tk.TclError:
            pass
        dialog.focus_set()

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

    @staticmethod
    def _split_text_urls(text: str) -> List[Tuple[str, Optional[str]]]:
        """Split display text into plain and HTTP(S) URL segments."""
        segments: List[Tuple[str, Optional[str]]] = []
        cursor = 0
        for match in re.finditer(r"https?://[^\s<>\"']+", text):
            if match.start() > cursor:
                segments.append((text[cursor : match.start()], None))
            matched_text = match.group(0)
            url = matched_text.rstrip(".,;:!)]}")
            trailing = matched_text[len(url) :]
            segments.append((url, url))
            if trailing:
                segments.append((trailing, None))
            cursor = match.end()
        if cursor < len(text):
            segments.append((text[cursor:], None))
        return segments or [(text, None)]

    def _open_output_url(self, url: str) -> None:
        try:
            webbrowser.open_new_tab(url)
        except Exception as exc:
            messagebox.showerror(
                "Open Link",
                f"Could not open the link:\n{url}\n\n{exc}",
                parent=self,
            )

    def _insert_text_with_urls(
        self, widget: tk.Text, text: str, base_tag: str
    ) -> None:
        """Insert text and make every HTTP(S) URL behave like a hyperlink."""
        for segment, url in self._split_text_urls(text):
            if not url:
                widget.insert("end", segment, base_tag)
                continue
            self.url_link_counter += 1
            link_tag = f"output_url_{self.url_link_counter}"
            widget.insert("end", segment, (base_tag, link_tag))
            self.output_url_targets[link_tag] = url
            self._bind_output_url_tag(widget, link_tag, url)

    def _insert_issue_setting_link(
        self, widget: tk.Text, target: Tuple[str, str]
    ) -> None:
        self.issue_link_counter += 1
        link_tag = f"issue_link_{self.issue_link_counter}"
        self.issue_link_targets[link_tag] = target
        widget.insert("end", "  Open related setting", (link_tag,))
        self._bind_issue_setting_tag(widget, link_tag, target)

    @staticmethod
    def _existing_text_widget(widget: Optional[tk.Text]) -> Optional[tk.Text]:
        if widget is None:
            return None
        try:
            return widget if widget.winfo_exists() else None
        except tk.TclError:
            return None

    def add_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        if level in {"warning", "error"}:
            self.current_run_diagnostics.append(
                {
                    "severity": level,
                    "message": message.strip(),
                    "stage": self.current_stage,
                    "region": self.current_region,
                    "technology": self.current_technology,
                }
            )
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
            issue_widgets = [self.issue_text]
            expanded_issues = self._existing_text_widget(self.expanded_issue_text)
            if expanded_issues is not None:
                issue_widgets.append(expanded_issues)
            for widget in issue_widgets:
                widget.configure(state="normal")
                self._insert_text_with_urls(widget, display, level)
                if target:
                    self._insert_issue_setting_link(widget, target)
                widget.insert("end", "\n")
                widget.configure(state="disabled")
                widget.see("end")
            self.issue_count += 1
            self.run_feedback_notebook.tab(
                self.issues_frame, text=f"Warnings & Errors ({self.issue_count})"
            )
            if self.expanded_feedback_notebook is not None:
                try:
                    self.expanded_feedback_notebook.tab(
                        1, text=f"Warnings & Errors ({self.issue_count})"
                    )
                except tk.TclError:
                    pass
            if level == "error":
                self.run_feedback_notebook.select(self.issues_frame)
                if self.expanded_feedback_notebook is not None:
                    try:
                        self.expanded_feedback_notebook.select(1)
                    except tk.TclError:
                        pass
        else:
            tag = level if level in {"info", "success"} else "info"
            output_widgets = [self.log_text]
            expanded_log = self._existing_text_widget(self.expanded_log_text)
            if expanded_log is not None:
                output_widgets.append(expanded_log)
            for widget in output_widgets:
                widget.configure(state="normal")
                self._insert_text_with_urls(widget, formatted, tag)
                widget.insert("end", "\n", tag)
                widget.configure(state="disabled")
                widget.see("end")
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
        widgets = [self.log_text, self.issue_text]
        for expanded in (self.expanded_log_text, self.expanded_issue_text):
            existing = self._existing_text_widget(expanded)
            if existing is not None:
                widgets.append(existing)
        for widget in widgets:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.configure(state="disabled")
        self.issue_count = 0
        self.issue_link_counter = 0
        self.url_link_counter = 0
        self.output_url_targets.clear()
        self.issue_link_targets.clear()
        self.traceback_active = False
        self.current_run_context = {}
        self.current_run_diagnostics = []
        self.current_run_missing_optional_data = set()
        self.capture_missing_optional_data = False
        self.current_run_overpass_retries = set()
        self.run_feedback_notebook.tab(self.issues_frame, text="Warnings & Errors (0)")
        if self.expanded_feedback_notebook is not None:
            try:
                self.expanded_feedback_notebook.tab(1, text="Warnings & Errors (0)")
            except tk.TclError:
                pass

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
        scenario_mapping = context.get("technology_scenarios", {})
        scenario_counts = (
            [len(values) for values in scenario_mapping.values()]
            if isinstance(scenario_mapping, Mapping)
            else []
        )
        technology_scenario_count = sum(scenario_counts) or technology_count
        shared_scenario_count = max(scenario_counts, default=1)
        stages = set(context.get("stages", []))
        total = 1  # Snakemake's final `all` job.
        if "spatial_data_prep" in stages or "exclusion" in stages:
            total += region_count
        if "exclusion" in stages:
            total += region_count * technology_scenario_count
        if "suitability" in stages:
            total += region_count * shared_scenario_count
        if "timeseries" in stages:
            total += region_count * technology_scenario_count * year_count
        if "weather_data_prep" in stages:
            total += region_count * year_count
        if "weather_bias_adjust" in stages:
            total += region_count
        if "energy_profiles" in stages:
            total += region_count * technology_scenario_count * year_count
        return max(1, total)

    def _initialize_run_feedback(self, report: Mapping[str, Any]) -> None:
        context = report.get("run_context", {})
        context = context if isinstance(context, Mapping) else {}
        self.current_run_context = dict(context)
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
        # Scenario mappings for technologies outside the current selection are
        # retained deliberately, so changing selections does not discard their
        # configuration.  This is advisory even if an upstream formatter adds
        # an ERROR prefix to the message.
        if "scenario selections exist for unselected technologies" in lower:
            return "warning"
        if (
            "does not define the scenario" in lower
            or "selected snakemake scenarios are not defined" in lower
        ):
            return "error"
        if "overpass query failed" in lower and "retrying" in lower:
            return "warning"
        if "following data was not found in data folder" in lower:
            return "warning"
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
            PARENT_DIR / "utils" / script_name,
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
        command = [sys.executable, "-u", str(script_path)]
        if script_id == "results_analysis":
            command.extend(["--root", str(PARENT_DIR)])

        values = {
            "region": self.run_region_var.get().strip(),
            "technology": self.run_technology_var.get().strip(),
            "scenario": self.run_scenario_var.get().strip(),
            "weather_year": self.run_weather_year_var.get().strip(),
        }
        arguments_by_script = {
            "spatial_data_prep": (("region", "--region"),),
            "weather_data_prep": (
                ("region", "--region"),
                ("weather_year", "--weather_years"),
            ),
            "exclusion": (
                ("region", "--region"),
                ("technology", "--technology"),
                ("scenario", "--scenario"),
            ),
            "suitability": (
                ("region", "--region"),
                ("scenario", "--scenario"),
            ),
            "weather_bias_adjust": (),
            "energy_profiles": (
                ("region", "--region"),
                ("technology", "--technology"),
                ("scenario", "--scenario"),
                ("weather_year", "--weather_year"),
            ),
        }
        for value_name, flag in arguments_by_script.get(script_id, ()):
            value = values[value_name]
            if not value:
                display_name = value_name.replace("_", " ")
                raise RuntimeError(
                    f"Select a {display_name} before running {script_name}."
                )
            command.extend([flag, value])
        return command, PARENT_DIR if script_id == "results_analysis" else script_path.parent

    def _build_snakemake_command(
        self, *, dry_run: bool = False
    ) -> Tuple[List[str], Path, Optional[Path]]:
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
            str(snakefile_path),
            cores_value,
            snakemake_exec,
            dry_run=dry_run,
        )
        return command, PARENT_DIR, None

    def _assemble_snakemake_command(
        self,
        snakefile_path: str,
        cores: int,
        snakemake_exec: Optional[str],
        *,
        dry_run: bool = False,
    ) -> List[str]:
        base_args = [
            "--snakefile",
            snakefile_path,
            "--cores",
            str(cores),
            "--resources",
            "openeo_req=1",
        ]
        if dry_run:
            base_args.extend(["--dry-run", "--printshellcmds"])
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
                        resolved_path, used_legacy_name = (
                            resolve_custom_study_area_path(
                                configured_region=region,
                                filename_template=custom_name,
                                project_root=PARENT_DIR,
                            )
                        )
                    except ValueError:
                        resolved_path = (
                            PARENT_DIR
                            / "Raw_Spatial_Data"
                            / "custom_study_area"
                            / custom_name
                        )
                        used_legacy_name = False
                        self._add_preflight_issue(
                            report,
                            "error",
                            f"Invalid custom study-area filename template: {custom_name}",
                        )
                    self._record_preflight_path(
                        report,
                        f"Custom study area ({region})",
                        resolved_path,
                    )
                    if used_legacy_name:
                        self._add_preflight_issue(
                            report,
                            "warning",
                            "Using a legacy cleaned custom study-area filename for "
                            f"{region}: {resolved_path.name}. Rename it using the "
                            "original region spelling when convenient.",
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

        if "weather_data_prep" in stage_set:
            weather_extent = str(config.get("weather_data_extend") or "").strip()
            if (
                weather_extent
                and weather_extent not in WEATHER_DATA_EXTEND_OPTIONS
                and weather_extent not in LEGACY_WEATHER_DATA_EXTEND_OPTIONS
            ):
                self._record_preflight_path(
                    report,
                    "Custom weather study area",
                    PARENT_DIR
                    / "Raw_Spatial_Data"
                    / "custom_study_area"
                    / weather_extent,
                )

        weather_consumers = {"weather_bias_adjust", "energy_profiles"}
        weather_path_value = config.get("weather_external_data_path")
        if stage_set & weather_consumers:
            if weather_path_value is None or not str(weather_path_value).strip():
                weather_path_value = PARENT_DIR / "Raw_Spatial_Data" / "Weather_data"
            weather_path = self._record_preflight_path(
                report,
                "Weather-data directory",
                weather_path_value,
                kind="directory",
                required="weather_data_prep" not in stage_set,
                missing_status="Will create",
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

    def build_preflight_report(self, *, dry_run: bool = False) -> Dict[str, Any]:
        """Build a non-mutating report for the currently selected execution."""
        report: Dict[str, Any] = {
            "summary": {},
            "files": [],
            "issues": [],
            "command": None,
            "cwd": None,
            "temp_path": None,
            "script_id": None,
            "dry_run": dry_run,
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
            technology_scenario_map = resolve_technology_scenarios(snakemake)
            scenario_summary = "; ".join(
                f"{technology}: {', '.join(names)}"
                for technology, names in technology_scenario_map.items()
            )
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
            self._refresh_single_run_inputs()
            script_id = self.selected_script.get()
            regions = self._preflight_values(self.run_region_var.get())
            scenario = self.run_scenario_var.get().strip()
            technology_scenario_map = {}
            scenario_summary = scenario
            stages = [script_id]
            technologies = (
                self._preflight_values(self.run_technology_var.get())
                if script_id in {"exclusion", "energy_profiles"}
                else []
            )
            weather_years = (
                self._preflight_values(self.run_weather_year_var.get())
                if script_id in {"weather_data_prep", "energy_profiles"}
                else []
            )
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
                command, cwd, temp_path = self._build_snakemake_command(
                    dry_run=dry_run
                )
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

        if mode == "snakemake" and "exclusion" in stages:
            try:
                spatial_plan = build_spatial_prep_plan(project_root=PARENT_DIR)
                report["spatial_prep_plan"] = spatial_plan
                external_issues = spatial_plan.get("external_issues") or []
                for issue in external_issues:
                    self._add_preflight_issue(
                        report,
                        "error",
                        "Spatial preparation cannot create the external input "
                        f"{issue.get('path')}: {issue.get('reason')}.",
                    )
                if spatial_plan.get("requires_preparation"):
                    affected = ", ".join(spatial_plan.get("invalid_regions") or [])
                    if dry_run:
                        message = (
                            "Spatial preparation is required for "
                            f"{affected}. The dry run will force the checkpoint in "
                            "planning mode but will not download or modify data."
                        )
                    else:
                        message = (
                            "Spatial preparation will be forced before exclusion for: "
                            f"{affected}. Prepared inputs will be validated again "
                            "before exclusion starts."
                        )
                    self._add_preflight_issue(report, "warning", message)
                    command = report.get("command")
                    if isinstance(command, list) and "--forcerun" not in command:
                        force_targets = [
                            str(
                                Path("data")
                                / region
                                / f"{region}_local_CRS.pkl"
                            )
                            for region in spatial_plan.get("invalid_regions") or []
                        ]
                        command.extend(["--forcerun", *force_targets])
            except Exception as exc:
                self._add_preflight_issue(
                    report,
                    "error",
                    f"Spatial preparation planning could not run: {exc}",
                )

        execution_summary = "Single script"
        if mode == "snakemake":
            execution_summary = (
                "Snakemake dry run" if dry_run else "Snakemake workflow"
            )
        report["summary"] = {
            "Execution": execution_summary,
            "Regions": ", ".join(regions) if regions else "Not configured",
            "Technologies": ", ".join(technologies)
            if technologies
            else "Not applicable",
            "Scenarios by technology"
            if mode == "snakemake"
            else "Scenario": scenario_summary or "Not configured",
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
            "scenario": scenario if mode != "snakemake" else "",
            "technology_scenarios": technology_scenario_map,
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

    def _capture_run_diagnostic_context(self, message: str) -> None:
        """Collect structured details that are too fragmented in raw output."""
        stripped = message.strip()
        lower = stripped.lower()
        if "following data was not found in data folder" in lower:
            self.capture_missing_optional_data = True
            return
        if self.capture_missing_optional_data:
            if stripped.startswith("-"):
                item = stripped.lstrip("- ").strip()
                if item:
                    self.current_run_missing_optional_data.add(item)
                return
            self.capture_missing_optional_data = False

        retry_match = re.search(
            r"Overpass query failed for ['\"]([^'\"]+)['\"].*retrying",
            stripped,
            re.IGNORECASE,
        )
        if retry_match:
            self.current_run_overpass_retries.add(retry_match.group(1))

    @staticmethod
    def _format_run_duration(seconds: Optional[float]) -> str:
        if seconds is None:
            return "--"
        total_seconds = max(0, int(round(seconds)))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds_part = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m {seconds_part}s"
        if minutes:
            return f"{minutes}m {seconds_part}s"
        return f"{seconds_part}s"

    @staticmethod
    def _unique_summary_messages(messages: List[str], limit: int = 6) -> List[str]:
        unique: List[str] = []
        seen: set[str] = set()
        for message in messages:
            compact = re.sub(r"\s+", " ", message).strip()
            if not compact:
                continue
            key = compact.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(compact)
        if len(unique) > limit:
            remaining = len(unique) - limit
            return [*unique[:limit], f"{remaining} additional message(s); see the full log."]
        return unique

    def _group_run_diagnostics(self, *, successful: bool) -> Tuple[List[str], List[str]]:
        warnings: List[str] = []
        errors: List[str] = []
        if self.current_run_overpass_retries:
            datasets = ", ".join(sorted(self.current_run_overpass_retries))
            recovery = " and the workflow recovered" if successful else ""
            warnings.append(
                "The OpenStreetMap service temporarily failed for "
                f"{datasets}; an automatic retry was attempted{recovery}."
            )
        if self.current_run_missing_optional_data:
            warnings.append(
                "Optional exclusion data were unavailable and omitted: "
                + ", ".join(sorted(self.current_run_missing_optional_data))
                + "."
            )

        for diagnostic in self.current_run_diagnostics:
            severity = diagnostic.get("severity", "warning")
            message = diagnostic.get("message", "").strip()
            lower = message.lower()
            if not message:
                continue
            if (
                "following data was not found in data folder" in lower
                or ("overpass query failed" in lower and "retrying" in lower)
            ):
                continue
            if lower.startswith("spatial preparation check:"):
                continue
            if severity == "error":
                if lower.startswith("traceback (most recent call last)"):
                    continue
                if re.match(r'^file\s+["\']', message, re.IGNORECASE):
                    continue
                if not re.search(
                    r"error|exception|failed|failure|missing|lock|exited|cannot|"
                    r"not found|invalid|terminated|killed|non-zero",
                    lower,
                ):
                    continue
                errors.append(message)
            else:
                warnings.append(message)

        warnings = self._unique_summary_messages(warnings)
        errors = self._unique_summary_messages(errors)
        if successful and errors:
            warnings.extend(
                f"Recovered/non-fatal: {message}" for message in errors
            )
            errors = []
            warnings = self._unique_summary_messages(warnings)
        return warnings, errors

    def _build_run_summary(
        self,
        record: Mapping[str, Any],
        *,
        return_code: int,
        outcome: str,
        is_dry_run: bool,
    ) -> Dict[str, Any]:
        successful = outcome in {"completed", "dry_run_completed"}
        warnings, errors = self._group_run_diagnostics(successful=successful)
        if outcome in {"stopped", "reset"} and errors:
            warnings = self._unique_summary_messages([*warnings, *errors])
            errors = []
        is_workflow = str(record.get("script_id")) == "snakemake"
        subject = "Workflow" if is_workflow else "Run"

        if outcome == "dry_run_completed" and warnings:
            heading = "Dry run completed with warnings"
            subtitle = (
                "Snakemake planned the workflow without executing jobs; review the "
                "warnings below."
            )
            color = "#8A5A00"
            status_text = "Dry run completed with warnings"
        elif outcome == "dry_run_completed":
            heading = "Dry run completed successfully"
            subtitle = "Snakemake validated and planned the workflow; no jobs were executed."
            color = "#1A7F37"
            status_text = "Dry run completed"
        elif outcome == "completed" and warnings:
            heading = f"{subject} completed with warnings"
            subtitle = "All requested jobs completed, but review the warnings below."
            color = "#8A5A00"
            status_text = "Completed with warnings"
        elif outcome == "completed":
            heading = f"{subject} completed successfully"
            subtitle = "All requested work finished without detected warnings or errors."
            color = "#1A7F37"
            status_text = "Completed"
        elif outcome == "stopped":
            heading = f"{subject} was stopped"
            subtitle = "The process ended after a stop request. Completed outputs were retained."
            color = "#8A5A00"
            status_text = "Stopped"
        elif outcome == "reset":
            heading = f"{subject} was reset"
            subtitle = "The process was terminated and the Run tab was reset."
            color = "#8A5A00"
            status_text = "Reset"
        else:
            heading = f"{subject} failed"
            subtitle = "The workflow did not complete. Review the error summary and full log."
            color = "#B42318"
            status_text = "Failed"

        regions = [str(value) for value in record.get("regions", []) if str(value)]
        technologies = [
            str(value) for value in record.get("technologies", []) if str(value)
        ]
        stages = [str(value) for value in record.get("stages", []) if str(value)]
        scenario_mapping = self.current_run_context.get("technology_scenarios", {})
        scenario_parts: List[str] = []
        if isinstance(scenario_mapping, Mapping):
            for technology, values in scenario_mapping.items():
                selected = self._preflight_values(values)
                if selected:
                    scenario_parts.append(f"{technology}: {', '.join(selected)}")
        single_scenario = str(self.current_run_context.get("scenario", "")).strip()

        duration = None
        if self.start_time is not None and self.end_time is not None:
            duration = self.end_time - self.start_time
        if is_dry_run:
            jobs_text = "Planning only; no jobs executed"
        elif self.total_jobs:
            jobs_text = f"{self.completed_jobs} of {self.total_jobs} completed"
        else:
            jobs_text = f"{self.completed_jobs} completed"

        facts: List[Tuple[str, str]] = [
            ("Status", status_text),
            ("Duration", self._format_run_duration(duration)),
            ("Jobs", jobs_text),
            (
                "Stages",
                ", ".join(self.STAGE_LABELS.get(stage, stage) for stage in stages)
                or "Not recorded",
            ),
            ("Regions", ", ".join(regions) or "Not applicable"),
            ("Technologies", ", ".join(technologies) or "Not applicable"),
        ]
        scenario_text = "; ".join(scenario_parts) or single_scenario
        if scenario_text:
            facts.append(("Scenarios", scenario_text))
        facts.append(("Exit code", str(return_code)))

        sections: List[Tuple[str, List[str]]] = []
        if successful:
            completed_items = (
                ["The workflow graph and required commands were validated."]
                if is_dry_run
                else [
                    f"{self.STAGE_LABELS.get(stage, stage)} completed."
                    for stage in stages
                ]
            )
            if not completed_items:
                completed_items = ["The requested process completed."]
            sections.append(("Completed work", completed_items))
        elif self.completed_jobs:
            sections.append(
                ("Completed work", [f"{self.completed_jobs} job(s) completed before the run ended."])
            )
        if warnings:
            sections.append(("Warnings", warnings))
        if errors:
            sections.append(("Errors", errors))
        elif not successful and outcome == "failed":
            sections.append(
                ("Errors", [f"The process exited with code {return_code}; see the full log for details."])
            )
        if not sections:
            sections.append(("Result", ["No additional diagnostics were recorded."]))

        return {
            "title": "Workflow run summary" if is_workflow else "Run summary",
            "heading": heading,
            "subtitle": subtitle,
            "color": color,
            "facts": facts,
            "sections": sections,
        }

    def _handle_process_output(self, level: str, message: str) -> None:
        self._capture_run_diagnostic_context(message)
        self._update_run_context_from_output(message)
        self.add_log(self._classify_process_message(level, message), message)

    def _handle_process_exit(self, return_code: int) -> None:
        is_dry_run = self.current_run_is_dry_run
        record = next(
            (
                item
                for item in self.run_history
                if item.get("id") == self.current_run_record_id
            ),
            {
                "script_id": self.last_run_script_id or "run",
                "stages": self.current_run_context.get("stages", []),
                "regions": self.current_run_context.get("regions", []),
                "technologies": self.current_run_context.get("technologies", []),
                "cwd": str(self.expected_output_dir or PARENT_DIR),
            },
        )
        self.runner.cancel()
        self._stop_spinner()
        self._cancel_duration_timer()
        self.end_time = time.time()
        self._cleanup_temp_snakefile()
        if self.reset_requested:
            process_name = "Dry run" if is_dry_run else "Process"
            self.add_log(
                "error", f"{process_name} reset after exiting with code {return_code}."
            )
            history_status = "Dry run reset" if is_dry_run else "Reset"
            self._finish_run_record(return_code, history_status)
            self._show_run_summary(
                record,
                return_code=return_code,
                outcome="reset",
                is_dry_run=is_dry_run,
            )
            self.current_run_log_path = None
            self._finalize_reset()
            return
        if return_code == 0 and not self.stop_requested:
            self.status = "completed"
            self.progress.set(100)
            if is_dry_run:
                self.completed_jobs = 0
                self.total_jobs = 0
                self._refresh_progress_feedback()
                self.jobs_var.set("Dry run complete — no jobs executed")
                self.add_log(
                    "success", "Dry run completed successfully; no jobs were executed."
                )
            else:
                self.completed_jobs = self.total_jobs
                self._refresh_progress_feedback()
                self.add_log("success", "Process completed successfully.")
                self._update_results_tab_with_json()
            self._update_status_labels()
            if is_dry_run:
                self._finish_run_record(return_code, "Dry run completed")
                outcome = "dry_run_completed"
            else:
                self._finish_run_record(return_code, "Completed")
                outcome = "completed"
            self._show_run_summary(
                record,
                return_code=return_code,
                outcome=outcome,
                is_dry_run=is_dry_run,
            )
        else:
            self.status = "error"
            if self.stop_requested:
                process_name = "Dry run" if is_dry_run else "Process"
                self.add_log(
                    "error",
                    f"{process_name} exited with code {return_code} after stop request.",
                )
                history_status = "Dry run stopped" if is_dry_run else "Stopped"
                outcome = "stopped"
            else:
                process_name = "Dry run" if is_dry_run else "Process"
                self.add_log("error", f"{process_name} exited with code {return_code}.")
                history_status = "Dry run failed" if is_dry_run else "Failed"
                outcome = "failed"
            self._finish_run_record(return_code, history_status)
            self._update_status_labels()
            self._show_run_summary(
                record,
                return_code=return_code,
                outcome=outcome,
                is_dry_run=is_dry_run,
            )
        self.current_run_log_path = None
        self.stop_requested = False
        self.reset_requested = False
        self.last_run_script_id = None
        self.expected_output_dir = None
        self.current_run_is_dry_run = False
        self._update_run_button_states()

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
        self.current_run_is_dry_run = False
        self._update_run_button_states()

    def handle_run(self) -> None:
        self._handle_execution(dry_run=False)

    def handle_dry_run(self) -> None:
        if self.execution_mode.get() != "snakemake":
            messagebox.showinfo(
                "Dry Run",
                "Dry run is available only in Snakemake Workflow mode.",
            )
            return
        self._handle_execution(dry_run=True)

    def _handle_execution(self, *, dry_run: bool) -> None:
        if self.runner.is_running():
            return
        if self.results_tab.has_active_operation():
            messagebox.showwarning(
                "Run Workflow",
                "Wait for the active aggregation or scenario deletion in the Results tab to finish.",
            )
            return
        self.expected_output_dir = None
        self.last_run_script_id = None
        self.current_run_is_dry_run = False
        report = self.build_preflight_report(dry_run=dry_run)
        dialog = PreflightDialog(self, report)
        self.wait_window(dialog)
        if not dialog.confirmed:
            errors = [
                item for item in report["issues"] if item.get("severity") == "error"
            ]
            if errors:
                action_name = "Dry run" if dry_run else "Run"
                self.add_log(
                    "error",
                    f"{action_name} blocked by {len(errors)} preflight error(s).",
                )
            else:
                action_name = "Dry run" if dry_run else "Run"
                self.add_log(
                    "info", f"{action_name} cancelled after preflight review."
                )
            return
        cmd = report.get("command")
        cwd = report.get("cwd")
        temp_path = report.get("temp_path")
        script_id = report.get("script_id")
        if not cmd or not cwd:
            action_name = "dry run" if dry_run else "run"
            self.add_log(
                "error",
                f"The {action_name} was blocked because preflight did not produce a valid command.",
            )
            return
        self.expected_output_dir = cwd
        self.last_run_script_id = script_id
        if not dry_run and script_id == "results_analysis":
            self.results_tab.clear_aggregated_results()
        self.temp_snakefile_path = temp_path
        self.stop_requested = False
        self.reset_requested = False
        self.current_run_is_dry_run = dry_run
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
        action_name = "dry run" if dry_run else "process"
        spatial_plan = report.get("spatial_prep_plan")
        if isinstance(spatial_plan, Mapping):
            plan_level = (
                "warning" if spatial_plan.get("requires_preparation") else "info"
            )
            for line in format_spatial_prep_plan(spatial_plan):
                self.add_log(plan_level, line)
        self.add_log("info", f"Starting {action_name}: {self.last_command_text}")
        self._update_run_button_states()
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
            action_name = "dry run" if dry_run else "process"
            self.runner.cancel()
            self._stop_spinner()
            self._cancel_duration_timer()
            self.status = "error"
            self.add_log("error", f"Failed to start {action_name}: {exc}")
            history_status = "Dry run start failed" if dry_run else "Start failed"
            self._finish_run_record(None, history_status)
            self.current_run_log_path = None
            self.start_time = None
            self.end_time = None
            self._update_status_labels()
            messagebox.showerror(
                "Dry Run Error" if dry_run else "Execution Error",
                f"Failed to start {action_name}:\n{exc}",
            )
            self._cleanup_temp_snakefile()
            self.stop_requested = False
            self.reset_requested = False
            self.last_run_script_id = None
            self.expected_output_dir = None
            self.current_run_is_dry_run = False
            self._update_run_button_states()

    def handle_stop(self) -> None:
        if not self.runner.is_running():
            return
        self.stop_requested = True
        self.runner.stop()
        self._stop_spinner()
        self._cancel_duration_timer()
        self.status = "error"
        self.end_time = time.time()
        action_name = "Dry run" if self.current_run_is_dry_run else "Execution"
        self.add_log("error", f"{action_name} stopped by user.")
        self._update_status_labels()

    def handle_reset(self) -> None:
        if self.runner.is_running():
            self.reset_requested = True
            self.stop_requested = True
            self.runner.stop()
            return
        self._finalize_reset()
