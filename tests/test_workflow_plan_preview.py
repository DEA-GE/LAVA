from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tkinter_app.run_tab import build_workflow_plan_rows


class WorkflowPlanPreviewTests(unittest.TestCase):
    def test_expands_requested_targets_and_implicit_spatial_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rows = build_workflow_plan_rows(
                ["Region"],
                ["solar", "onshorewind"],
                {"solar": ["base"], "onshorewind": ["base", "high"]},
                ["exclusion", "weather_data_prep"],
                ["2020", "2021"],
                project_root=Path(temp_dir),
            )

        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["stage"], "Spatial data preparation (dependency)")
        exclusion_rows = [row for row in rows if row["stage"] == "Land exclusion"]
        self.assertEqual(
            {(row["technology"], row["scenario"]) for row in exclusion_rows},
            {("solar", "base"), ("onshorewind", "base"), ("onshorewind", "high")},
        )
        weather_rows = [
            row for row in rows if row["stage"] == "Weather data preparation"
        ]
        self.assertEqual(
            {row["weather_year"] for row in weather_rows}, {"2020", "2021"}
        )

    def test_existing_target_does_not_claim_that_it_is_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = (
                root
                / "data"
                / "Region"
                / "available_land"
                / "Region_solar_base_available_land.tif"
            )
            target.parent.mkdir(parents=True)
            target.write_text("result", encoding="utf-8")
            rows = build_workflow_plan_rows(
                ["Region"],
                ["solar"],
                {"solar": ["base"]},
                ["exclusion"],
                [],
                project_root=root,
            )

        exclusion = next(row for row in rows if row["stage"] == "Land exclusion")
        self.assertEqual(exclusion["status"], "Output exists; check freshness")
        self.assertEqual(exclusion["status_level"], "existing")

    def test_spatial_preflight_status_overrides_file_existence(self) -> None:
        spatial_plan = {
            "regions": {
                "Region": {
                    "configured_region": "Region",
                    "region": "Region",
                    "ready": True,
                    "requires_preparation": False,
                    "blocking": False,
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            rows = build_workflow_plan_rows(
                ["Region"],
                ["solar"],
                {"solar": ["base"]},
                ["exclusion"],
                [],
                project_root=Path(temp_dir),
                spatial_plan=spatial_plan,
            )

        spatial = rows[0]
        self.assertEqual(spatial["status"], "Prepared inputs reusable")
        self.assertEqual(spatial["status_level"], "ready")

    def test_missing_scenario_is_shown_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rows = build_workflow_plan_rows(
                ["Region"],
                ["solar"],
                {"solar": []},
                ["exclusion"],
                [],
                project_root=Path(temp_dir),
            )

        exclusion = next(row for row in rows if row["stage"] == "Land exclusion")
        self.assertEqual(exclusion["scenario"], "Not configured")
        self.assertEqual(exclusion["status_level"], "blocked")


if __name__ == "__main__":
    unittest.main()
