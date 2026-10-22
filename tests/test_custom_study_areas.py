"""Tests for custom study-area collection folders and legacy fallbacks."""

import json

import pytest

from tkinter_app.data_loader import (
    load_custom_study_area_names,
    validate_configuration_documents,
)
from utils.spatial_prep_plan import resolve_custom_study_area_path


def test_nested_collection_path_is_preferred(tmp_path):
    collection = (
        tmp_path / "Raw_Spatial_Data" / "custom_study_area" / "denmark_adm1"
    )
    collection.mkdir(parents=True)
    expected = collection / "Sjælland.geojson"
    expected.write_text("{}", encoding="utf-8")

    path, used_legacy_path = resolve_custom_study_area_path(
        configured_region="Sjælland",
        filename_template="denmark_adm1/{region_name}.geojson",
        project_root=tmp_path,
    )

    assert path == expected
    assert not used_legacy_path


def test_nested_template_accepts_flat_file_as_legacy_fallback(tmp_path):
    root = tmp_path / "Raw_Spatial_Data" / "custom_study_area"
    root.mkdir(parents=True)
    legacy = root / "Sjaelland.geojson"
    legacy.write_text("{}", encoding="utf-8")

    path, used_legacy_path = resolve_custom_study_area_path(
        configured_region="Sjælland",
        filename_template="denmark_adm1/{region_name}.geojson",
        project_root=tmp_path,
    )

    assert path == legacy
    assert used_legacy_path


def test_custom_study_area_path_cannot_escape_its_root(tmp_path):
    with pytest.raises(ValueError, match="cannot contain"):
        resolve_custom_study_area_path(
            configured_region="Region",
            filename_template="../{region_name}.geojson",
            project_root=tmp_path,
        )


def test_study_area_names_are_discovered_recursively(tmp_path):
    root = tmp_path / "custom_study_area"
    first = root / "denmark_adm1"
    second = root / "municipalities"
    first.mkdir(parents=True)
    second.mkdir()
    (first / "Hovedstaden.geojson").write_text("{}", encoding="utf-8")
    (second / "Odense.geojson").write_text("{}", encoding="utf-8")
    (first / "processed_areas_list.json").write_text(
        json.dumps(["Hovedstaden", "Missing"]), encoding="utf-8"
    )

    assert load_custom_study_area_names(root) == ["Hovedstaden", "Odense"]


def test_flat_config_path_produces_collection_folder_warning():
    issues = validate_configuration_documents(
        {
            "config.yaml": {
                "study_region_name": "Region",
                "country_code": "DNK",
                "custom_study_area_filename": "Region.geojson",
                "GADM_source": "gadm",
                "OSM_source": "overpass",
                "population_source": "0",
                "protected_areas_source": "0",
            }
        }
    )

    assert any(
        issue["key"] == "custom_study_area_filename"
        and issue["severity"] == "warning"
        and "collection folder" in issue["message"]
        for issue in issues
    )
