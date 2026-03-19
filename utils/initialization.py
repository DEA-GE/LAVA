from __future__ import annotations

"""Initialize config files from default templates or a country example.

Usage:
    python utils/initialization.py
    python utils/initialization.py --source default
    python utils/initialization.py --source example --country China
"""

import argparse
import shutil
import sys
from pathlib import Path
from typing import List

TEMPLATE_SUFFIX = "_template.yaml"
EXAMPLE_TEMPLATE_TOKEN = "_template_"
EXAMPLES_SUBDIR = "examples"


def _available_example_countries(configs_dir: Path) -> List[str]:
    """Return unique country names discovered in configs/examples templates."""
    examples_dir = configs_dir / EXAMPLES_SUBDIR
    if not examples_dir.exists():
        return []

    countries_by_key: dict[str, str] = {}
    for template_path in sorted(examples_dir.glob("*_template_*.yaml")):
        _, token, suffix = template_path.name.partition(EXAMPLE_TEMPLATE_TOKEN)
        if not token or not suffix.endswith(".yaml"):
            continue

        country_name = suffix.removesuffix(".yaml").strip()
        if not country_name:
            continue

        display_name = country_name.replace("_", " ").replace("-", " ").strip()
        display_name = " ".join(display_name.split())
        if display_name.islower():
            display_name = display_name.title()

        countries_by_key.setdefault(country_name.lower(), display_name)

    return sorted(countries_by_key.values(), key=str.lower)


def _prompt_source() -> str:
    """Prompt user to choose default templates or country examples."""
    print("Initializing script, which setting to be used?")
    prompt = (
        "Select setting: [1] Odense, DK (default), [2] country example: "
    )
    valid = {
        "": "default",
        "1": "default",
        "default": "default",
        "odense": "default",
        "odense, dk": "default",
        "2": "example",
        "example": "example",
    }

    while True:
        response = input(prompt).strip().lower()
        if response in valid:
            return valid[response]
        print("Invalid choice. Enter 1/Odense, DK or 2/example.")


def _prompt_country(configs_dir: Path) -> str:
    """Prompt user to pick a country example discovered in configs/examples."""
    countries = _available_example_countries(configs_dir)
    if not countries:
        raise FileNotFoundError(
            f"No country example templates found in {configs_dir / EXAMPLES_SUBDIR}."
        )

    print("Available country examples:")
    for idx, country in enumerate(countries, start=1):
        print(f" [{idx}] {country}")

    prompt = f"Select country [1-{len(countries)}] (default: 1): "

    while True:
        response = input(prompt).strip()
        if not response:
            return countries[0]

        if response.isdigit():
            choice = int(response)
            if 1 <= choice <= len(countries):
                return countries[choice - 1]

        for country in countries:
            if response.lower() == country.lower():
                return country

        print("Invalid choice. Enter a number from the list or a country name.")


def _prompt_overwrite(existing_targets: List[Path]) -> bool:
    """Ask whether existing target files should be overwritten."""
    print("The following target files already exist:")
    for path in existing_targets:
        print(f" - {path}")

    prompt = "Overwrite existing files? [y/N]: "
    yes_values = {"y", "yes"}
    no_values = {"", "n", "no"}

    while True:
        response = input(prompt).strip().lower()
        if response in yes_values:
            return True
        if response in no_values:
            return False
        print("Invalid choice. Enter y/yes or n/no.")


def _country_templates(configs_dir: Path, country: str) -> List[tuple[Path, Path]]:
    """Return (source, target) pairs for a selected country example."""
    examples_dir = configs_dir / EXAMPLES_SUBDIR
    if not examples_dir.exists():
        raise FileNotFoundError(f"Examples directory not found: {examples_dir}")

    matches: List[tuple[Path, Path]] = []
    country_key = country.strip().lower()

    for template_path in sorted(examples_dir.glob("*_template_*.yaml")):
        prefix, token, suffix = template_path.name.partition(EXAMPLE_TEMPLATE_TOKEN)
        if not token or not suffix.endswith(".yaml"):
            continue

        file_country = suffix.removesuffix(".yaml").strip().lower()
        if file_country != country_key:
            continue

        target_path = configs_dir / f"{prefix}.yaml"
        matches.append((template_path, target_path))

    return matches


def _default_templates(configs_dir: Path) -> List[tuple[Path, Path]]:
    """Return (source, target) pairs for default templates."""
    matches: List[tuple[Path, Path]] = []
    for template_path in sorted(configs_dir.glob(f"*{TEMPLATE_SUFFIX}")):
        target_name = template_path.name.removesuffix(TEMPLATE_SUFFIX) + ".yaml"
        target_path = template_path.with_name(target_name)
        matches.append((template_path, target_path))

    return matches


def _template_pairs(configs_dir: Path, country: str | None) -> List[tuple[Path, Path]]:
    """Return copy pairs for either default templates or a country example."""
    if country:
        country_templates = _country_templates(configs_dir, country)
        if not country_templates:
            raise FileNotFoundError(
                f"No country example templates found for '{country}' in "
                f"{configs_dir / EXAMPLES_SUBDIR}."
            )
        return country_templates

    return _default_templates(configs_dir)


def initialize_config_templates(
    configs_dir: Path,
    overwrite: bool = False,
    country: str | None = None,
) -> List[Path]:
    """Copy template YAML files to non-template YAML files in ``configs``.

    Default mode:
    ``config_template.yaml`` -> ``config.yaml``

    Country example mode:
    ``configs/examples/config_template_china.yaml`` -> ``configs/config.yaml``
    """
    created_or_updated: List[Path] = []
    for template_path, target_path in _template_pairs(configs_dir, country):

        if target_path.exists() and not overwrite:
            continue

        shutil.copy2(template_path, target_path)
        created_or_updated.append(target_path)

    return created_or_updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Initialize configs from defaults or country examples in "
            "configs/examples/."
        )
    )
    parser.add_argument(
        "--configs-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "configs",
        help="Directory containing *_template.yaml files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite target files if they already exist.",
    )
    parser.add_argument(
        "--source",
        choices=["default", "example"],
        default=None,
        help="Choose default templates (Odense, DK) or country example templates.",
    )
    parser.add_argument(
        "--country",
        type=str,
        help="Country example name, e.g. China (for source=example).",
    )
    args = parser.parse_args()

    if not args.configs_dir.exists():
        raise FileNotFoundError(f"Configs directory not found: {args.configs_dir}")

    interactive = sys.stdin.isatty()
    source = args.source or (_prompt_source() if interactive else "default")
    country = args.country

    if source == "example":
        if not country:
            if not interactive:
                parser.error("--country is required with --source example in non-interactive runs.")
            country = _prompt_country(args.configs_dir)
    else:
        country = None

    overwrite = args.overwrite
    if not overwrite and interactive:
        existing_targets = [
            target_path
            for _, target_path in _template_pairs(args.configs_dir, country)
            if target_path.exists()
        ]
        if existing_targets:
            overwrite = _prompt_overwrite(existing_targets)

    copied_files = initialize_config_templates(
        args.configs_dir,
        overwrite=overwrite,
        country=country,
    )

    if not copied_files:
        print("No files copied. Targets may already exist.")
        return

    print("Copied files:")
    for path in copied_files:
        print(f" - {path}")


if __name__ == "__main__":
    main()
