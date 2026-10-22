"""Regression tests for the technology configuration editor schema."""

from pathlib import Path
from types import SimpleNamespace

import yaml

from tkinter_app import data_loader
from tkinter_app import configuration_tab
from tkinter_app.configuration_tab import (
    ConfigurationTab,
    _mousewheel_scroll_units,
    rebuild_from_widgets,
    sections_to_yaml,
)
from tkinter_app.data_loader import (
    CONFIG_SECTION_DEFINITIONS,
    ONSHORE_SECTION_DEFINITIONS,
    SOLAR_SECTION_DEFINITIONS,
    _build_sections_from_data,
    save_sections_round_trip,
)


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_additional_spatial_folder_settings_are_exposed_in_editor():
    expected = {
        "additional_exclusion_polygons_folder_name": "additional_exclusion_polygons",
        "additional_exclusion_rasters_folder_name": "additional_exclusion_rasters",
        "additional_inclusion_polygons_folder_name": "additional_inclusion_polygons",
        "additional_inclusion_rasters_folder_name": "additional_inclusion_rasters",
    }
    section = next(
        item
        for item in CONFIG_SECTION_DEFINITIONS
        if item["name"] == "additional_spatial_layers"
    )

    assert {parameter["key"] for parameter in section["parameters"]} == set(expected)
    for key, folder in expected.items():
        assert configuration_tab.PARAMETER_PICKERS[key] == "folder_name"
        assert configuration_tab.PARAMETER_FOLDER_ROOTS[key] == (
            ROOT_DIR / "Raw_Spatial_Data" / folder
        )


def test_workflow_save_syncs_list_controls_before_dirty_check(tmp_path, monkeypatch):
    """A just-removed region must be saved even if Tk missed its callback."""
    sections = [{"parameters": [{"key": "study_region_name", "value": ["Old"]}]}]
    baseline = [{"parameters": [{"key": "study_region_name", "value": ["Old"]}]}]
    save_path = tmp_path / "config_snakemake.yaml"
    save_path.write_text("study_region_name: [Old]\n", encoding="utf-8")
    info = {
        "sections": sections,
        "sections_baseline": baseline,
        "mode_var": SimpleNamespace(get=lambda: "visual"),
        "dirty": False,
        "kind": "config_snakemake",
        "text_widget": None,
        "save_path": save_path,
    }
    editor = SimpleNamespace(
        extra_files={"config_snakemake.yaml": info},
        master=SimpleNamespace(master=SimpleNamespace()),
        _comment_help_cache={},
    )

    def sync(_label):
        sections[0]["parameters"][0]["value"] = []

    editor._update_extra_sections_from_controls = sync
    editor._editor_states_equal = ConfigurationTab._editor_states_equal
    editor._serialize_sections_for_kind = lambda _kind, _sections: (
        "study_region_name: []\n"
    )
    editor._render_extra_visual_sections = lambda *_args: None
    editor._update_extra_visual_controls = lambda *_args: None
    editor._reset_visual_history = lambda *_args: None
    editor._refresh_dirty_state_ui = lambda: None
    editor._show_save_confirmation = lambda *_args: None
    monkeypatch.setattr(configuration_tab, "round_trip_available", lambda: False)

    assert ConfigurationTab._save_extra_file(
        editor, "config_snakemake.yaml", validate=False
    )
    assert save_path.read_text(encoding="utf-8") == "study_region_name: []\n"


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


def test_active_inclusion_enabled_values_are_yaml_booleans():
    for technology in ("onshorewind", "solar"):
        active_path = ROOT_DIR / "configs" / f"{technology}.yaml"
        active_data = yaml.safe_load(active_path.read_text(encoding="utf-8"))

        for key in ("additional_inclusion_polygons", "additional_inclusion_rasters"):
            assert isinstance(active_data[key]["enabled"], bool), (
                f"{active_path.name}: {key}.enabled must be a YAML boolean"
            )


def test_visual_editor_saves_raster_codes_as_integers_after_malformed_config():
    class FakeVariable:
        def get(self):
            return "7, 6, 5, 4"

    malformed = {
        "additional_inclusion_rasters": {
            "enabled": True,
            "defaults": {"codes": ["[7", "6", "5", "4]"]},
        }
    }
    rebuilt = rebuild_from_widgets(
        malformed,
        {
            "additional_inclusion_rasters.defaults.codes": FakeVariable(),
        },
    )

    assert rebuilt["additional_inclusion_rasters"]["defaults"]["codes"] == [
        7,
        6,
        5,
        4,
    ]
    assert all(
        type(code) is int
        for code in rebuilt["additional_inclusion_rasters"]["defaults"]["codes"]
    )


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
