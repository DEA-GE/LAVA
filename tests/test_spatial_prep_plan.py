import tempfile
import unittest
import json
import pickle
from pathlib import Path

import numpy as np
import rasterio
import yaml
from rasterio.transform import from_origin
from pyproj import CRS

from utils.spatial_prep_plan import (
    build_spatial_prep_plan,
    inspect_landcover_bundle,
    inspect_raster_resolution,
    resolve_custom_study_area_path,
)
from utils.region_names import RegionNames, canonical_region_name


class SpatialPreparationPlanTests(unittest.TestCase):
    def test_manual_and_snakemake_share_the_same_generated_region_name(self) -> None:
        original = "Sjælland"
        manual_output_region = canonical_region_name(original)
        snakemake_identity = RegionNames.from_original(original)

        self.assertEqual(manual_output_region, "Sjaelland")
        self.assertEqual(snakemake_identity.original, original)
        self.assertEqual(snakemake_identity.canonical, manual_output_region)

    def test_custom_study_area_prefers_original_region_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom_directory = root / "Raw_Spatial_Data" / "custom_study_area"
            custom_directory.mkdir(parents=True)
            original = custom_directory / "Sjælland.geojson"
            cleaned = custom_directory / "Sjaelland.geojson"
            original.write_text("{}", encoding="utf-8")
            cleaned.write_text("{}", encoding="utf-8")

            path, used_legacy_name = resolve_custom_study_area_path(
                configured_region="Sjælland",
                filename_template="{region_name}.geojson",
                project_root=root,
            )

            self.assertEqual(path, original)
            self.assertFalse(used_legacy_name)

    def test_custom_study_area_accepts_cleaned_legacy_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom_directory = root / "Raw_Spatial_Data" / "custom_study_area"
            custom_directory.mkdir(parents=True)
            cleaned = custom_directory / "Sjaelland.geojson"
            cleaned.write_text("{}", encoding="utf-8")

            path, used_legacy_name = resolve_custom_study_area_path(
                configured_region="Sjælland",
                filename_template="{region_name}.geojson",
                project_root=root,
            )

            self.assertEqual(path, cleaned)
            self.assertTrue(used_legacy_name)

    def test_raster_resolution_is_read_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landcover.tif"
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=4,
                height=3,
                count=1,
                dtype="uint8",
                crs="EPSG:4326",
                transform=from_origin(10, 20, 0.1, 0.1),
            ) as dataset:
                dataset.write(np.ones((1, 3, 4), dtype=np.uint8))

            compatible = inspect_raster_resolution(path, 0.1)
            incompatible = inspect_raster_resolution(path, 0.01)

            self.assertTrue(compatible["compatible"])
            self.assertEqual(compatible["actual_resolution"], [0.1, 0.1])
            self.assertFalse(incompatible["compatible"])
            self.assertIn("does not match", incompatible["reason"])

    def test_landcover_bundle_detects_stale_pixel_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            region = "TestRegion"
            data_directory = root / "data" / region
            data_directory.mkdir(parents=True)
            local_crs_path = data_directory / f"{region}_local_CRS.pkl"
            with local_crs_path.open("wb") as stream:
                pickle.dump(CRS.from_epsg(32632), stream)

            rasters = (
                (
                    data_directory / f"landcover_openeo_{region}_EPSG4326.tif",
                    "EPSG:4326",
                    0.1,
                ),
                (
                    data_directory / f"landcover_openeo_{region}_EPSG32632.tif",
                    "EPSG:32632",
                    1000.0,
                ),
            )
            for path, crs, resolution in rasters:
                with rasterio.open(
                    path,
                    "w",
                    driver="GTiff",
                    width=4,
                    height=3,
                    count=1,
                    dtype="uint8",
                    crs=crs,
                    transform=from_origin(10, 20, resolution, resolution),
                ) as dataset:
                    dataset.write(np.ones((1, 3, 4), dtype=np.uint8))
            pixel_size = data_directory / f"pixel_size_{region}_EPSG32632.json"
            pixel_size.write_text(json.dumps(10.0), encoding="utf-8")

            bundle = inspect_landcover_bundle(
                region=region,
                project_root=root,
                config={
                    "landcover_source": "openeo",
                    "resolution_landcover": 0.1,
                },
                local_crs_path=local_crs_path,
            )

            self.assertFalse(bundle["ready"])
            self.assertTrue(
                any(
                    "does not match local raster" in issue["reason"]
                    for issue in bundle["issues"]
                )
            )

    def test_missing_checkpoint_requests_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            (root / "configs" / "config.yaml").write_text(
                yaml.safe_dump(
                    {
                        "landcover_source": "openeo",
                        "resolution_landcover": 0.1,
                    }
                ),
                encoding="utf-8",
            )
            (root / "configs" / "config_snakemake.yaml").write_text(
                yaml.safe_dump(
                    {
                        "study_region_name": ["Test Region"],
                        "technologies": ["solar"],
                        "technology_scenarios": {"solar": ["reference"]},
                        "stages": {"exclusion": True},
                    }
                ),
                encoding="utf-8",
            )

            plan = build_spatial_prep_plan(project_root=root)

            self.assertFalse(plan["ready"])
            self.assertTrue(plan["requires_preparation"])
            self.assertEqual(plan["invalid_regions"], ["TestRegion"])
            issue = plan["regions"]["TestRegion"]["issues"][0]
            self.assertIn("local CRS checkpoint is missing", issue["reason"])

    def test_planner_is_not_applicable_without_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            for name, document in (
                ("config.yaml", {}),
                (
                    "config_snakemake.yaml",
                    {
                        "study_region_name": ["Test"],
                        "stages": {"exclusion": False},
                    },
                ),
            ):
                (root / "configs" / name).write_text(
                    yaml.safe_dump(document), encoding="utf-8"
                )

            plan = build_spatial_prep_plan(project_root=root)

            self.assertFalse(plan["applicable"])
            self.assertTrue(plan["ready"])
            self.assertFalse(plan["requires_preparation"])


if __name__ == "__main__":
    unittest.main()
