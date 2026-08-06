#!/usr/bin/env python3
"""Delete outputs for a chosen scenario.

Builds scenario choices primarily from existing files under the target output
folders. If none are found, falls back to ``data/<province>/scenario_runs.log``
entries. Prompts the user to pick a scenario. Shows the files that would be
deleted in these folders for every province, then deletes upon confirmation:

- ``data/<province>/available_land``
- ``data/<province>/suitability``
- ``data/<province>/snakemake_log``

Files are matched using exact scenario token boundaries in filenames, so
selecting ``incForest`` does not also match ``incForest1500rugg``.
"""

from __future__ import annotations

import argparse
import csv
import re
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


def _discover_provinces(root: Path) -> List[str]:
    data_dir = root / "data"
    if not data_dir.exists():
        return []
    return sorted([p.name for p in data_dir.iterdir() if p.is_dir()])


def _extract_scenario_from_filename(name: str, province: str, techs: Set[str]) -> str | None:
    """Extract scenario from known output filename patterns."""
    stem = Path(name).stem

    # snakemake_log: exclusion_<tech>_<scenario>.done
    if stem.startswith("exclusion_"):
        rest = stem[len("exclusion_") :]
        for tech in sorted(techs, key=len, reverse=True):
            prefix = f"{tech}_"
            if rest.startswith(prefix):
                scenario = rest[len(prefix) :].strip()
                return scenario or None

    # Files prefixed by province in available_land/suitability patterns.
    prov_prefix = f"{province}_"
    if not stem.startswith(prov_prefix):
        return None
    rest = stem[len(prov_prefix) :]

    # <scenario>_<tech>_exclusion_info
    m = re.match(r"^(?P<left>.+)_(?P<tech>[^_]+)_exclusion_info$", rest)
    if m and m.group("tech") in techs:
        scenario = m.group("left").strip()
        return scenario or None

    # <tech>_<scenario>_available_land_...
    marker = "_available_land_"
    if marker in rest:
        left = rest.split(marker, 1)[0]
        for tech in sorted(techs, key=len, reverse=True):
            prefix = f"{tech}_"
            if left.startswith(prefix):
                scenario = left[len(prefix) :].strip()
                return scenario or None

    return None


def _discover_scenarios_from_files(root: Path, provinces: List[str], techs: Set[str]) -> List[str]:
    scenarios: Set[str] = set()
    for prov in provinces:
        base = root / "data" / prov
        for folder_name in ("available_land", "suitability", "snakemake_log"):
            folder = base / folder_name
            if not folder.exists():
                continue
            for p in folder.rglob("*"):
                if not p.is_file():
                    continue
                scenario = _extract_scenario_from_filename(p.name, prov, techs)
                if scenario:
                    scenarios.add(scenario)
    return sorted(scenarios)


def _matching_files_in_folder(folder: Path, tech: str, scenario: str) -> List[Path]:
    if not folder.exists():
        return []
    matches: List[Path] = []
    scenario_rx = re.compile(rf"(^|_){re.escape(scenario)}(_|\.|$)")
    tech_rx = re.compile(rf"(^|_){re.escape(tech)}(_|\.|$)") if tech else None
    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        if not scenario_rx.search(name):
            continue
        if tech_rx and not tech_rx.search(name):
            continue
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
        default=Path.cwd(),
        help="Project root containing data directory",
    )
    args = parser.parse_args()
    scenarios_by_tech, provinces_with_logs = _discover(args.root)
    provinces = _discover_provinces(args.root) or provinces_with_logs

    techs: Set[str] = {t for t in scenarios_by_tech.keys() if t}
    techs.update({"onshorewind", "solar", "offshorewind"})
    scenarios = _discover_scenarios_from_files(args.root, provinces, techs)

    if not scenarios and scenarios_by_tech:
        # Fallback to log-derived scenarios if no parseable scenarios are found in files.
        scenarios_set = set()
        for sset in scenarios_by_tech.values():
            scenarios_set.update(sset)
        scenarios = sorted(scenarios_set)
        print("No scenarios parsed from existing files. Falling back to scenario_runs.log.")

    if not scenarios:
        print("No scenarios found in current files or scenario_runs.log.")
        return

    while True:
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
        else:
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
            else:
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

        again = input("Delete another scenario? [y/N]: ").strip().lower()
        if again not in {"y", "yes"}:
            break


if __name__ == "__main__":
    main()
