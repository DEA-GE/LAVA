import json
import tempfile
import unittest
from pathlib import Path

from utils.delete_scenario_results import (
    collect_scenario_files,
    delete_scenario_outputs,
    discover_scenarios,
)
from utils.results_analysis import (
    ResultsAnalysisError,
    _build_groups,
    aggregate_available_land,
)
import numpy as np
import rasterio
from rasterio.transform import from_origin


class ResultsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_raster(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="uint8",
            crs="EPSG:3857",
            transform=from_origin(0, 200, 100, 100),
            nodata=0,
        ) as dataset:
            dataset.write(np.array([[1, 0], [0, 0]], dtype="uint8"), 1)

    def _write_result(
        self,
        region: str,
        technology: str,
        scenario: str,
        *,
        available: float,
        study_area: float | None,
        legacy: bool = False,
    ) -> tuple[Path, Path]:
        folder = self.root / "data" / region / "available_land"
        folder.mkdir(parents=True, exist_ok=True)
        if legacy:
            info_path = folder / f"{region}_{scenario}_{technology}_exclusion_info.json"
            raster_path = folder / (
                f"{region}_{technology}_{scenario}_available_land_EPSG3035.tif"
            )
            payload = {
                "technology": technology,
                "scenario": scenario,
                "eligibility_share": available / study_area,
                "available_area_km2": available / 1e6,
                "power_potential_MW": available / 100,
            }
        else:
            info_path = folder / f"{region}_{technology}_{scenario}_exclusion_info.json"
            raster_path = folder / f"{region}_{technology}_{scenario}_available_land.tif"
            payload = {
                "technology": technology,
                "scenario": scenario,
                "eligibility_share": available / study_area,
                "available_area_m2": available,
                "study_area_m2": study_area,
                "power_potential_MW": available / 100,
            }
        info_path.write_text(json.dumps(payload), encoding="utf-8")
        self._write_raster(raster_path)
        return info_path, raster_path

    def test_metadata_supports_current_and_legacy_output_names(self):
        self._write_result(
            "Region_with_underscores", "solar", "scenario_with_underscores",
            available=500_000, study_area=1_000_000, legacy=True
        )
        groups = _build_groups(self.root)
        items = groups[("solar", "scenario_with_underscores")]
        self.assertEqual(items[0][0], "Region_with_underscores")
        self.assertTrue(items[0][1].name.endswith("_EPSG3035.tif"))
        self.assertEqual(items[0][2]["available_area"], 500_000)
        self.assertEqual(items[0][2]["study_area"], 1_000_000)

    def test_aggregation_is_area_weighted_and_writes_all_formats(self):
        self._write_result(
            "Small", "onshorewind", "shared", available=50, study_area=100
        )
        self._write_result(
            "Large", "onshorewind", "shared", available=900, study_area=1_000
        )
        self._write_result(
            "Small", "solar", "shared", available=25, study_area=100
        )
        gpkg = self.root / "aggregated_available_land.gpkg"
        metrics = self.root / "aggregated_available_land.json"
        csv_path = self.root / "aggregated_available_land.csv"
        aggregate_available_land(self.root, gpkg, metrics, csv_output=csv_path)

        payload = json.loads(metrics.read_text(encoding="utf-8"))
        wind = next(item for item in payload if item["technology"] == "onshorewind")
        self.assertEqual(wind["aggregated"]["eligibility_share_%"], 86.36)
        self.assertTrue(gpkg.is_file())
        self.assertTrue(csv_path.is_file())

    def test_invalid_metadata_does_not_replace_last_successful_outputs(self):
        folder = self.root / "data" / "Broken" / "available_land"
        folder.mkdir(parents=True)
        (folder / "Broken_solar_test_exclusion_info.json").write_text(
            "not-json", encoding="utf-8"
        )
        gpkg = self.root / "aggregated_available_land.gpkg"
        metrics = self.root / "aggregated_available_land.json"
        csv_path = self.root / "aggregated_available_land.csv"
        for path in (gpkg, metrics, csv_path):
            path.write_text("last-success", encoding="utf-8")
        with self.assertRaises(ResultsAnalysisError):
            aggregate_available_land(self.root, gpkg, metrics, csv_output=csv_path)
        for path in (gpkg, metrics, csv_path):
            self.assertEqual(path.read_text(encoding="utf-8"), "last-success")

    def test_deletion_uses_exact_scenario_boundaries_and_invalidates_aggregates(self):
        self._write_result(
            "Region", "solar", "base", available=50, study_area=100
        )
        _, longer_raster = self._write_result(
            "Region", "solar", "base_extended", available=50, study_area=100
        )
        aggregate = self.root / "aggregated_available_land.json"
        aggregate.write_text("[]", encoding="utf-8")

        self.assertEqual(discover_scenarios(self.root), ["base", "base_extended"])
        selected = collect_scenario_files(self.root, "base")
        self.assertTrue(selected)
        self.assertTrue(all("base_extended" not in path.name for path in selected))
        deleted, invalidated = delete_scenario_outputs(self.root, "base")

        self.assertEqual(len(deleted), 2)
        self.assertEqual(invalidated, [aggregate])
        self.assertTrue(longer_raster.exists())
        self.assertIn(
            "Region,solar,base_extended",
            (self.root / "data" / "Region" / "scenario_runs.log").read_text(
                encoding="utf-8"
            ),
        )


if __name__ == "__main__":
    unittest.main()
