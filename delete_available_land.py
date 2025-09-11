#!/usr/bin/env python3
"""Delete outputs for a chosen scenario.

Scans all ``data/<province>/scenario_runs.log`` files to discover available
scenarios (across technologies such as ``onshorewind`` and ``solar``). Prompts
the user to pick a scenario. Shows the files that would be deleted in these
folders for every province, then deletes upon confirmation:

- ``data/<province>/available_land``
- ``data/<province>/suitability``
- ``data/<province>/snakemake_log``

Files are matched if their filename contains the selected scenario substring,
which covers naming patterns like ``<prov>_<tech>_<scenario>_*`` and
``<prov>_<scenario>_<tech>_*``. All technologies using that scenario are
affected.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Set, Tuple


def _discover(root: Path) -> Tuple[Dict[str, Set[str]], List[str]]:
    """Return (scenarios_by_tech, provinces_with_logs).

    Parses every ``data/<province>/scenario_runs.log`` assuming CSV lines with
    three fields: province, technology, scenario.
    """
    scenarios_by_tech: Dict[str, Set[str]] = {}
    provinces: Set[str] = set()

    data_dir = root / "data"
    for log_path in data_dir.glob("*/scenario_runs.log"):
        province = log_path.parent.name
        provinces.add(province)
        with log_path.open(newline="") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if not row:
                    continue
                if len(row) == 3:
                    _, tech, scenario = [part.strip() for part in row]
                elif len(row) >= 2:
                    tech, scenario = row[-2].strip(), row[-1].strip()
                else:
                    # Only one token; treat as scenario without tech.
                    tech, scenario = "", row[0].strip()
                if not scenario:
                    continue
                if tech not in scenarios_by_tech:
                    scenarios_by_tech[tech] = set()
                scenarios_by_tech[tech].add(scenario)

    return scenarios_by_tech, sorted(provinces)


def _matching_files_in_folder(folder: Path, tech: str, scenario: str) -> List[Path]:
    if not folder.exists():
        return []
    matches: List[Path] = []
    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        if scenario in name and (tech == "" or tech in name):
            matches.append(p)
    return matches


def _collect_files_for_all_provinces(root: Path, provinces: List[str], tech: str, scenario: str) -> List[Path]:
    files: List[Path] = []
    for prov in provinces:
        base = root / "data" / prov
        files += _matching_files_in_folder(base / "available_land", tech, scenario)
        files += _matching_files_in_folder(base / "suitability", tech, scenario)
        files += _matching_files_in_folder(base / "snakemake_log", tech, scenario)
    # Deduplicate while preserving order
    seen: Set[Path] = set()
    unique: List[Path] = []
    for f in files:
        if f not in seen:
            unique.append(f)
            seen.add(f)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete available land files by scenario run from scenario_runs.log"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Project root containing data directory",
    )
    args = parser.parse_args()
    scenarios_by_tech, provinces = _discover(args.root)
    if not scenarios_by_tech:
        print(f"No scenario runs found in {args.root / 'data'}")
        return

    # Union of scenarios across all technologies
    scenarios_set = set()
    for sset in scenarios_by_tech.values():
        scenarios_set.update(sset)
    scenarios = sorted(scenarios_set)
    if not scenarios:
        print("No scenarios found.")
        return

    print("Scenarios:")
    for i, s in enumerate(scenarios, 1):
        print(f"{i}. {s}")
    while True:
        raw = input("Choose scenario [number]: ").strip()
        try:
            si = int(raw)
            if 1 <= si <= len(scenarios):
                break
        except ValueError:
            pass
        print("Invalid selection. Try again.")
    scenario = scenarios[si - 1]

    files = _collect_files_for_all_provinces(args.root, provinces, "", scenario)
    if not files:
        print("No files found matching the selected technology and scenario.")
        return

    print("The following files will be deleted:")
    for p in files:
        try:
            rel = p.relative_to(args.root)
        except Exception:
            rel = p
        print(f" - {rel}")
    print(f"Total files: {len(files)}")

    confirm = input("Proceed with deletion? Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Deletion aborted.")
        return

    deleted = 0
    for path in files:
        try:
            path.unlink()
            deleted += 1
        except FileNotFoundError:
            pass
        except PermissionError:
            print(f"Permission denied: {path}")
    print(f"Deleted {deleted} files for scenario '{scenario}'.")


if __name__ == "__main__":
    main()
