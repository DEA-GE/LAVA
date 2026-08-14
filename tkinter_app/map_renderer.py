"""GeoTIFF conversion and browser-based Folium map rendering."""

from __future__ import annotations

import html
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import folium
import numpy as np
import rasterio
import tkinter as tk
from branca.element import MacroElement, Template
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from tkinter import ttk


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


def show_map_in_tk(html_path: str, parent: tk.Widget) -> Dict[str, Any]:
    """Open the interactive map in the system browser.

    Browser display is intentional: Folium and Leaflet receive a complete,
    maintained browser runtime without coupling the Tkinter application to an
    embedded WebView implementation.
    """
    target = Path(html_path).resolve()
    info = "Interactive map opened in your default browser."
    label = ttk.Label(
        parent, text=info, foreground="#1a7f37", wraplength=420, justify="left"
    )
    label.pack(fill="x", padx=10, pady=8)
    opened = webbrowser.open_new_tab(target.as_uri())
    if not opened:
        label.configure(
            text=(
                "The map was created, but the operating system did not confirm "
                f"that it opened a browser. Open it manually: {target}"
            ),
            foreground="#b42318",
        )
    return {
        "embedded": False,
        "opened": opened,
        "widget": label,
        "cleanup": lambda: None,
    }

