from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from numbers import Real
from typing import Any

import atlite
import geopandas as gpd
import numpy as np
import rasterio
from atlite.gis import shape_availability
from rasterio.enums import Resampling
from rasterio.mask import mask
from rasterio.vrt import WarpedVRT
from shapely.geometry import mapping
from utils.data_preprocessing import geopandas_clip_reproject


MANIFEST_FILENAME = "manifest.json"
SUPPORTED_COMBINE_MODES = {"all", "any"}
SUPPORTED_LAYER_TYPES = {"polygon", "raster"}


def _validate_layer_options(
    options: Mapping[str, Any], layer_type: str, context: str
) -> dict[str, Any]:
    if layer_type not in SUPPORTED_LAYER_TYPES:
        raise ValueError(f"Unsupported inclusion layer type: {layer_type}")

    defaults = {"buffer": 0}
    allowed_keys = {"buffer"}
    if layer_type == "raster":
        defaults.update({"codes": [1], "nodata": 0})
        allowed_keys.update({"codes", "nodata"})

    unknown_keys = set(options) - allowed_keys
    if unknown_keys:
        raise ValueError(
            f"Unsupported settings in {context}: {sorted(unknown_keys)}"
        )

    normalized = {**defaults, **options}
    buffer_value = normalized["buffer"]
    if (
        not isinstance(buffer_value, Real)
        or isinstance(buffer_value, bool)
        or buffer_value < 0
    ):
        raise ValueError(f"{context}.buffer must be a non-negative number")

    if layer_type == "raster":
        codes = normalized["codes"]
        if isinstance(codes, int) and not isinstance(codes, bool):
            codes = [codes]
        elif isinstance(codes, (list, tuple)) and codes:
            codes = list(codes)
        else:
            raise ValueError(
                f"{context}.codes must be an integer or a non-empty list"
            )
        if not all(
            isinstance(code, int) and not isinstance(code, bool) for code in codes
        ):
            raise ValueError(f"{context}.codes must contain integers")
        normalized["codes"] = codes

        nodata = normalized["nodata"]
        if not isinstance(nodata, Real) or isinstance(nodata, bool):
            raise ValueError(f"{context}.nodata must be a number")

    return normalized


def parse_inclusion_layer_settings(
    tech_config: Mapping[str, Any], config_key: str, layer_type: str
) -> dict[str, Any] | None:
    """Validate a polygon or raster inclusion configuration block."""
    raw_settings = tech_config.get(config_key)
    if raw_settings is None:
        return None
    if not isinstance(raw_settings, Mapping):
        raise ValueError(f"{config_key} must be a YAML mapping")

    allowed_keys = {"enabled", "combine", "defaults", "overrides"}
    unknown_keys = set(raw_settings) - allowed_keys
    if unknown_keys:
        raise ValueError(
            f"Unsupported settings in {config_key}: {sorted(unknown_keys)}"
        )

    enabled = raw_settings.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError(f"{config_key}.enabled must be true or false")

    combine = str(raw_settings.get("combine", "all")).lower()
    if combine not in SUPPORTED_COMBINE_MODES:
        raise ValueError(f"{config_key}.combine must be either 'all' or 'any'")

    raw_defaults = raw_settings.get("defaults") or {}
    if not isinstance(raw_defaults, Mapping):
        raise ValueError(f"{config_key}.defaults must be a YAML mapping")
    defaults = _validate_layer_options(
        raw_defaults, layer_type, f"{config_key}.defaults"
    )

    raw_overrides = raw_settings.get("overrides") or {}
    if not isinstance(raw_overrides, Mapping):
        raise ValueError(f"{config_key}.overrides must be a YAML mapping")
    overrides = {}
    for source_filename, override in raw_overrides.items():
        if not isinstance(source_filename, str) or not source_filename:
            raise ValueError(f"{config_key}.overrides keys must be source filenames")
        if not isinstance(override, Mapping):
            raise ValueError(
                f"{config_key}.overrides.{source_filename} must be a YAML mapping"
            )
        merged = {**defaults, **override}
        overrides[source_filename] = _validate_layer_options(
            merged,
            layer_type,
            f"{config_key}.overrides.{source_filename}",
        )

    return {
        "enabled": enabled,
        "combine": combine,
        "defaults": defaults,
        "overrides": overrides,
    }


def write_inclusion_layer_manifest(
    output_folder: str,
    source_folder_name: str,
    layer_type: str,
    layers: list[dict[str, str]],
) -> str:
    """Map original inclusion-layer names to their processed filenames."""
    manifest_path = os.path.join(output_folder, MANIFEST_FILENAME)
    manifest = {
        "version": 1,
        "layer_type": layer_type,
        "source_folder": source_folder_name,
        "layers": sorted(layers, key=lambda layer: layer["source"]),
    }
    with open(manifest_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)
        file.write("\n")
    return manifest_path


def _prepare_inclusion_folder(
    source_root: str,
    output_root: str,
    source_folder_name: str,
    layer_type: str,
    extensions: tuple[str, ...],
    process_layer: Callable[[str, str, str, int], str | None],
) -> str:
    """Process one inclusion folder and write its source-file manifest."""
    source_folder = os.path.join(source_root, source_folder_name)
    output_folder = os.path.join(output_root, source_folder_name)
    os.makedirs(output_folder, exist_ok=True)

    processed_layers = []
    for filename in sorted(os.listdir(source_folder)):
        if not filename.lower().endswith(extensions):
            continue
        source_path = os.path.join(source_folder, filename)
        output_path = process_layer(
            source_path,
            output_folder,
            filename,
            len(processed_layers) + 1,
        )
        if output_path is not None:
            processed_layers.append(
                {
                    "source": filename,
                    "processed": os.path.basename(output_path),
                }
            )

    write_inclusion_layer_manifest(
        output_folder,
        source_folder_name,
        layer_type,
        processed_layers,
    )
    return output_folder


def prepare_inclusion_polygon_folder(
    source_root: str,
    output_root: str,
    source_folder_name: str,
    region: Any,
    region_name: str,
    target_crs: Any,
    target_crs_tag: str,
) -> str:
    """Clip a selected polygon folder and create its preprocessing manifest."""

    def process_polygon(
        source_path: str, output_folder: str, filename: str, counter: int
    ) -> str | None:
        polygon_data = gpd.read_file(source_path)
        processed_data = geopandas_clip_reproject(
            polygon_data, region, target_crs
        )
        if processed_data.empty:
            return None

        filename_base = os.path.splitext(filename)[0]
        processed_filename = (
            f"{counter}_{filename_base}_{region_name}_{target_crs_tag}.gpkg"
        )
        output_path = os.path.join(output_folder, processed_filename)
        processed_data.to_file(output_path, driver="GPKG")
        return output_path

    return _prepare_inclusion_folder(
        source_root,
        output_root,
        source_folder_name,
        "polygon",
        (".geojson", ".gpkg"),
        process_polygon,
    )


def clip_reproject_inclusion_raster(
    input_raster_path: str,
    region: Any,
    output_folder: str,
    region_name: str,
    data_name: str | None = None,
) -> str:
    """Clip an inclusion raster and reproject it to the study-area CRS.

    Nearest-neighbour resampling is used because inclusion rasters contain
    discrete eligibility codes rather than continuous measurements.
    """
    if getattr(region, "crs", None) is None:
        raise ValueError(
            "The study-area CRS is required to reproject inclusion rasters."
        )

    target_crs = rasterio.crs.CRS.from_user_input(region.crs)
    clip_geometries = region.geometry[
        region.geometry.notna() & ~region.geometry.is_empty
    ]
    if clip_geometries.empty:
        raise ValueError(
            "The study area has no non-empty geometries for raster clipping."
        )
    clip_shapes = clip_geometries.apply(mapping)

    with rasterio.open(input_raster_path) as src:
        if src.crs is None:
            raise ValueError(
                f"Cannot reproject inclusion raster with no CRS: {input_raster_path}"
            )

        if src.crs == target_crs:
            out_image, out_transform = mask(
                src, clip_shapes, crop=True, all_touched=True
            )
        else:
            with WarpedVRT(
                src,
                crs=target_crs,
                resampling=Resampling.nearest,
            ) as reprojected:
                out_image, out_transform = mask(
                    reprojected, clip_shapes, crop=True, all_touched=True
                )

        out_meta = src.meta.copy()
        out_meta.update(
            {
                "driver": "GTiff",
                "crs": target_crs,
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "compress": "DEFLATE",
            }
        )

        source_colormap = None
        if src.count == 1:
            try:
                source_colormap = src.colormap(1)
            except (ValueError, KeyError):
                pass

    authority = target_crs.to_authority()
    crs_tag = (
        "".join(authority)
        if authority
        else target_crs.to_string().replace(":", "_").replace(" ", "_")
    )
    output_prefix = (
        os.path.splitext(os.path.basename(input_raster_path))[0]
        if data_name is None
        else data_name
    )
    output_path = os.path.join(
        output_folder, f"{output_prefix}_{region_name}_{crs_tag}.tif"
    )
    os.makedirs(output_folder, exist_ok=True)
    with rasterio.open(output_path, "w", **out_meta) as dest:
        dest.write(out_image)
        if source_colormap:
            dest.write_colormap(1, source_colormap)

    return output_path


def prepare_inclusion_raster_folder(
    source_root: str,
    output_root: str,
    source_folder_name: str,
    region: Any,
    region_name: str,
) -> str:
    """Clip and reproject a raster folder to the study-area CRS."""

    def process_raster(
        source_path: str, output_folder: str, filename: str, counter: int
    ) -> str:
        del counter
        data_name = os.path.splitext(filename)[0]
        return clip_reproject_inclusion_raster(
            source_path,
            region,
            output_folder,
            region_name,
            data_name=data_name,
        )

    return _prepare_inclusion_folder(
        source_root,
        output_root,
        source_folder_name,
        "raster",
        (".tif", ".tiff"),
        process_raster,
    )


def discover_processed_inclusion_layers(
    output_folder: str, layer_type: str
) -> list[dict[str, str]]:
    """Read source-to-processed layer mappings from a preprocessing manifest."""
    if not os.path.isdir(output_folder):
        return []

    manifest_path = os.path.join(output_folder, MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(
            f"Inclusion-layer manifest not found: {manifest_path}. "
            "Run spatial_data_prep.py again."
        )

    with open(manifest_path, "r", encoding="utf-8") as file:
        manifest = json.load(file)
    if manifest.get("layer_type") != layer_type:
        raise ValueError(
            f"Expected a {layer_type} inclusion manifest at {manifest_path}"
        )
    manifest_layers = manifest.get("layers")
    if not isinstance(manifest_layers, list):
        raise ValueError(f"Invalid inclusion-layer manifest: {manifest_path}")

    layers = []
    for layer in manifest_layers:
        if not isinstance(layer, Mapping):
            raise ValueError(f"Invalid layer entry in manifest: {manifest_path}")
        source = layer.get("source")
        processed = layer.get("processed")
        for name in (source, processed):
            if not isinstance(name, str) or os.path.basename(name) != name:
                raise ValueError(f"Invalid filename in manifest: {manifest_path}")
        processed_path = os.path.join(output_folder, processed)
        if not os.path.isfile(processed_path):
            raise FileNotFoundError(
                "Processed inclusion layer listed in the manifest was not found: "
                f"{processed_path}"
            )
        layers.append(
            {"source": source, "processed": processed, "path": processed_path}
        )
    return layers


def apply_inclusion_layer_overrides(
    layers: list[dict[str, str]], settings: Mapping[str, Any], config_key: str
) -> list[dict[str, Any]]:
    """Attach default or source-filename-specific settings to discovered layers."""
    sources = {layer["source"] for layer in layers}
    unknown_overrides = set(settings["overrides"]) - sources
    if unknown_overrides:
        raise ValueError(
            f"{config_key}.overrides contains files not found in the selected "
            f"source folder: {sorted(unknown_overrides)}"
        )

    configured_layers = []
    for layer in layers:
        layer_settings = settings["overrides"].get(
            layer["source"], settings["defaults"]
        )
        configured_layers.append({**layer, "settings": layer_settings})
    return configured_layers


def compute_combined_inclusion_mask(
    layers: list[dict[str, Any]],
    combine: str,
    register_layer: Callable[[Any, dict[str, Any]], None],
    region_geometry: Any,
    crs: Any,
    resolution: float,
) -> tuple[np.ndarray, Any]:
    """Create layer masks and combine them with shared AND/OR logic."""
    if not layers:
        raise ValueError("At least one inclusion layer is required")
    if combine not in SUPPORTED_COMBINE_MODES:
        raise ValueError("combine must be either 'all' or 'any'")

    combined_mask = None
    combined_transform = None
    for layer in layers:
        layer_excluder = atlite.ExclusionContainer(crs=crs, res=resolution)
        register_layer(layer_excluder, layer)
        try:
            layer_mask, layer_transform = shape_availability(
                region_geometry, layer_excluder
            )
        finally:
            for raster_config in layer_excluder.rasters:
                opened_raster = raster_config["raster"]
                if hasattr(opened_raster, "close"):
                    opened_raster.close()

        if combined_mask is None:
            combined_mask = layer_mask.astype(bool, copy=True)
            combined_transform = layer_transform
            continue
        if (
            layer_transform != combined_transform
            or layer_mask.shape != combined_mask.shape
        ):
            raise RuntimeError("Inclusion layers could not be aligned to one grid")
        if combine == "all":
            combined_mask &= layer_mask
        else:
            combined_mask |= layer_mask

    return combined_mask, combined_transform
