from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tkinter_app.map_tab import MapTab
from tkinter_app.results_tab import build_scenario_comparison, numeric_result


class ResultsComparisonTests(unittest.TestCase):
    def test_comparison_calculates_all_requested_differences(self) -> None:
        rows = [
            {
                "Scenario": "base",
                "Technology": "solar",
                "Region": "North",
                "eligibility_share_%": 40,
                "available_area_km2": "1.20e+03",
                "power_potential_TW": 0.5,
            },
            {
                "Scenario": "high",
                "Technology": "solar",
                "Region": "North",
                "eligibility_share_%": 46.5,
                "available_area_km2": "1.35e+03",
                "power_potential_TW": 0.62,
            },
        ]

        comparison = build_scenario_comparison(rows, "base", "high")

        self.assertEqual(len(comparison), 1)
        result = comparison[0]
        self.assertAlmostEqual(result["difference_eligibility_share_pp"], 6.5)
        self.assertAlmostEqual(result["difference_available_area_km2"], 150.0)
        self.assertAlmostEqual(result["difference_power_potential_TW"], 0.12)

    def test_comparison_filters_and_preserves_rows_missing_from_one_scenario(self) -> None:
        rows = [
            {
                "Scenario": "base",
                "Technology": "solar",
                "Region": "North",
                "eligibility_share_%": 40,
                "available_area_km2": 100,
                "power_potential_TW": 0.5,
            },
            {
                "Scenario": "high",
                "Technology": "solar",
                "Region": "South",
                "eligibility_share_%": 50,
                "available_area_km2": 120,
                "power_potential_TW": 0.6,
            },
            {
                "Scenario": "high",
                "Technology": "onshorewind",
                "Region": "South",
                "eligibility_share_%": 30,
                "available_area_km2": 80,
                "power_potential_TW": 0.2,
            },
        ]

        comparison = build_scenario_comparison(
            rows, "base", "high", technology="solar"
        )

        self.assertEqual({row["Region"] for row in comparison}, {"North", "South"})
        north = next(row for row in comparison if row["Region"] == "North")
        south = next(row for row in comparison if row["Region"] == "South")
        self.assertIsNone(north["comparison_available_area_km2"])
        self.assertIsNone(north["difference_available_area_km2"])
        self.assertIsNone(south["baseline_available_area_km2"])

    def test_numeric_result_accepts_scientific_notation_and_rejects_invalid_values(self) -> None:
        self.assertEqual(numeric_result("2.77e+04"), 27700.0)
        self.assertIsNone(numeric_result("not a number"))
        self.assertIsNone(numeric_result(None))

    def test_available_land_identity_handles_region_and_scenario_underscores(self) -> None:
        path = Path(
            "data/Region_with_underscores/available_land/"
            "Region_with_underscores_onshorewind_policy_high_available_land.tif"
        )
        resource_path = path.with_name(
            "Region_with_underscores_solar_reference_available_land_ResourceValues.tif"
        )

        self.assertEqual(
            MapTab._available_land_identity("Region_with_underscores", path),
            ("onshorewind", "policy_high"),
        )
        self.assertEqual(
            MapTab._available_land_identity("Region_with_underscores", resource_path),
            ("solar", "reference"),
        )

    def test_layer_discovery_omits_old_resolution_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            region_dir = data_dir / "Region" / "available_land"
            region_dir.mkdir(parents=True)
            current = region_dir / "Region_solar_base_available_land.tif"
            backup = region_dir / "Region_solar_base_available_land.old_resolution.tif"
            current.write_text("current", encoding="utf-8")
            backup.write_text("backup", encoding="utf-8")

            discovered = MapTab._discover_region_layers(data_dir)

        self.assertEqual(discovered, {"Region": [current]})


if __name__ == "__main__":
    unittest.main()
