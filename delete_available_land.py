#!/usr/bin/env python3
"""Delete available land files for a chosen scenario run.

The available scenarios are derived from ``scenario_runs.log`` files located
inside ``data/<province>`` directories. The user selects a scenario run to
delete and the script lists the matching ``*_available_land_*.tif`` files.
After confirmation all files are removed."""

from __future__ import annotations

import argparse
from pathlib import Path


def _parse_runs(root: Path) -> list[tuple[str, str]]:
    """Return unique (province, scenario) pairs from scenario run logs.

    Each ``scenario_runs.log`` is expected to reside in ``data/<province>`` and
    contain scenario names. If the log also includes the province name, the
    second token is treated as the scenario.
    """

    runs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    data_dir = root / "data"
    for log_path in data_dir.glob("*/scenario_runs.log"):
        province = log_path.parent.name
        with log_path.open() as fh:
            for line in fh:
                parts = line.strip().split()
                if not parts:
                    continue
                scenario = parts[1] if len(parts) > 1 else parts[0]
                key = (province, scenario)
                if key not in seen:
                    runs.append(key)
                    seen.add(key)

    return runs


def _collect_files(root: Path, province: str, scenario: str) -> list[Path]:
    """Return available land files for the given province and scenario."""
    base = root / "data" / province / "available_land"
    if not base.exists():
        return []
    return list(base.rglob(f"*{scenario}_available_land*.tif"))


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
    runs = _parse_runs(args.root)
    if not runs:
        print(f"No scenario runs found in {args.root / 'data'}")
        return

    print("Scenario runs:")
    for idx, (province, scenario) in enumerate(runs, start=1):
        print(f"{idx}. {province} - {scenario}")

    choice = input("Enter the number of the scenario to delete: ")
    try:
        index = int(choice)
        if index < 1 or index > len(runs):
            raise ValueError
    except ValueError:
        print("Invalid selection. Aborting.")
        return

    province, scenario = runs[index - 1]
    files = _collect_files(args.root, province, scenario)
    if not files:
        print("No available land files found for the selected scenario run.")
        return

    print("The following files will be deleted:")
    for path in files:
        print(f" - {path}")

    confirm = input("Proceed with deletion? [y/N]: ").strip().lower()
    if not confirm.startswith("y"):
        print("Deletion aborted.")
        return

    for path in files:
        try:
            path.unlink()
            print(f"Deleted {path}")
        except FileNotFoundError:
            print(f"File not found: {path}")

    print(f"Scenario '{scenario}' for province '{province}' deleted.")


if __name__ == "__main__":
    main()
