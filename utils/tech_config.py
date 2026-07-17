from __future__ import annotations

import copy
import os
from typing import Any

import yaml


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _load_yaml_file(file_path: str) -> dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as file:
        return yaml.load(file, Loader=yaml.FullLoader)


def _split_scenario_sections(
    raw_config: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, dict[str, Any]]]:
    reference_scenario = raw_config.get("reference_scenario", "ref")
    additional_scenarios = copy.deepcopy(raw_config.get("additional_scenarios") or {})
    base_config = copy.deepcopy(raw_config)
    base_config.pop("reference_scenario", None)
    base_config.pop("additional_scenarios", None)

    if reference_scenario in additional_scenarios:
        raise ValueError(
            f"Scenario override '{reference_scenario}' conflicts with reference_scenario. "
            "Use the top-level config as the reference scenario and keep only non-reference scenarios under additional_scenarios."
        )

    return reference_scenario, base_config, additional_scenarios


def load_tech_config_from_path(file_path: str, scenario: str | None) -> dict[str, Any]:
    raw_config = _load_yaml_file(file_path)
    reference_scenario, base_config, additional_scenarios = _split_scenario_sections(
        raw_config
    )

    if scenario is None or scenario == reference_scenario:
        return base_config

    if scenario not in additional_scenarios:
        valid_scenarios = [reference_scenario, *additional_scenarios.keys()]
        raise KeyError(
            f"Scenario '{scenario}' is not defined in {os.path.basename(file_path)}. "
            f"Available scenarios: {valid_scenarios}"
        )

    return _deep_merge_dicts(base_config, additional_scenarios[scenario])


def load_tech_config(
    technology: str, scenario: str | None, config_dir: str = "configs"
) -> dict[str, Any]:
    file_path = os.path.join(config_dir, f"{technology}.yaml")
    return load_tech_config_from_path(file_path, scenario)


def get_tech_scenarios_from_path(file_path: str) -> list[str]:
    raw_config = _load_yaml_file(file_path)
    reference_scenario, _, additional_scenarios = _split_scenario_sections(raw_config)
    return [reference_scenario, *additional_scenarios.keys()]


def get_tech_scenarios(technology: str, config_dir: str = "configs") -> list[str]:
    file_path = os.path.join(config_dir, f"{technology}.yaml")
    return get_tech_scenarios_from_path(file_path)


def validate_selected_scenarios(
    technologies: list[str], scenarios: list[str], config_dir: str = "configs"
) -> None:
    invalid: dict[str, list[str]] = {}

    for technology in technologies:
        available_scenarios = set(get_tech_scenarios(technology, config_dir=config_dir))
        missing = [
            scenario for scenario in scenarios if scenario not in available_scenarios
        ]
        if missing:
            invalid[technology] = missing

    if invalid:
        lines = [
            f"{technology}: missing scenarios {missing}"
            for technology, missing in invalid.items()
        ]
        raise ValueError(
            "Selected Snakemake scenarios are not defined in the technology configs:\n"
            + "\n".join(lines)
        )
