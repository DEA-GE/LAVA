"""Tkinter-based translation of the Python Script Manager interface."""

from __future__ import annotations

import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import geopandas as gpd  # noqa: F401  # Load GEOS before rasterio/GDAL on Windows.

try:  # Optional ttkbootstrap theming
    from ttkbootstrap import Style  # type: ignore

    HAVE_TTKBOOTSTRAP = True
except Exception:  # pragma: no cover - optional dependency
    HAVE_TTKBOOTSTRAP = False
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
CONFIGS_DIR = PARENT_DIR / "configs"
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))
if str(PARENT_DIR) not in sys.path:
    sys.path.append(str(PARENT_DIR))
from data_loader import (  # type: ignore  # noqa: E402
    load_initial_sections,
    load_sample_results,
)
if __package__:
    from .configuration_tab import ConfigurationTab  # noqa: E402
    from .documentation_tab import DocumentationTab  # noqa: E402
    from .results_tab import ResultsTab  # noqa: E402
    from .run_tab import RunTab  # noqa: E402
else:
    from configuration_tab import ConfigurationTab  # type: ignore  # noqa: E402
    from documentation_tab import DocumentationTab  # type: ignore  # noqa: E402
    from results_tab import ResultsTab  # type: ignore  # noqa: E402
    from run_tab import RunTab  # type: ignore  # noqa: E402
from utils.initialization import (  # noqa: E402
    available_example_countries,
    initialize_config_templates,
    preview_config_templates,
)
from utils.gadm_levels_to_geojson import (  # noqa: E402
    GADMExtractionResult,
    extract_gadm_levels,
)
REQUIRED_ACTIVE_CONFIGS = (
    "config.yaml",
    "onshorewind.yaml",
    "solar.yaml",
)
OPTIONAL_ACTIVE_CONFIGS = (
    "suitability.yaml",
    "config_snakemake.yaml",
)

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












class ConfigurationSetupDialog(tk.Toplevel):
    """Initialize active configuration files before opening their editors."""

    def __init__(self, master: tk.Widget, on_complete: Callable[[], None]) -> None:
        super().__init__(master)
        self.title("Configuration Setup")
        self.geometry("820x700")
        self.minsize(720, 620)
        self.transient(master)
        self.on_complete = on_complete
        self.source_var = tk.StringVar(value="default")
        self.country_var = tk.StringVar()
        self.overwrite_var = tk.BooleanVar(value=False)
        self.prepare_study_areas_var = tk.BooleanVar(value=False)
        self.gadm_input_var = tk.StringVar()
        self.gadm_level_var = tk.IntVar(value=1)
        self.gadm_output_var = tk.StringVar(
            value=str(
                PARENT_DIR
                / "Raw_Spatial_Data"
                / "custom_study_area"
                / "gadm_areas"
            )
        )
        self.gadm_overwrite_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar()
        self._setup_running = False
        self._study_area_queue: queue.Queue[Tuple[Any, ...]] = queue.Queue()
        self._study_area_after_id: Optional[str] = None
        self.countries = available_example_countries(CONFIGS_DIR)
        if self.countries:
            self.country_var.set(self.countries[0])
        self._build_ui()
        self._refresh_preview()
        self.protocol("WM_DELETE_WINDOW", self._close)
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

        study_area = ttk.LabelFrame(
            body, text="Optional study-area preparation", padding=10
        )
        study_area.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        study_area.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            study_area,
            text="Split a GADM dataset into individual study-area GeoJSON files",
            variable=self.prepare_study_areas_var,
            command=self._toggle_study_area_controls,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            study_area,
            text=(
                "Each named area at the selected administrative level is written to "
                "a collection folder under Raw_Spatial_Data/custom_study_area and "
                "listed in that folder's processed_areas_list.json. Use a distinct "
                "folder for each dataset or administrative level."
            ),
            foreground="#555555",
            wraplength=740,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(3, 7))
        study_controls = ttk.Frame(study_area)
        study_controls.grid(row=2, column=0, sticky="ew")
        study_controls.columnconfigure(1, weight=1)
        ttk.Label(study_controls, text="GADM dataset:").grid(
            row=0, column=0, sticky="w", pady=2
        )
        gadm_input_entry = ttk.Entry(study_controls, textvariable=self.gadm_input_var)
        gadm_input_entry.grid(row=0, column=1, sticky="ew", padx=(8, 6), pady=2)
        gadm_input_button = ttk.Button(
            study_controls, text="Browse...", command=self._browse_gadm_input
        )
        gadm_input_button.grid(row=0, column=2, pady=2)
        ttk.Label(study_controls, text="Administrative level:").grid(
            row=1, column=0, sticky="w", pady=2
        )
        gadm_level_spinbox = ttk.Spinbox(
            study_controls,
            textvariable=self.gadm_level_var,
            from_=0,
            to=9,
            increment=1,
            width=6,
        )
        gadm_level_spinbox.grid(row=1, column=1, sticky="w", padx=(8, 6), pady=2)
        ttk.Label(study_controls, text="Output folder:").grid(
            row=2, column=0, sticky="w", pady=2
        )
        gadm_output_entry = ttk.Entry(study_controls, textvariable=self.gadm_output_var)
        gadm_output_entry.grid(row=2, column=1, sticky="ew", padx=(8, 6), pady=2)
        gadm_output_button = ttk.Button(
            study_controls, text="Browse...", command=self._browse_gadm_output
        )
        gadm_output_button.grid(row=2, column=2, pady=2)
        gadm_overwrite_check = ttk.Checkbutton(
            study_controls,
            text="Replace existing area files with matching names",
            variable=self.gadm_overwrite_var,
        )
        gadm_overwrite_check.grid(
            row=3, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(3, 0)
        )
        self.study_area_widgets = (
            gadm_input_entry,
            gadm_input_button,
            gadm_level_spinbox,
            gadm_output_entry,
            gadm_output_button,
            gadm_overwrite_check,
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self._close).pack(
            side="right", padx=(8, 0)
        )
        self.initialize_button = ttk.Button(
            buttons, text="Initialize and Continue", command=self._initialize
        )
        self.initialize_button.pack(side="right")
        self._toggle_study_area_controls()
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

    def _close(self) -> None:
        if self._setup_running:
            return
        self.destroy()

    def _toggle_study_area_controls(self) -> None:
        state = "normal" if self.prepare_study_areas_var.get() else "disabled"
        for widget in self.study_area_widgets:
            widget.configure(state=state)

    def _browse_gadm_input(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Select GADM dataset",
            initialdir=str(PARENT_DIR / "Raw_Spatial_Data" / "custom_study_area"),
            filetypes=(
                ("Geospatial files", "*.geojson *.json *.gpkg *.shp"),
                ("GeoJSON", "*.geojson *.json"),
                ("GeoPackage", "*.gpkg"),
                ("Shapefile", "*.shp"),
                ("All files", "*.*"),
            ),
        )
        if selected:
            self.gadm_input_var.set(selected)

    def _browse_gadm_output(self) -> None:
        selected = filedialog.askdirectory(
            parent=self,
            title="Select study-area output folder",
            initialdir=self.gadm_output_var.get() or str(PARENT_DIR),
        )
        if selected:
            self.gadm_output_var.set(selected)

    @staticmethod
    def _resolve_setup_path(value: str) -> Path:
        expanded = Path(os.path.expandvars(value.strip())).expanduser()
        if not expanded.is_absolute():
            expanded = PARENT_DIR / expanded
        return expanded.resolve()

    def _study_area_options(self) -> Optional[Dict[str, Any]]:
        if not self.prepare_study_areas_var.get():
            return None
        input_text = self.gadm_input_var.get().strip()
        output_text = self.gadm_output_var.get().strip()
        if not input_text:
            raise ValueError("Select a GADM input dataset.")
        if not output_text:
            raise ValueError("Select a study-area output folder.")
        input_path = self._resolve_setup_path(input_text)
        if not input_path.is_file():
            raise FileNotFoundError(f"GADM input file not found: {input_path}")
        try:
            level = int(self.gadm_level_var.get())
        except (tk.TclError, TypeError, ValueError) as exc:
            raise ValueError(
                "Administrative level must be a non-negative integer."
            ) from exc
        if level < 0:
            raise ValueError("Administrative level must be a non-negative integer.")
        output_path = self._resolve_setup_path(output_text)
        custom_root = (
            PARENT_DIR / "Raw_Spatial_Data" / "custom_study_area"
        ).resolve()
        try:
            relative_output = output_path.relative_to(custom_root)
        except ValueError as exc:
            raise ValueError(
                "The output must be a named collection folder below "
                f"{custom_root}."
            ) from exc
        if relative_output == Path("."):
            raise ValueError(
                "Choose or create a named collection folder below "
                f"{custom_root}; do not write GeoJSON files directly into it."
            )
        return {
            "input_path": input_path,
            "gadm_level": level,
            "output_folder": output_path,
            "overwrite": self.gadm_overwrite_var.get(),
        }

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
        try:
            study_area_options = self._study_area_options()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Study-area preparation", str(exc), parent=self)
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
        if study_area_options and study_area_options["overwrite"]:
            confirmed = messagebox.askyesno(
                "Replace Study-area Files",
                "Replace existing GeoJSON files when their generated area names match?",
                parent=self,
            )
            if not confirmed:
                return
        if study_area_options:
            self._setup_running = True
            self.initialize_button.configure(state="disabled")
            self.status_var.set("Preparing study-area GeoJSON files...")
            self._study_area_queue = queue.Queue()
            worker = threading.Thread(
                target=self._prepare_study_areas_worker,
                args=(study_area_options, country, overwrite, pairs),
                daemon=True,
            )
            worker.start()
            self._poll_study_area_worker()
            return
        self._complete_initialization(country, overwrite, pairs, None)

    def _prepare_study_areas_worker(
        self,
        options: Dict[str, Any],
        country: Optional[str],
        overwrite_configs: bool,
        pairs: List[Tuple[Path, Path]],
    ) -> None:
        try:
            result = extract_gadm_levels(
                options["input_path"],
                gadm_level=options["gadm_level"],
                output_folder=options["output_folder"],
                overwrite=options["overwrite"],
            )
        except Exception as exc:
            self._study_area_queue.put(("error", str(exc)))
            return
        self._study_area_queue.put(
            ("success", result, country, overwrite_configs, pairs)
        )

    def _poll_study_area_worker(self) -> None:
        self._study_area_after_id = None
        try:
            item = self._study_area_queue.get_nowait()
        except queue.Empty:
            if self._setup_running:
                self._study_area_after_id = self.after(
                    100, self._poll_study_area_worker
                )
            return
        if item[0] == "error":
            self._study_area_failed(str(item[1]))
            return
        _, result, country, overwrite_configs, pairs = item
        self._complete_initialization(
            country, overwrite_configs, pairs, result
        )

    def _study_area_failed(self, detail: str) -> None:
        self._setup_running = False
        self.initialize_button.configure(state="normal")
        self.status_var.set("Study-area preparation failed.")
        messagebox.showerror("Study-area Preparation Failed", detail, parent=self)

    def _complete_initialization(
        self,
        country: Optional[str],
        overwrite: bool,
        pairs: List[Tuple[Path, Path]],
        study_area_result: Optional[GADMExtractionResult],
    ) -> None:
        try:
            changed = initialize_config_templates(
                CONFIGS_DIR, overwrite=overwrite, country=country
            )
        except Exception as exc:
            self._setup_running = False
            self.initialize_button.configure(state="normal")
            messagebox.showerror(
                "Configuration Setup", f"Initialization failed:\n{exc}", parent=self
            )
            return
        missing = [target for _, target in pairs if not target.exists()]
        if missing:
            self._setup_running = False
            self.initialize_button.configure(state="normal")
            self.status_var.set("Configuration initialization was incomplete.")
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
        if study_area_result is not None:
            created_message += (
                f"\n\nPrepared {len(study_area_result.area_names)} study area(s): "
                f"{len(study_area_result.created_files)} written and "
                f"{len(study_area_result.skipped_files)} kept."
            )
        messagebox.showinfo("Configuration Setup", created_message, parent=self)
        self._setup_running = False
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
        self.state("zoomed")
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
        self.documentation_tab = DocumentationTab(self.notebook)
        self.notebook.add(self.documentation_tab, text="Documentation")
        self.notebook_tabs.extend(
            [self.run_tab, self.results_tab, self.documentation_tab]
        )
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
