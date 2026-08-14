"""Interactive map tab and region-layer preset discovery."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

from rasterio.warp import transform_geom

if __package__:
    from .map_renderer import (
        _extract_geojson_bounds,
        build_map_html,
        geotiff_to_png_with_bounds,
        show_map_in_tk,
    )
else:
    from map_renderer import (  # type: ignore
        _extract_geojson_bounds,
        build_map_html,
        geotiff_to_png_with_bounds,
        show_map_in_tk,
    )


PARENT_DIR = Path(__file__).resolve().parent.parent


class MapTab(ttk.Frame):
    MAX_LAYERS = 3
    SUPPORTED_SUFFIXES = {".tif", ".tiff", ".geojson", ".gpkg"}
    FILETYPES = [
        ("Supported files", "*.tif *.tiff *.geojson *.gpkg"),
        ("GeoTIFF", "*.tif *.tiff"),
        ("GeoJSON", "*.geojson"),
        ("GeoPackage", "*.gpkg"),
    ]

    def __init__(self, master: tk.Widget):
        super().__init__(master)
        self.file_vars = [tk.StringVar() for _ in range(self.MAX_LAYERS)]
        self.layer_order = [
            tk.StringVar(value=str(i + 1)) for i in range(self.MAX_LAYERS)
        ]
        self.layer_opacity = [tk.DoubleVar(value=0.7) for _ in range(self.MAX_LAYERS)]
        self.layer_names = [tk.StringVar(value="") for _ in range(self.MAX_LAYERS)]
        self.preset_region_var = tk.StringVar()
        self.preset_layer_var = tk.StringVar()
        self.preset_region_combo: Optional[ttk.Combobox] = None
        self.preset_layer_combo: Optional[ttk.Combobox] = None
        self.preset_add_button: Optional[ttk.Button] = None
        self.preset_regions: Dict[str, List[Path]] = {}
        self.preset_layer_paths: Dict[str, Path] = {}
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
        self.rowconfigure(4, weight=1)
        self._build_ui()
        self.bind("<Destroy>", self._on_destroy)

    def _build_ui(self) -> None:
        presets = ttk.LabelFrame(self, text="Available Region Layers")
        presets.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        presets.columnconfigure(3, weight=1)
        ttk.Label(presets, text="Region:").grid(
            row=0, column=0, sticky="w", padx=(8, 6), pady=8
        )
        self.preset_region_combo = ttk.Combobox(
            presets,
            textvariable=self.preset_region_var,
            state="readonly",
            width=24,
        )
        self.preset_region_combo.grid(row=0, column=1, sticky="w", pady=8)
        self.preset_region_combo.bind(
            "<<ComboboxSelected>>", self._on_preset_region_selected
        )
        ttk.Label(presets, text="Available layer:").grid(
            row=0, column=2, sticky="e", padx=(18, 6), pady=8
        )
        self.preset_layer_combo = ttk.Combobox(
            presets,
            textvariable=self.preset_layer_var,
            state="readonly",
        )
        self.preset_layer_combo.grid(row=0, column=3, sticky="ew", pady=8)
        self.preset_add_button = ttk.Button(
            presets,
            text="Add to Layer Selection",
            command=self._add_preset_layer,
            state="disabled",
        )
        self.preset_add_button.grid(row=0, column=4, padx=(6, 0), pady=8)
        ttk.Button(
            presets, text="Refresh", command=self._refresh_preset_regions
        ).grid(row=0, column=5, padx=8, pady=8)
        ttk.Label(
            presets,
            text=(
                "Layers are discovered from data/<region>. Temporary and old-resolution "
                "backup files are omitted."
            ),
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=6, sticky="w", padx=8, pady=(0, 8))

        selection = ttk.LabelFrame(self, text="Layer Selection")
        selection.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
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
        buttons.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
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
        self.status_label.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 5))

        map_and_legend = ttk.Frame(self)
        map_and_legend.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 10))
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
        self._refresh_preset_regions()

    @classmethod
    def _discover_region_layers(cls, data_dir: Path) -> Dict[str, List[Path]]:
        """Return supported, user-facing map files grouped by data region."""
        regions: Dict[str, List[Path]] = {}
        if not data_dir.is_dir():
            return regions
        for region_dir in sorted(
            (path for path in data_dir.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        ):
            files = sorted(
                (
                    path
                    for path in region_dir.rglob("*")
                    if path.is_file()
                    and path.suffix.lower() in cls.SUPPORTED_SUFFIXES
                    and not path.name.startswith(".")
                    and ".old_resolution." not in path.name.lower()
                ),
                key=lambda path: str(path.relative_to(region_dir)).casefold(),
            )
            if files:
                regions[region_dir.name] = files
        return regions

    @staticmethod
    def _crs_label(stem: str) -> str:
        match = re.search(r"(EPSG\d+)", stem, re.IGNORECASE)
        return match.group(1).upper() if match else "native CRS"

    @classmethod
    def _preset_layer_label(cls, region: str, path: Path) -> str:
        """Build a concise label for commonly generated LAVA map layers."""
        stem = path.stem
        lower = stem.lower()
        crs = cls._crs_label(stem)
        parent = path.parent.name
        if parent == "available_land":
            content = stem.removeprefix(f"{region}_")
            resource_values = content.endswith("_available_land_ResourceValues")
            suffix = (
                "_available_land_ResourceValues"
                if resource_values
                else "_available_land"
            )
            identity = content.removesuffix(suffix)
            technology, separator, scenario = identity.partition("_")
            technology_labels = {
                "onshorewind": "Onshore wind",
                "offshorewind": "Offshore wind",
                "solar": "Solar",
            }
            technology = technology_labels.get(
                technology, technology.replace("_", " ").title()
            )
            result_type = "Resource values" if resource_values else "Available land"
            details = f"{technology} · {scenario}" if separator else technology
            return f"{result_type} — {details}"
        if path.suffix.lower() == ".geojson" and lower.startswith(region.lower()):
            return f"Study-area boundary — {crs}"
        if "landcover" in lower:
            style = "colored" if "colored" in lower else crs
            return f"Land cover — {style}"
        if lower.startswith("population_"):
            return f"Population — {crs}"
        if lower.startswith("protected_areas"):
            return f"Protected areas — {crs}"
        if lower.startswith("dem_buffered"):
            return f"Elevation (buffered) — {crs}"
        if lower.startswith("dem_"):
            return f"Elevation — {crs}"
        if lower.startswith("wind_"):
            return f"Wind resource — {crs}"
        if lower.startswith("solar_"):
            return f"Solar resource — {crs}"
        if lower.startswith("goas_"):
            return f"Global atlas grid — {crs}"
        if parent == "derived_from_DEM":
            measure = "Slope" if lower.startswith("slope_") else "Aspect"
            return f"{measure} — {crs}"
        if parent == "OSM_Infrastructure":
            return f"OSM infrastructure — {stem.replace('_', ' ').title()}"
        relative_parent = parent.replace("_", " ").title()
        return f"{relative_parent} — {stem.replace('_', ' ')}"

    def _refresh_preset_regions(self) -> None:
        self.preset_regions = self._discover_region_layers(PARENT_DIR / "data")
        region_names = list(self.preset_regions)
        if self.preset_region_combo:
            self.preset_region_combo.configure(values=region_names)
        current = self.preset_region_var.get()
        if current not in self.preset_regions:
            self.preset_region_var.set(region_names[0] if region_names else "")
        self._on_preset_region_selected()
        if not region_names:
            self._set_status(
                f"No supported map layers were found below {PARENT_DIR / 'data'}.",
                "warning",
            )

    def _on_preset_region_selected(self, _event: Optional[tk.Event] = None) -> None:
        region = self.preset_region_var.get().strip()
        available = self.preset_regions.get(region, [])
        labels: Dict[str, Path] = {}
        for path in available:
            label = self._preset_layer_label(region, path)
            if label in labels:
                relative = path.relative_to(PARENT_DIR / "data" / region)
                label = f"{label} [{relative}]"
            labels[label] = path
        self.preset_layer_paths = labels
        values = list(labels)
        if self.preset_layer_combo:
            self.preset_layer_combo.configure(values=values)
        self.preset_layer_var.set(values[0] if values else "")
        if self.preset_add_button:
            self.preset_add_button.configure(state="normal" if values else "disabled")
        if region:
            self._set_status(
                f"Found {len(values)} available map layer(s) for {region}.",
                "success" if values else "warning",
            )

    def _add_preset_layer(self) -> None:
        label = self.preset_layer_var.get().strip()
        path = self.preset_layer_paths.get(label)
        if path is None:
            messagebox.showwarning("Add Region Layer", "Select an available layer first.")
            return
        resolved = str(path.resolve())
        if any(var.get().strip() == resolved for var in self.file_vars):
            self._set_status(f"{label} is already selected.", "warning")
            return
        slot = next(
            (index for index, variable in enumerate(self.file_vars) if not variable.get().strip()),
            None,
        )
        if slot is None:
            messagebox.showwarning(
                "Add Region Layer",
                "All three layer slots are in use. Clear a slot before adding another layer.",
            )
            return
        self.file_vars[slot].set(resolved)
        self.layer_names[slot].set(label)
        self._set_status(f"Added {label} as layer {slot + 1}.", "success")

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
                elif suffix == ".gpkg":
                    import fiona

                    layer_names = fiona.listlayers(path)
                    if not layer_names:
                        raise ValueError("The GeoPackage contains no vector layers.")
                    for layer_name in layer_names:
                        with fiona.open(path, layer=layer_name) as source:
                            source_crs = source.crs_wkt or source.crs
                            if not source_crs:
                                raise ValueError(
                                    f"GeoPackage layer '{layer_name}' has no coordinate reference system."
                                )
                            features = []
                            for feature in source:
                                geometry = feature.get("geometry")
                                if geometry is None:
                                    continue
                                features.append(
                                    {
                                        "type": "Feature",
                                        "properties": dict(feature.get("properties") or {}),
                                        "geometry": transform_geom(
                                            source_crs, "EPSG:4326", dict(geometry)
                                        ),
                                    }
                                )
                        if not features:
                            continue
                        geojson_data = {
                            "type": "FeatureCollection",
                            "features": features,
                        }
                        layers.append(
                            {
                                "type": "geojson",
                                "name": f"{path.name}:{layer_name}",
                                "display_name": (
                                    display_name
                                    if len(layer_names) == 1
                                    else f"{display_name} - {layer_name}"
                                ),
                                "data": geojson_data,
                                "bounds": _extract_geojson_bounds(geojson_data),
                                "opacity": opacity_value,
                                "order": order_value,
                                "index": idx,
                            }
                        )
                    if not any(layer["index"] == idx for layer in layers):
                        raise ValueError("The GeoPackage contains no non-empty vector layers.")
                else:
                    raise ValueError(
                        "Unsupported file type. Choose .tif, .tiff, .geojson, or .gpkg."
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
        browser_opened = bool(self._map_view.get("opened")) if self._map_view else False
        if browser_opened:
            self._set_status(
                f"Loaded {len(layers)} layer(s) in your default browser.", "success"
            )
        else:
            self._set_status(
                "The map was created, but the browser could not be opened automatically.",
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
        try:
            children = list(self.map_container.winfo_children())
        except tk.TclError:
            children = []
        for child in children:
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
