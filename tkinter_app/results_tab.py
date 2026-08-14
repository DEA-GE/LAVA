"""Results aggregation, scenario deletion, and map notebook tab."""

from __future__ import annotations

import csv
import json
import re
import shlex
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Mapping, Optional, Tuple

if __package__:
    from .map_tab import MapTab
    from .process_runner import ProcessRunner
else:
    from map_tab import MapTab  # type: ignore
    from process_runner import ProcessRunner  # type: ignore
from utils.delete_scenario_results import (
    ResultsDeletionError,
    collect_scenario_files,
    discover_scenarios,
)


CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent

RESULT_METRICS = (
    "eligibility_share_%",
    "available_area_km2",
    "power_potential_TW",
)
COMPARISON_COLUMNS = (
    "Technology",
    "Region",
    "baseline_eligibility_share_%",
    "comparison_eligibility_share_%",
    "difference_eligibility_share_pp",
    "baseline_available_area_km2",
    "comparison_available_area_km2",
    "difference_available_area_km2",
    "baseline_power_potential_TW",
    "comparison_power_potential_TW",
    "difference_power_potential_TW",
)


def numeric_result(value: Any) -> Optional[float]:
    """Convert JSON result numbers, including scientific-notation strings."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_scenario_comparison(
    rows: List[Dict[str, Any]],
    baseline_scenario: str,
    comparison_scenario: str,
    *,
    technology: str = "",
    region: str = "",
) -> List[Dict[str, Any]]:
    """Match two scenarios by technology and region and calculate differences."""

    def selected(row: Mapping[str, Any], scenario: str) -> bool:
        if str(row.get("Scenario", "")) != scenario:
            return False
        if technology and str(row.get("Technology", "")) != technology:
            return False
        if region and str(row.get("Region", "")) != region:
            return False
        return True

    baseline = {
        (str(row.get("Technology", "")), str(row.get("Region", ""))): row
        for row in rows
        if selected(row, baseline_scenario)
    }
    comparison = {
        (str(row.get("Technology", "")), str(row.get("Region", ""))): row
        for row in rows
        if selected(row, comparison_scenario)
    }
    keys = sorted(set(baseline) | set(comparison), key=lambda item: (item[0], item[1]))
    result: List[Dict[str, Any]] = []
    for technology_name, region_name in keys:
        baseline_row = baseline.get((technology_name, region_name), {})
        comparison_row = comparison.get((technology_name, region_name), {})
        item: Dict[str, Any] = {
            "Technology": technology_name,
            "Region": region_name,
        }
        for metric in RESULT_METRICS:
            baseline_value = numeric_result(baseline_row.get(metric))
            comparison_value = numeric_result(comparison_row.get(metric))
            item[f"baseline_{metric}"] = baseline_value
            item[f"comparison_{metric}"] = comparison_value
            difference_key = (
                "difference_eligibility_share_pp"
                if metric == "eligibility_share_%"
                else f"difference_{metric}"
            )
            item[difference_key] = (
                comparison_value - baseline_value
                if baseline_value is not None and comparison_value is not None
                else None
            )
        result.append(item)
    return result


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
        self.aggregated_sort_reverse: Dict[str, bool] = {}
        self.comparison_columns = COMPARISON_COLUMNS
        self.current_comparison_rows: List[Dict[str, Any]] = []
        self.comparison_sort_reverse: Dict[str, bool] = {}
        self.baseline_scenario_var = tk.StringVar()
        self.comparison_scenario_var = tk.StringVar()
        self.comparison_technology_var = tk.StringVar(value="All")
        self.comparison_region_var = tk.StringVar(value="All")
        self.chart_group_var = tk.StringVar(value="Region")
        self.chart_metric_var = tk.StringVar(value="Available area (km²)")
        self.comparison_status_var = tk.StringVar(
            value="Load aggregated results containing at least two scenarios."
        )
        self.comparison_tree: Optional[ttk.Treeview] = None
        self.comparison_chart: Optional[tk.Canvas] = None
        self.baseline_scenario_combo: Optional[ttk.Combobox] = None
        self.comparison_scenario_combo: Optional[ttk.Combobox] = None
        self.comparison_technology_combo: Optional[ttk.Combobox] = None
        self.comparison_region_combo: Optional[ttk.Combobox] = None
        self.delete_log_text: Optional[tk.Text] = None
        self.delete_scenario_var = tk.StringVar()
        self.delete_scenario_combo: Optional[ttk.Combobox] = None
        self.delete_preview_tree: Optional[ttk.Treeview] = None
        self.delete_preview_files: List[Path] = []
        self.delete_run_button: Optional[ttk.Button] = None
        self.delete_stop_button: Optional[ttk.Button] = None
        self.delete_status_label: Optional[ttk.Label] = None
        self.external_workflow_active = False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.analysis_tab = ttk.Frame(self.notebook)
        self.analysis_tab.columnconfigure(0, weight=1)
        self.analysis_tab.rowconfigure(0, weight=1)
        self.comparison_tab = ttk.Frame(self.notebook)
        self.comparison_tab.columnconfigure(0, weight=1)
        self.comparison_tab.rowconfigure(0, weight=1)
        self.delete_tab = ttk.Frame(self.notebook)
        self.delete_tab.columnconfigure(0, weight=1)
        self.delete_tab.rowconfigure(0, weight=1)
        self.notebook.add(self.analysis_tab, text="Aggregated Results")
        self.notebook.add(self.comparison_tab, text="Scenario Comparison")
        self.notebook.add(self.delete_tab, text="Delete Scenario Results")
        self.map_tab = MapTab(self.notebook)
        self.notebook.add(self.map_tab, text="Map")
        self._build_analysis_tab()
        self._build_comparison_tab()
        self._build_delete_tab()

    def _build_analysis_tab(self) -> None:
        frame = ttk.LabelFrame(self.analysis_tab, text="Results Analysis")
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=0)
        frame.rowconfigure(4, weight=1)

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
        log_frame.grid(row=3, column=0, sticky="ew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame, height=4, wrap="none", state="disabled", font=("Consolas", 10)
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
            self.aggregated_tree.heading(
                col,
                text=header,
                command=lambda column=col: self._sort_tree_column(
                    self.aggregated_tree,
                    column,
                    numeric=column in RESULT_METRICS,
                    reverse_state=self.aggregated_sort_reverse,
                ),
            )
            self.aggregated_tree.column(
                col,
                anchor="e" if col in RESULT_METRICS else "w",
                width=160,
            )
        self.aggregated_tree.grid(row=1, column=0, sticky="nsew")
        aggregated_scroll = ttk.Scrollbar(
            results_frame, orient="vertical", command=self.aggregated_tree.yview
        )
        aggregated_scroll.grid(row=1, column=1, sticky="ns")
        self.aggregated_tree.configure(yscrollcommand=aggregated_scroll.set)

    def _build_comparison_tab(self) -> None:
        frame = ttk.LabelFrame(self.comparison_tab, text="Scenario Comparison")
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=3)
        frame.rowconfigure(4, weight=2)

        controls = ttk.Frame(frame)
        controls.grid(row=0, column=0, sticky="ew", pady=(4, 6))
        controls.columnconfigure(7, weight=1)
        ttk.Label(controls, text="Scenario A (baseline):").grid(
            row=0, column=0, sticky="w"
        )
        self.baseline_scenario_combo = ttk.Combobox(
            controls,
            textvariable=self.baseline_scenario_var,
            state="readonly",
            width=20,
        )
        self.baseline_scenario_combo.grid(row=0, column=1, padx=(5, 12))
        ttk.Label(controls, text="Scenario B:").grid(row=0, column=2, sticky="w")
        self.comparison_scenario_combo = ttk.Combobox(
            controls,
            textvariable=self.comparison_scenario_var,
            state="readonly",
            width=20,
        )
        self.comparison_scenario_combo.grid(row=0, column=3, padx=(5, 12))
        ttk.Label(controls, text="Technology:").grid(row=0, column=4, sticky="w")
        self.comparison_technology_combo = ttk.Combobox(
            controls,
            textvariable=self.comparison_technology_var,
            state="readonly",
            width=17,
        )
        self.comparison_technology_combo.grid(row=0, column=5, padx=(5, 12))
        ttk.Label(controls, text="Region:").grid(row=0, column=6, sticky="w")
        self.comparison_region_combo = ttk.Combobox(
            controls,
            textvariable=self.comparison_region_var,
            state="readonly",
            width=17,
        )
        self.comparison_region_combo.grid(row=0, column=7, sticky="w", padx=(5, 12))
        ttk.Button(controls, text="Compare", command=self._update_comparison).grid(
            row=0, column=8, padx=(0, 6)
        )
        ttk.Button(controls, text="Export CSV", command=self._export_comparison_csv).grid(
            row=0, column=9, padx=(0, 6)
        )
        ttk.Button(
            controls, text="Export Excel", command=self._export_comparison_excel
        ).grid(row=0, column=10)
        for combo in (
            self.baseline_scenario_combo,
            self.comparison_scenario_combo,
            self.comparison_technology_combo,
            self.comparison_region_combo,
        ):
            combo.bind("<<ComboboxSelected>>", lambda _event: self._update_comparison())

        ttk.Label(
            frame,
            textvariable=self.comparison_status_var,
            foreground="#555555",
            wraplength=980,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 5))

        table_frame = ttk.Frame(frame)
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.comparison_tree = ttk.Treeview(
            table_frame,
            columns=self.comparison_columns,
            show="headings",
            height=12,
        )
        comparison_headings = {
            "Technology": "Technology",
            "Region": "Region",
            "baseline_eligibility_share_%": "A eligibility (%)",
            "comparison_eligibility_share_%": "B eligibility (%)",
            "difference_eligibility_share_pp": "Difference (pp)",
            "baseline_available_area_km2": "A area (km²)",
            "comparison_available_area_km2": "B area (km²)",
            "difference_available_area_km2": "Difference area (km²)",
            "baseline_power_potential_TW": "A power (TW)",
            "comparison_power_potential_TW": "B power (TW)",
            "difference_power_potential_TW": "Difference power (TW)",
        }
        for column in self.comparison_columns:
            numeric = column not in {"Technology", "Region"}
            self.comparison_tree.heading(
                column,
                text=comparison_headings[column],
                command=lambda selected=column, is_numeric=numeric: self._sort_tree_column(
                    self.comparison_tree,
                    selected,
                    numeric=is_numeric,
                    reverse_state=self.comparison_sort_reverse,
                ),
            )
            self.comparison_tree.column(
                column,
                anchor="e" if numeric else "w",
                width=145 if "difference" in column else 120,
                stretch=False,
            )
        self.comparison_tree.grid(row=0, column=0, sticky="nsew")
        comparison_scroll_y = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.comparison_tree.yview
        )
        comparison_scroll_y.grid(row=0, column=1, sticky="ns")
        comparison_scroll_x = ttk.Scrollbar(
            table_frame, orient="horizontal", command=self.comparison_tree.xview
        )
        comparison_scroll_x.grid(row=1, column=0, sticky="ew")
        self.comparison_tree.configure(
            yscrollcommand=comparison_scroll_y.set,
            xscrollcommand=comparison_scroll_x.set,
        )

        chart_controls = ttk.Frame(frame)
        chart_controls.grid(row=3, column=0, sticky="ew", pady=(8, 4))
        ttk.Label(chart_controls, text="Chart by:").pack(side="left")
        chart_group = ttk.Combobox(
            chart_controls,
            textvariable=self.chart_group_var,
            values=("Region", "Technology"),
            state="readonly",
            width=14,
        )
        chart_group.pack(side="left", padx=(5, 12))
        ttk.Label(chart_controls, text="Metric:").pack(side="left")
        chart_metric = ttk.Combobox(
            chart_controls,
            textvariable=self.chart_metric_var,
            values=(
                "Available area (km²)",
                "Eligibility share (pp)",
                "Power potential (TW)",
            ),
            state="readonly",
            width=24,
        )
        chart_metric.pack(side="left", padx=(5, 0))
        chart_group.bind("<<ComboboxSelected>>", lambda _event: self._draw_comparison_chart())
        chart_metric.bind("<<ComboboxSelected>>", lambda _event: self._draw_comparison_chart())

        chart_frame = ttk.LabelFrame(frame, text="Scenario B minus Scenario A")
        chart_frame.grid(row=4, column=0, sticky="nsew")
        chart_frame.columnconfigure(0, weight=1)
        chart_frame.rowconfigure(0, weight=1)
        self.comparison_chart = tk.Canvas(
            chart_frame,
            height=220,
            background="white",
            highlightthickness=0,
        )
        self.comparison_chart.grid(row=0, column=0, sticky="nsew")
        self.comparison_chart.bind(
            "<Configure>", lambda _event: self._draw_comparison_chart()
        )

    def _build_delete_tab(self) -> None:
        frame = ttk.LabelFrame(self.delete_tab, text="Delete Scenario Results")
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=2)
        frame.rowconfigure(4, weight=1)

        ttk.Label(
            frame,
            text="Preview and delete generated files for one scenario.",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text=(
                "Select a scenario, review the exact files, then confirm deletion. "
                "Aggregated outputs are invalidated automatically."
            ),
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Scenario:").grid(row=0, column=0, padx=(0, 6))
        self.delete_scenario_combo = ttk.Combobox(
            controls,
            textvariable=self.delete_scenario_var,
            state="readonly",
            width=32,
        )
        self.delete_scenario_combo.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.delete_scenario_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._preview_selected_scenario()
        )
        ttk.Button(
            controls, text="Refresh", command=self._refresh_delete_scenarios
        ).grid(row=0, column=2, padx=(0, 6))
        self.delete_run_button = ttk.Button(
            controls,
            text="Delete Selected Scenario",
            command=self.handle_delete_run,
        )
        self.delete_run_button.grid(row=0, column=3, padx=(0, 6))
        self.delete_stop_button = ttk.Button(
            controls, text="Stop", command=self.handle_delete_stop, state="disabled"
        )
        self.delete_stop_button.grid(row=0, column=4, padx=(0, 6))
        self.delete_status_label = ttk.Label(controls, text="Status: Idle")
        self.delete_status_label.grid(row=0, column=5, sticky="w")

        preview_frame = ttk.LabelFrame(frame, text="Files to Delete")
        preview_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.delete_preview_tree = ttk.Treeview(
            preview_frame, columns=("path",), show="headings", height=10
        )
        self.delete_preview_tree.heading("path", text="Project-relative path")
        self.delete_preview_tree.column("path", anchor="w", width=800)
        self.delete_preview_tree.grid(row=0, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(
            preview_frame, orient="vertical", command=self.delete_preview_tree.yview
        )
        preview_scroll.grid(row=0, column=1, sticky="ns")
        self.delete_preview_tree.configure(yscrollcommand=preview_scroll.set)

        log_frame = ttk.LabelFrame(frame, text="Script Output")
        log_frame.grid(row=4, column=0, sticky="nsew")
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

        self._refresh_delete_scenarios()
        self._set_delete_running_state(False)

    def _format_command(self, cmd: List[str]) -> str:
        if hasattr(shlex, "join"):
            return shlex.join(cmd)
        return " ".join(cmd)

    def _set_running_state(self, running: bool) -> None:
        blocked = running or self.delete_runner.is_running() or self.external_workflow_active
        self.run_button.configure(state="disabled" if blocked else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self._set_delete_running_state(self.delete_runner.is_running())

    def set_workflow_active(self, active: bool) -> None:
        """Block result mutations while the main Run tab owns the workflow."""
        self.external_workflow_active = active
        self._set_running_state(self.runner.is_running())

    def _ensure_results_idle(self, action: str) -> bool:
        if self.external_workflow_active:
            messagebox.showwarning(
                action,
                "Wait for the active workflow in the Run tab to finish before changing results.",
            )
            return False
        if self.runner.is_running() or self.delete_runner.is_running():
            messagebox.showwarning(
                action, "Wait for the current Results operation to finish."
            )
            return False
        return True

    def has_active_operation(self) -> bool:
        return self.runner.is_running() or self.delete_runner.is_running()

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
            PARENT_DIR / "utils" / script_name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError(
            f"Could not find {script_name} in the expected locations."
        )

    def _resolve_results_json_path(self) -> Path:
        json_path = PARENT_DIR / "aggregated_available_land.json"
        try:
            return json_path.resolve()
        except Exception:
            return json_path

    def handle_run(self) -> None:
        if not self._ensure_results_idle("Results Analysis"):
            return
        try:
            script_path = self._resolve_script_path("results_analysis.py")
        except FileNotFoundError as exc:
            message = str(exc)
            self._append_log("error", message)
            messagebox.showerror("Execution Error", message)
            return
        self.expected_output_dir = PARENT_DIR
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
        command = [
            sys.executable,
            "-u",
            str(script_path),
            "--root",
            str(PARENT_DIR),
            "--output",
            str(PARENT_DIR / "aggregated_available_land.gpkg"),
            "--json-output",
            str(PARENT_DIR / "aggregated_available_land.json"),
            "--csv-output",
            str(PARENT_DIR / "aggregated_available_land.csv"),
        ]
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
        self._refresh_comparison_options()

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

    @staticmethod
    def _sort_tree_column(
        tree: Optional[ttk.Treeview],
        column: str,
        *,
        numeric: bool,
        reverse_state: Dict[str, bool],
    ) -> None:
        if tree is None:
            return
        reverse = reverse_state.get(column, False)
        populated: List[Tuple[Any, str]] = []
        missing: List[Tuple[Any, str]] = []
        for item_id in tree.get_children(""):
            raw = tree.set(item_id, column).strip()
            if numeric:
                value = numeric_result(raw.replace(",", ""))
                (populated if value is not None else missing).append((value, item_id))
            else:
                populated.append((raw.casefold(), item_id))
        populated.sort(key=lambda item: item[0], reverse=reverse)
        for index, (_value, item_id) in enumerate([*populated, *missing]):
            tree.move(item_id, "", index)
        reverse_state[column] = not reverse

    def _refresh_comparison_options(self) -> None:
        scenarios = sorted(
            {str(row.get("Scenario", "")) for row in self.current_aggregated_rows if row.get("Scenario")},
            key=str.casefold,
        )
        technologies = sorted(
            {str(row.get("Technology", "")) for row in self.current_aggregated_rows if row.get("Technology")},
            key=str.casefold,
        )
        regions = sorted(
            {str(row.get("Region", "")) for row in self.current_aggregated_rows if row.get("Region")},
            key=lambda value: (value != "ALL", value.casefold()),
        )
        if self.baseline_scenario_combo:
            self.baseline_scenario_combo.configure(values=scenarios)
        if self.comparison_scenario_combo:
            self.comparison_scenario_combo.configure(values=scenarios)
        if self.comparison_technology_combo:
            self.comparison_technology_combo.configure(values=["All", *technologies])
        if self.comparison_region_combo:
            self.comparison_region_combo.configure(values=["All", *regions])

        if self.baseline_scenario_var.get() not in scenarios:
            self.baseline_scenario_var.set(scenarios[0] if scenarios else "")
        if self.comparison_scenario_var.get() not in scenarios or (
            len(scenarios) > 1
            and self.comparison_scenario_var.get() == self.baseline_scenario_var.get()
        ):
            self.comparison_scenario_var.set(scenarios[1] if len(scenarios) > 1 else "")
        if self.comparison_technology_var.get() not in ["All", *technologies]:
            self.comparison_technology_var.set("All")
        if self.comparison_region_var.get() not in ["All", *regions]:
            self.comparison_region_var.set("All")
        self._update_comparison()

    def _clear_comparison(self, message: str) -> None:
        self.current_comparison_rows = []
        if self.comparison_tree:
            self.comparison_tree.delete(*self.comparison_tree.get_children())
        if self.comparison_chart:
            self.comparison_chart.delete("all")
            self.comparison_chart.create_text(
                12,
                12,
                text=message,
                anchor="nw",
                fill="#555555",
                font=("Segoe UI", 10),
            )
        self.comparison_status_var.set(message)

    def _update_comparison(self) -> None:
        baseline = self.baseline_scenario_var.get().strip()
        comparison = self.comparison_scenario_var.get().strip()
        if not baseline or not comparison:
            self._clear_comparison(
                "Load aggregated results containing at least two scenarios."
            )
            return
        if baseline == comparison:
            self._clear_comparison("Select two different scenarios to compare.")
            return
        technology = self.comparison_technology_var.get().strip()
        region = self.comparison_region_var.get().strip()
        rows = build_scenario_comparison(
            self.current_aggregated_rows,
            baseline,
            comparison,
            technology="" if technology == "All" else technology,
            region="" if region == "All" else region,
        )
        self.current_comparison_rows = rows
        if self.comparison_tree:
            self.comparison_tree.delete(*self.comparison_tree.get_children())
            for row in rows:
                values = []
                for column in self.comparison_columns:
                    value = row.get(column)
                    if isinstance(value, float):
                        rendered = f"{value:+.4f}" if column.startswith("difference_") else f"{value:.4f}"
                        value = rendered.rstrip("0").rstrip(".")
                    values.append("" if value is None else value)
                self.comparison_tree.insert("", "end", values=values)
        complete_rows = sum(
            1
            for row in rows
            if all(row.get(f"baseline_{metric}") is not None for metric in RESULT_METRICS)
            and all(row.get(f"comparison_{metric}") is not None for metric in RESULT_METRICS)
        )
        if rows:
            suffix = ""
            if complete_rows != len(rows):
                suffix = f" {len(rows) - complete_rows} row(s) exist in only one scenario."
            self.comparison_status_var.set(
                f"Comparing {comparison} minus {baseline}: {len(rows)} row(s).{suffix}"
            )
        else:
            self.comparison_status_var.set("No matching technology and region rows were found.")
        self._draw_comparison_chart()

    def _comparison_chart_values(self) -> List[Tuple[str, float]]:
        metric_key = {
            "Available area (km²)": "difference_available_area_km2",
            "Eligibility share (pp)": "difference_eligibility_share_pp",
            "Power potential (TW)": "difference_power_potential_TW",
        }[self.chart_metric_var.get()]
        group_column = self.chart_group_var.get()
        candidate_rows = self.current_comparison_rows
        if group_column == "Technology":
            aggregated_rows = [row for row in candidate_rows if row.get("Region") == "ALL"]
            if aggregated_rows:
                candidate_rows = aggregated_rows
        else:
            candidate_rows = [row for row in candidate_rows if row.get("Region") != "ALL"]
        grouped: Dict[str, List[float]] = {}
        for row in candidate_rows:
            label = str(row.get(group_column, ""))
            value = numeric_result(row.get(metric_key))
            if label and value is not None:
                grouped.setdefault(label, []).append(value)
        average = metric_key == "difference_eligibility_share_pp"
        values = [
            (label, sum(items) / len(items) if average else sum(items))
            for label, items in grouped.items()
            if items
        ]
        return sorted(values, key=lambda item: abs(item[1]), reverse=True)[:20]

    def _draw_comparison_chart(self) -> None:
        canvas = self.comparison_chart
        if canvas is None:
            return
        canvas.delete("all")
        values = self._comparison_chart_values() if self.current_comparison_rows else []
        width = max(canvas.winfo_width(), 500)
        height = max(canvas.winfo_height(), 200)
        if not values:
            canvas.create_text(
                12,
                12,
                text="No comparable values available for this chart.",
                anchor="nw",
                fill="#555555",
                font=("Segoe UI", 10),
            )
            return
        left, right, top, bottom = 58, 18, 18, 58
        plot_width = max(1, width - left - right)
        plot_height = max(1, height - top - bottom)
        minimum = min(0.0, *(value for _label, value in values))
        maximum = max(0.0, *(value for _label, value in values))
        if minimum == maximum:
            minimum, maximum = -1.0, 1.0

        def y_position(value: float) -> float:
            return top + (maximum - value) / (maximum - minimum) * plot_height

        zero_y = y_position(0.0)
        canvas.create_line(left, zero_y, width - right, zero_y, fill="#777777")
        canvas.create_text(
            left - 6, zero_y, text="0", anchor="e", fill="#555555", font=("Segoe UI", 8)
        )
        slot = plot_width / len(values)
        bar_width = max(4.0, min(48.0, slot * 0.62))
        for index, (label, value) in enumerate(values):
            center = left + slot * (index + 0.5)
            value_y = y_position(value)
            color = "#1A7F37" if value >= 0 else "#B42318"
            canvas.create_rectangle(
                center - bar_width / 2,
                min(zero_y, value_y),
                center + bar_width / 2,
                max(zero_y, value_y),
                fill=color,
                outline=color,
            )
            canvas.create_text(
                center,
                value_y - 5 if value >= 0 else value_y + 5,
                text=f"{value:+.3g}",
                anchor="s" if value >= 0 else "n",
                fill=color,
                font=("Segoe UI", 8),
            )
            canvas.create_text(
                center,
                height - bottom + 7,
                text=label,
                anchor="ne",
                angle=35,
                fill="#333333",
                font=("Segoe UI", 8),
            )

    def _comparison_export_fields(self) -> List[Tuple[str, str]]:
        baseline = self.baseline_scenario_var.get().strip() or "Scenario A"
        comparison = self.comparison_scenario_var.get().strip() or "Scenario B"
        return [
            ("Technology", "Technology"),
            ("Region", "Region"),
            (f"{baseline} eligibility share (%)", "baseline_eligibility_share_%"),
            (f"{comparison} eligibility share (%)", "comparison_eligibility_share_%"),
            ("Difference eligibility (percentage points)", "difference_eligibility_share_pp"),
            (f"{baseline} available area (km²)", "baseline_available_area_km2"),
            (f"{comparison} available area (km²)", "comparison_available_area_km2"),
            ("Difference available area (km²)", "difference_available_area_km2"),
            (f"{baseline} power potential (TW)", "baseline_power_potential_TW"),
            (f"{comparison} power potential (TW)", "comparison_power_potential_TW"),
            ("Difference power potential (TW)", "difference_power_potential_TW"),
        ]

    def _comparison_export_path(self, extension: str) -> Optional[Path]:
        if not self.current_comparison_rows:
            messagebox.showwarning("Export Comparison", "Create a scenario comparison first.")
            return None
        baseline = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.baseline_scenario_var.get())
        comparison = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.comparison_scenario_var.get())
        filename = filedialog.asksaveasfilename(
            title="Export scenario comparison",
            initialdir=str(PARENT_DIR),
            initialfile=f"{baseline}_vs_{comparison}_comparison.{extension}",
            defaultextension=f".{extension}",
            filetypes=[
                ("CSV files", "*.csv") if extension == "csv" else ("Excel workbooks", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        return Path(filename) if filename else None

    def _export_comparison_csv(self) -> None:
        path = self._comparison_export_path("csv")
        if path is None:
            return
        fields = self._comparison_export_fields()
        try:
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow([heading for heading, _key in fields])
                for row in self.current_comparison_rows:
                    writer.writerow([row.get(key, "") for _heading, key in fields])
        except OSError as exc:
            messagebox.showerror("Export Comparison", f"Could not write CSV:\n{exc}")
            return
        messagebox.showinfo("Export Comparison", f"Saved comparison to:\n{path}")

    def _export_comparison_excel(self) -> None:
        path = self._comparison_export_path("xlsx")
        if path is None:
            return
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
        except ImportError:
            messagebox.showerror(
                "Export Comparison",
                "Excel export requires openpyxl. Install it in the lava environment with "
                "'conda install openpyxl' or use CSV export.",
            )
            return
        fields = self._comparison_export_fields()
        try:
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Scenario comparison"
            sheet.append([heading for heading, _key in fields])
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            for row in self.current_comparison_rows:
                sheet.append([row.get(key) for _heading, key in fields])
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column_cells in sheet.columns:
                width = min(
                    42,
                    max(len(str(cell.value or "")) for cell in column_cells) + 2,
                )
                sheet.column_dimensions[column_cells[0].column_letter].width = width
            workbook.save(path)
        except Exception as exc:
            messagebox.showerror("Export Comparison", f"Could not write Excel file:\n{exc}")
            return
        messagebox.showinfo("Export Comparison", f"Saved comparison to:\n{path}")

    def _update_delete_status(self) -> None:
        if self.delete_status_label:
            self.delete_status_label.configure(
                text=f"Status: {self.delete_status.capitalize()}"
            )

    def _set_delete_running_state(self, running: bool) -> None:
        if self.delete_run_button:
            blocked = (
                running
                or self.runner.is_running()
                or self.external_workflow_active
                or not self.delete_preview_files
            )
            self.delete_run_button.configure(state="disabled" if blocked else "normal")
        if self.delete_stop_button:
            self.delete_stop_button.configure(state="normal" if running else "disabled")

    def _refresh_delete_scenarios(self) -> None:
        try:
            scenarios = discover_scenarios(PARENT_DIR)
        except ResultsDeletionError as exc:
            scenarios = []
            self._delete_append_log("error", str(exc))
        if self.delete_scenario_combo:
            self.delete_scenario_combo.configure(values=scenarios)
        current = self.delete_scenario_var.get()
        if current not in scenarios:
            self.delete_scenario_var.set(scenarios[0] if scenarios else "")
        self._preview_selected_scenario()

    def _preview_selected_scenario(self) -> None:
        scenario = self.delete_scenario_var.get().strip()
        try:
            files = collect_scenario_files(PARENT_DIR, scenario) if scenario else []
        except ResultsDeletionError as exc:
            files = []
            self._delete_append_log("error", str(exc))
        self.delete_preview_files = files
        if self.delete_preview_tree:
            self.delete_preview_tree.delete(*self.delete_preview_tree.get_children())
            for path in files:
                try:
                    display = path.relative_to(PARENT_DIR)
                except ValueError:
                    display = path
                self.delete_preview_tree.insert("", "end", values=(str(display),))
        self._set_delete_running_state(self.delete_runner.is_running())

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
        if not self._ensure_results_idle("Delete Scenario Results"):
            return
        scenario = self.delete_scenario_var.get().strip()
        self._preview_selected_scenario()
        if not scenario or not self.delete_preview_files:
            messagebox.showwarning(
                "Delete Scenario Results", "Select a scenario that has generated files."
            )
            return
        if not messagebox.askyesno(
            "Confirm Scenario Deletion",
            f"Permanently delete {len(self.delete_preview_files)} generated file(s) "
            f"for scenario '{scenario}'?\n\nAggregated result files will also be removed "
            "because they would otherwise be stale.",
            icon="warning",
        ):
            return
        try:
            script_path = self._resolve_script_path("delete_scenario_results.py")
        except FileNotFoundError as exc:
            message = str(exc)
            self._delete_append_log("error", message)
            messagebox.showerror("Execution Error", message)
            return
        self.delete_expected_dir = PARENT_DIR
        self.delete_status = "running"
        self._set_delete_running_state(True)
        self._set_running_state(self.runner.is_running())
        self._update_delete_status()
        self._delete_clear_log()
        command = [
            sys.executable,
            "-u",
            str(script_path),
            "--root",
            str(PARENT_DIR),
            "--scenario",
            scenario,
            "--yes",
        ]
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

    def _handle_delete_output(self, level: str, message: str) -> None:
        self._delete_append_log(level, message)

    def _handle_delete_exit(self, return_code: int) -> None:
        self.delete_runner.cancel()
        if return_code == 0 and self.delete_status != "stopping":
            self.delete_status = "completed"
            self._delete_append_log("success", "Process completed successfully.")
            self.clear_aggregated_results()
            self._refresh_delete_scenarios()
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
        self._set_running_state(self.runner.is_running())
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
        self._refresh_comparison_options()

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
