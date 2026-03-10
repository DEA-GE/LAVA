from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import List

TEMPLATE_SUFFIX = "_template.yaml"


def initialize_config_templates(configs_dir: Path, overwrite: bool = False) -> List[Path]:
    """Copy template YAML files to non-template YAML files in the same directory.

    Example: ``config_template.yaml`` -> ``config.yaml``
    """
    created_or_updated: List[Path] = []

    for template_path in sorted(configs_dir.glob(f"*{TEMPLATE_SUFFIX}")):
        target_name = template_path.name.removesuffix(TEMPLATE_SUFFIX) + ".yaml"
        target_path = template_path.with_name(target_name)

        if target_path.exists() and not overwrite:
            continue

        shutil.copy2(template_path, target_path)
        created_or_updated.append(target_path)

    return created_or_updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Copy template YAML files in configs/ to non-template YAML files "
            "(e.g. config_template.yaml -> config.yaml)."
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
    args = parser.parse_args()

    if not args.configs_dir.exists():
        raise FileNotFoundError(f"Configs directory not found: {args.configs_dir}")

    copied_files = initialize_config_templates(args.configs_dir, overwrite=args.overwrite)

    if not copied_files:
        print("No files copied. Targets may already exist.")
        return

    print("Copied files:")
    for path in copied_files:
        print(f" - {path}")


if __name__ == "__main__":
    main()
