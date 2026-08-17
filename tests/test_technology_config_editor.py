"""Regression tests for the technology configuration editor schema."""

from pathlib import Path
from types import SimpleNamespace

import yaml

from tkinter_app import data_loader
from tkinter_app.configuration_tab import _mousewheel_scroll_units, sections_to_yaml
from tkinter_app.data_loader import (
    CONFIG_SECTION_DEFINITIONS,
    ONSHORE_SECTION_DEFINITIONS,
    SOLAR_SECTION_DEFINITIONS,
    _build_sections_from_data,
    save_sections_round_trip,
)


ROOT_DIR = Path(__file__).resolve().parents[1]


def _template_data(name: str):
    path = ROOT_DIR / "configs" / f"{name}_template.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _definition_keys(definitions):
    return [
        parameter["key"]
        for section in definitions
        for parameter in section["parameters"]
    ]


def test_main_config_editor_definitions_match_current_template():
    template_data = _template_data("config")

    assert _definition_keys(CONFIG_SECTION_DEFINITIONS) == list(template_data)


def test_main_config_template_fields_have_named_editor_sections():
    sections = _build_sections_from_data(
        _template_data("config"), CONFIG_SECTION_DEFINITIONS
    )

    assert all(section["name"] != "additional_parameters" for section in sections)


def test_main_config_template_survives_visual_serialization():
    original_data = _template_data("config")
    sections = _build_sections_from_data(original_data, CONFIG_SECTION_DEFINITIONS)

    serialized_data = yaml.safe_load(sections_to_yaml(sections))

    assert serialized_data == original_data
    for key, original_value in original_data.items():
        if original_value is None:
            assert serialized_data[key] is None


def test_missing_main_config_falls_back_to_current_template(tmp_path, monkeypatch):
    monkeypatch.setattr(data_loader, "CONFIG_PATH", tmp_path / "missing.yaml")

    sections = data_loader.load_initial_sections()

    assert _definition_keys(sections) == list(_template_data("config"))


def test_technology_editor_definitions_match_current_templates():
    for technology, definitions in (
        ("onshorewind", ONSHORE_SECTION_DEFINITIONS),
        ("solar", SOLAR_SECTION_DEFINITIONS),
    ):
        template_keys = list(_template_data(technology))

        assert _definition_keys(definitions) == template_keys


def test_current_template_fields_have_named_editor_sections():
    for technology, definitions in (
        ("onshorewind", ONSHORE_SECTION_DEFINITIONS),
        ("solar", SOLAR_SECTION_DEFINITIONS),
    ):
        sections = _build_sections_from_data(_template_data(technology), definitions)

        assert all(section["name"] != "additional_parameters" for section in sections)


def test_technology_templates_survive_visual_editor_round_trip(tmp_path):
    for technology, definitions in (
        ("onshorewind", ONSHORE_SECTION_DEFINITIONS),
        ("solar", SOLAR_SECTION_DEFINITIONS),
    ):
        template_path = ROOT_DIR / "configs" / f"{technology}_template.yaml"
        original_text = template_path.read_text(encoding="utf-8")
        original_data = yaml.safe_load(original_text)
        sections = _build_sections_from_data(original_data, definitions)
        save_path = tmp_path / f"{technology}.yaml"
        save_path.write_text(original_text, encoding="utf-8")

        save_sections_round_trip(save_path, sections)

        assert yaml.safe_load(save_path.read_text(encoding="utf-8")) == original_data


def test_mousewheel_events_translate_to_pane_scroll_units():
    assert _mousewheel_scroll_units(SimpleNamespace(num=4, delta=0)) == -1
    assert _mousewheel_scroll_units(SimpleNamespace(num=5, delta=0)) == 1
    assert _mousewheel_scroll_units(SimpleNamespace(num=None, delta=120)) == -1
    assert _mousewheel_scroll_units(SimpleNamespace(num=None, delta=-120)) == 1
