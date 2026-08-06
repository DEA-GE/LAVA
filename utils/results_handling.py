#!/usr/bin/env python3
"""Utilities for handling scenario-result metadata.

Includes rebuilding ``scenario_runs.log`` files from existing province outputs.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Set, Tuple


TECHS: Set[str] = {"onshorewind", "solar", "offshorewind"}


def _tech_pattern(techs: Set[str]) -> str:
    return "|".join(re.escape(t) for t in sorted(techs, key=len, reverse=True))


def _pairs_from_available_land(province_dir: Path, province: str, techs: Set[str]) -> Set[Tuple[str, str]]:
    pairs: Set[Tuple[str, str]] = set()
    folder = province_dir / "available_land"
    if not folder.exists():
        return pairs

    tech_pat = _tech_pattern(techs)
    rx_exclusion = re.compile(rf"^(?P<scenario>.+)_(?P<tech>{tech_pat})_exclusion_info$")
    tech_ordered = sorted(techs, key=len, reverse=True)
    prov_prefix = f"{province}_"

    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        stem = p.stem
        if not stem.startswith(prov_prefix):
            continue
        rest = stem[len(prov_prefix) :]

        # Pattern: <province>_<scenario>_<tech>_exclusion_info.*
        m = rx_exclusion.match(rest)
        if m:
            pairs.add((m.group("tech"), m.group("scenario")))
            continue

        # Pattern: <province>_<tech>_<scenario>_available_land_*
        marker = "_available_land_"
        if marker not in rest:
            continue
        left = rest.split(marker, 1)[0]
        for tech in tech_ordered:
            prefix = f"{tech}_"
            if left.startswith(prefix):
                scenario = left[len(prefix) :]
                if scenario:
                    pairs.add((tech, scenario))
                break

    return pairs


def _pairs_from_snakemake_log(province_dir: Path, techs: Set[str]) -> Set[Tuple[str, str]]:
    pairs: Set[Tuple[str, str]] = set()
    folder = province_dir / "snakemake_log"
    if not folder.exists():
        return pairs

    tech_pat = _tech_pattern(techs)
    rx_exclusion_done = re.compile(rf"^exclusion_(?P<tech>{tech_pat})_(?P<scenario>.+)\.done$")

    for p in folder.rglob("*.done"):
        m = rx_exclusion_done.match(p.name)
        if not m:
            continue
        pairs.add((m.group("tech"), m.group("scenario")))

    return pairs


def _build_rows_for_province(province_dir: Path, techs: Set[str]) -> List[Tuple[str, str, str]]:
    province = province_dir.name
    pairs: Set[Tuple[str, str]] = set()
    pairs |= _pairs_from_available_land(province_dir, province, techs)
    pairs |= _pairs_from_snakemake_log(province_dir, techs)
    return [(province, tech, scenario) for tech, scenario in sorted(pairs, key=lambda x: (x[0], x[1]))]


def sync_scenario_logs(root: Path, dry_run: bool = False) -> Tuple[int, int, int]:
    """Sync ``data/<province>/scenario_runs.log`` from existing files.

    Returns ``(changed, unchanged, total_provinces)``.
    """
    data_dir = root / "data"
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return 0, 0, 0

    province_dirs = sorted([p for p in data_dir.iterdir() if p.is_dir()], key=lambda p: p.name)
    changed = 0
    unchanged = 0

    for province_dir in province_dirs:
        rows = _build_rows_for_province(province_dir, TECHS)
        log_path = province_dir / "scenario_runs.log"
        content = "".join(f"{province},{tech},{scenario}\n" for province, tech, scenario in rows)
        old_content = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        if old_content == content:
            unchanged += 1
            continue
        changed += 1
        if dry_run:
            print(f"[DRY-RUN] Would update {log_path.relative_to(root)} ({len(rows)} entries)")
        else:
            log_path.write_text(content, encoding="utf-8")
            print(f"Updated {log_path.relative_to(root)} ({len(rows)} entries)")

    print(f"Done. Changed: {changed}, unchanged: {unchanged}, provinces: {len(province_dirs)}")
    return changed, unchanged, len(province_dirs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync data/<province>/scenario_runs.log from existing files")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root containing the data directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without writing files",
    )
    args = parser.parse_args()
    sync_scenario_logs(root=args.root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
