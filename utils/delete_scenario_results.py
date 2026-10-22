#!/usr/bin/env python3
"""Preview and delete generated outputs for one exact scenario name."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.results_handling import sync_scenario_logs


RESULT_FOLDERS = ("available_land", "suitability", "snakemake_log")
AGGREGATED_PATTERN = "aggregated_available_land*"


class ResultsDeletionError(RuntimeError):
    """A user-actionable problem while discovering or deleting results."""


def discover_scenarios(root: Path) -> list[str]:
    """Return scenario names from output metadata and scenario logs."""
    scenarios: set[str] = set()
    data_dir = root / "data"
    if not data_dir.is_dir():
        return []

    for path in sorted(data_dir.glob("*/available_land/*_exclusion_info.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            scenario = payload["scenario"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ResultsDeletionError(
                f"Cannot read the scenario from exclusion metadata {path}: {exc}"
            ) from exc
        if not isinstance(scenario, str) or not scenario.strip():
            raise ResultsDeletionError(
                f"Exclusion metadata has an invalid scenario value: {path}"
            )
        scenarios.add(scenario.strip())

    for path in sorted(data_dir.glob("*/scenario_runs.log")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ResultsDeletionError(f"Cannot read {path}: {exc}") from exc
        for line in lines:
            fields = [field.strip() for field in line.split(",")]
            if len(fields) >= 3 and fields[-1]:
                scenarios.add(fields[-1])
    return sorted(scenarios, key=str.casefold)


def collect_scenario_files(root: Path, scenario: str) -> list[Path]:
    """Collect files for a scenario without confusing longer scenario names."""
    scenario = scenario.strip()
    if not scenario:
        raise ResultsDeletionError("A non-empty scenario name is required.")
    data_dir = root / "data"
    known_scenarios = set(discover_scenarios(root))
    known_scenarios.add(scenario)
    tokens = {
        name: re.compile(rf"(^|_){re.escape(name)}(?=_|\.|$)")
        for name in known_scenarios
    }
    matches: list[Path] = []
    if not data_dir.is_dir():
        return matches
    for province_dir in sorted(path for path in data_dir.iterdir() if path.is_dir()):
        for folder_name in RESULT_FOLDERS:
            folder = province_dir / folder_name
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*")):
                if not path.is_file():
                    continue
                matching_names = [
                    name for name, token in tokens.items() if token.search(path.name)
                ]
                if scenario in matching_names and len(scenario) == max(
                    map(len, matching_names)
                ):
                    matches.append(path)
    return sorted(set(matches))


def aggregated_result_files(root: Path) -> list[Path]:
    """Return default aggregate files, which become stale after any deletion."""
    allowed = {".gpkg", ".json", ".csv"}
    return sorted(
        path
        for path in root.glob(AGGREGATED_PATTERN)
        if path.is_file() and path.suffix.lower() in allowed
    )


def delete_scenario_outputs(root: Path, scenario: str) -> tuple[list[Path], list[Path]]:
    """Delete one scenario, invalidate aggregates, and rebuild scenario logs."""
    files = collect_scenario_files(root, scenario)
    if not files:
        raise ResultsDeletionError(
            f"No generated files match scenario '{scenario}' below {root / 'data'}."
        )
    deleted: list[Path] = []
    for path in files:
        try:
            path.unlink()
            deleted.append(path)
        except OSError as exc:
            raise ResultsDeletionError(f"Could not delete {path}: {exc}") from exc

    invalidated: list[Path] = []
    for path in aggregated_result_files(root):
        try:
            path.unlink()
            invalidated.append(path)
        except OSError as exc:
            raise ResultsDeletionError(
                f"Scenario files were deleted, but stale aggregate {path} could not be removed: {exc}"
            ) from exc
    sync_scenario_logs(root)
    return deleted, invalidated


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or delete one scenario's results")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--scenario", help="Exact scenario name")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    parser.add_argument("--yes", action="store_true", help="Perform deletion after preview")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.list:
            scenarios = discover_scenarios(root)
            if not scenarios:
                print(f"No scenario results were found below {root / 'data'}.")
                return 1
            print("\n".join(scenarios))
            return 0
        if not args.scenario:
            raise ResultsDeletionError("Specify --scenario NAME, or use --list.")
        files = collect_scenario_files(root, args.scenario)
        if not files:
            raise ResultsDeletionError(
                f"No generated files match scenario '{args.scenario}'."
            )
        print(f"Files selected for scenario '{args.scenario}':")
        for path in files:
            print(f" - {path.relative_to(root)}")
        print(f"Total files: {len(files)}")
        if not args.yes:
            raise ResultsDeletionError(
                "Preview only; no files were deleted. Re-run with --yes to confirm."
            )
        deleted, invalidated = delete_scenario_outputs(root, args.scenario)
        print(f"Deleted {len(deleted)} scenario file(s).")
        print(f"Invalidated {len(invalidated)} aggregate result file(s).")
        return 0
    except ResultsDeletionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
