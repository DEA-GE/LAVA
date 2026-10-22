"""Split a GADM dataset into one GeoJSON study-area file per region."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import geopandas as gpd


DEFAULT_OUTPUT_FOLDER = Path("Raw_Spatial_Data/custom_study_area/gadm_areas")
AREA_RENAMES = {"XinjiangUygur": "Xinjiang", "NingxiaHui": "Ningxia"}


@dataclass(frozen=True)
class GADMExtractionResult:
    """Files and area names produced by :func:`extract_gadm_levels`."""

    output_folder: Path
    area_names: list[str]
    created_files: list[Path]
    skipped_files: list[Path]
    manifest_path: Path


def _safe_area_name(value: object) -> str:
    name = AREA_RENAMES.get(str(value), str(value)).strip()
    safe_name = "".join(
        character if character.isalnum() or character in " _-" else "_"
        for character in name
    ).strip(" ._")
    return safe_name or "unnamed_area"


def available_gadm_levels(columns: Sequence[object]) -> list[int]:
    """Return sorted GADM levels represented by ``NAME_<level>`` columns."""
    levels: list[int] = []
    for column in columns:
        match = re.fullmatch(r"NAME_(\d+)", str(column))
        if match:
            levels.append(int(match.group(1)))
    return sorted(set(levels))


def extract_gadm_levels(
    input_path: str | Path,
    gadm_level: int = 1,
    output_folder: str | Path = DEFAULT_OUTPUT_FOLDER,
    *,
    overwrite: bool = False,
) -> GADMExtractionResult:
    """Extract every named area into a separate GeoJSON in one collection folder.

    Existing area files are preserved unless ``overwrite`` is true. The returned
    result lets graphical and command-line callers report created and skipped
    files without parsing console output. Use a distinct output folder for each
    source dataset or administrative level.
    """
    source = Path(input_path).expanduser()
    destination = Path(output_folder).expanduser()
    try:
        level = int(gadm_level)
    except (TypeError, ValueError) as exc:
        raise ValueError("GADM level must be a non-negative integer.") from exc
    if level < 0:
        raise ValueError("GADM level must be a non-negative integer.")
    if not source.is_file():
        raise FileNotFoundError(f"GADM input file not found: {source}")
    if destination.exists() and not destination.is_dir():
        raise NotADirectoryError(f"Output path is not a directory: {destination}")

    gadm_data = gpd.read_file(source)
    name_column = f"NAME_{level}"
    if name_column not in gadm_data.columns:
        available = available_gadm_levels(gadm_data.columns)
        detail = ", ".join(str(value) for value in available) or "none"
        raise ValueError(
            f"{source.name} does not contain {name_column}. "
            f"Available GADM levels: {detail}."
        )

    selected = gadm_data.loc[gadm_data[name_column].notna()].copy()
    if selected.empty:
        raise ValueError(f"No named areas were found in {name_column}.")

    destination.mkdir(parents=True, exist_ok=True)
    area_names: list[str] = []
    created_files: list[Path] = []
    skipped_files: list[Path] = []
    used_names: dict[str, int] = {}

    for raw_name, group in selected.groupby(name_column, sort=True):
        base_name = _safe_area_name(raw_name)
        occurrence = used_names.get(base_name, 0) + 1
        used_names[base_name] = occurrence
        safe_name = base_name if occurrence == 1 else f"{base_name}_{occurrence}"
        output_path = destination / f"{safe_name}.geojson"
        area_names.append(safe_name)
        if output_path.exists() and not overwrite:
            skipped_files.append(output_path)
            continue
        group.to_file(output_path, driver="GeoJSON")
        created_files.append(output_path)

    manifest_path = destination / "processed_areas_list.json"
    manifest_path.write_text(
        json.dumps(area_names, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return GADMExtractionResult(
        output_folder=destination,
        area_names=area_names,
        created_files=created_files,
        skipped_files=skipped_files,
        manifest_path=manifest_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split a GADM dataset into one GeoJSON file per named area."
    )
    parser.add_argument("input_path", type=Path, help="GADM GeoJSON/GPKG input file")
    parser.add_argument(
        "--level", type=int, default=1, help="GADM administrative level (default: 1)"
    )
    parser.add_argument(
        "--output-folder",
        type=Path,
        default=DEFAULT_OUTPUT_FOLDER,
        help=f"Output directory (default: {DEFAULT_OUTPUT_FOLDER})",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing area GeoJSON files"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = extract_gadm_levels(
        args.input_path,
        gadm_level=args.level,
        output_folder=args.output_folder,
        overwrite=args.overwrite,
    )
    print(
        f"Prepared {len(result.area_names)} area(s): "
        f"{len(result.created_files)} written, {len(result.skipped_files)} kept."
    )
    print(f"Output folder: {result.output_folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
