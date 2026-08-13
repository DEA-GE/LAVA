"""Plan and validate spatial preparation required by exclusion jobs.

The planner is deliberately read-only.  It translates the selected Snakemake
regions, technologies, and scenarios into the exact files used by Exclusion.py,
then inspects the prepared cache.  The UI uses the result to decide whether the
spatial-data checkpoint must be forced before exclusion can run.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml
from pyproj import CRS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.exclusion_inputs import (
    inspect_prepared_input_files,
    resolve_exclusion_inputs,
)
from utils.tech_config import resolve_selected_scenarios
from utils.region_names import canonical_region_name


LANDCOVER_METADATA_VERSION = 1
LANDCOVER_RESOLUTION_REL_TOLERANCE = 0.05


def clean_region_name(region_name: str) -> str:
    """Backward-compatible alias for the shared canonical region slug."""
    return canonical_region_name(region_name)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        document = yaml.load(stream, Loader=yaml.FullLoader) or {}
    if not isinstance(document, dict):
        raise TypeError(f"Expected a YAML mapping in {path}.")
    return document


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _enabled(value: Any) -> bool:
    return value not in (None, False, 0, "", "0")


def _crs_tag(crs: CRS) -> str:
    authority = crs.to_authority()
    if authority:
        return "".join(authority)
    return crs.to_string().replace(":", "_")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _float_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def resolve_custom_study_area_path(
    *,
    configured_region: str,
    filename_template: str,
    project_root: str | Path = ".",
) -> tuple[Path, bool]:
    """Resolve a custom study area using its original region spelling.

    The name supplied by the workflow/GADM selection is authoritative.  A
    cleaned-name candidate is accepted only as a backward-compatible fallback
    for caches created by older LAVA versions.  The boolean return value tells
    callers whether that fallback was selected.
    """
    root = Path(project_root)
    custom_directory = root / "Raw_Spatial_Data" / "custom_study_area"
    try:
        original_name = filename_template.format(region_name=configured_region)
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"Invalid custom study-area filename template {filename_template!r}: {exc}"
        ) from exc
    original_path = custom_directory / original_name
    if original_path.is_file():
        return original_path, False

    cleaned_region = canonical_region_name(configured_region)
    cleaned_name = filename_template.format(region_name=cleaned_region)
    cleaned_path = custom_directory / cleaned_name
    if cleaned_path != original_path and cleaned_path.is_file():
        return cleaned_path, True
    return original_path, False


def resolution_matches(
    actual: float,
    requested: float,
    *,
    relative_tolerance: float = LANDCOVER_RESOLUTION_REL_TOLERANCE,
) -> bool:
    """Return whether a raster resolution is compatible with the request."""
    return math.isclose(
        abs(float(actual)),
        abs(float(requested)),
        rel_tol=relative_tolerance,
        abs_tol=1e-12,
    )


def inspect_raster_resolution(
    path: str | Path,
    requested_resolution: Any,
    expected_crs: Any = None,
) -> dict[str, Any]:
    """Inspect a raster's CRS and pixel size without reading its pixel array."""
    raster_path = Path(path)
    requested = _float_value(requested_resolution)
    result: dict[str, Any] = {
        "path": str(raster_path),
        "exists": raster_path.is_file(),
        "requested_resolution": requested,
        "actual_resolution": None,
        "crs": None,
        "compatible": False,
        "reason": "missing",
    }
    if not raster_path.is_file():
        return result
    try:
        import rasterio

        with rasterio.open(raster_path) as dataset:
            actual = [abs(float(dataset.res[0])), abs(float(dataset.res[1]))]
            result["actual_resolution"] = actual
            result["crs"] = dataset.crs.to_string() if dataset.crs else None
            if dataset.width <= 0 or dataset.height <= 0:
                result["reason"] = "raster has no pixels"
                return result
            if expected_crs is not None and (
                dataset.crs is None
                or CRS.from_user_input(dataset.crs) != CRS.from_user_input(expected_crs)
            ):
                result["reason"] = (
                    f"raster CRS {result['crs']} does not match expected "
                    f"{CRS.from_user_input(expected_crs).to_string()}"
                )
                return result
            if requested is not None and not all(
                resolution_matches(value, requested) for value in actual
            ):
                result["reason"] = (
                    f"actual resolution {actual} does not match requested "
                    f"resolution {requested}"
                )
                return result
    except Exception as exc:
        result["reason"] = f"raster cannot be inspected: {exc}"
        return result
    result["compatible"] = True
    result["reason"] = "compatible"
    return result


def landcover_metadata_path(region_directory: str | Path) -> Path:
    return Path(region_directory) / ".spatial_prep" / "landcover.json"


def write_landcover_metadata(
    *,
    region_directory: str | Path,
    source: str,
    collection: str | None,
    requested_resolution: Any,
    global_raster: str | Path,
    local_raster: str | Path,
    pixel_size_file: str | Path,
) -> Path:
    """Atomically record the recipe and observed properties of land cover."""
    global_state = inspect_raster_resolution(
        global_raster, requested_resolution, expected_crs="EPSG:4326"
    )
    local_state = inspect_raster_resolution(local_raster, None)
    if not global_state["compatible"]:
        raise RuntimeError(
            "Cannot record land-cover metadata: " + str(global_state["reason"])
        )
    pixel_size_path = Path(pixel_size_file)
    with pixel_size_path.open("r", encoding="utf-8") as stream:
        pixel_size = float(json.load(stream))
    payload = {
        "metadata_version": LANDCOVER_METADATA_VERSION,
        "source": source,
        "collection": collection,
        "requested_resolution": _float_value(requested_resolution),
        "global_raster": str(Path(global_raster)),
        "global_crs": global_state["crs"],
        "actual_global_resolution": global_state["actual_resolution"],
        "local_raster": str(Path(local_raster)),
        "local_crs": local_state["crs"],
        "actual_local_resolution": local_state["actual_resolution"],
        "pixel_size": pixel_size,
    }
    metadata_path = landcover_metadata_path(region_directory)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = metadata_path.with_suffix(".json.partial")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary_path.replace(metadata_path)
    return metadata_path


def inspect_landcover_bundle(
    *,
    region: str,
    project_root: str | Path,
    config: Mapping[str, Any],
    local_crs_path: str | Path,
) -> dict[str, Any]:
    """Validate the openEO land-cover cache, including its derived local files."""
    root = Path(project_root)
    data_directory = root / "data" / region
    source = str(config.get("landcover_source") or "").strip()
    requested_resolution = config.get("resolution_landcover")
    result: dict[str, Any] = {
        "component": "landcover",
        "source": source,
        "requested_resolution": _float_value(requested_resolution),
        "ready": True,
        "issues": [],
        "files": [],
    }
    if source != "openeo":
        return result

    local_path = Path(local_crs_path)
    if not local_path.is_file():
        result["ready"] = False
        result["issues"].append(
            {"path": str(local_path), "reason": "local CRS checkpoint is missing"}
        )
        return result
    try:
        with local_path.open("rb") as stream:
            local_crs = CRS.from_user_input(pickle.load(stream))
    except Exception as exc:
        result["ready"] = False
        result["issues"].append(
            {"path": str(local_path), "reason": f"local CRS is unreadable: {exc}"}
        )
        return result

    local_tag = _crs_tag(local_crs)
    global_raster = data_directory / f"landcover_openeo_{region}_EPSG4326.tif"
    local_raster = data_directory / f"landcover_openeo_{region}_{local_tag}.tif"
    pixel_size = data_directory / f"pixel_size_{region}_{local_tag}.json"
    metadata = landcover_metadata_path(data_directory)
    result["files"] = [
        str(global_raster),
        str(local_raster),
        str(pixel_size),
        str(metadata),
    ]

    global_state = inspect_raster_resolution(
        global_raster, requested_resolution, expected_crs="EPSG:4326"
    )
    result["global_raster"] = global_state
    if not global_state["compatible"]:
        result["issues"].append(
            {"path": str(global_raster), "reason": global_state["reason"]}
        )

    local_state = inspect_raster_resolution(
        local_raster, None, expected_crs=local_crs
    )
    result["local_raster"] = local_state
    if not local_state["compatible"]:
        result["issues"].append(
            {"path": str(local_raster), "reason": local_state["reason"]}
        )

    expected_local_resolution = None
    if local_state.get("actual_resolution"):
        expected_local_resolution = float(local_state["actual_resolution"][0])
    try:
        with pixel_size.open("r", encoding="utf-8") as stream:
            observed_pixel_size = float(json.load(stream))
        if expected_local_resolution is not None and not resolution_matches(
            observed_pixel_size, expected_local_resolution, relative_tolerance=0.01
        ):
            raise ValueError(
                f"pixel size {observed_pixel_size} does not match local raster "
                f"resolution {expected_local_resolution}"
            )
        result["pixel_size"] = observed_pixel_size
    except Exception as exc:
        result["issues"].append(
            {"path": str(pixel_size), "reason": f"pixel-size metadata is invalid: {exc}"}
        )

    # Metadata is optional for legacy caches.  If present, it must agree with
    # the current request; a compatible legacy raster can be adopted later.
    if metadata.is_file():
        try:
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            recorded = _float_value(payload.get("requested_resolution"))
            requested = _float_value(requested_resolution)
            if recorded != requested and not (
                recorded is not None
                and requested is not None
                and resolution_matches(recorded, requested)
            ):
                raise ValueError(
                    f"recorded resolution {recorded} does not match requested {requested}"
                )
            if payload.get("source") != source:
                raise ValueError(
                    f"recorded source {payload.get('source')!r} does not match {source!r}"
                )
            result["metadata"] = "compatible"
        except Exception as exc:
            result["issues"].append(
                {"path": str(metadata), "reason": f"metadata is incompatible: {exc}"}
            )
    else:
        result["metadata"] = "legacy cache (no metadata)"

    result["ready"] = not result["issues"]
    return result


def _deduplicate(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items))


def build_spatial_prep_plan(
    *,
    project_root: str | Path = ".",
    config_path: str | Path = "configs/config.yaml",
    workflow_path: str | Path = "configs/config_snakemake.yaml",
) -> dict[str, Any]:
    """Build a read-only preparation plan for selected exclusion jobs."""
    root = Path(project_root).resolve()
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = root / config_file
    workflow_file = Path(workflow_path)
    if not workflow_file.is_absolute():
        workflow_file = root / workflow_file
    config = _load_yaml_mapping(config_file)
    workflow = _load_yaml_mapping(workflow_file)
    stage_mapping = workflow.get("stages") or {}
    exclusion_enabled = isinstance(stage_mapping, Mapping) and _enabled(
        stage_mapping.get("exclusion")
    )
    plan: dict[str, Any] = {
        "applicable": bool(exclusion_enabled),
        "ready": True,
        "requires_preparation": False,
        "invalid_regions": [],
        "regions": {},
        "external_issues": [],
    }
    if not exclusion_enabled:
        plan["message"] = "Exclusion is not selected; no spatial preparation gate is needed."
        return plan

    configured_regions = _as_list(workflow.get("study_region_name"))
    technologies = _as_list(workflow.get("technologies"))
    global_scenarios = _as_list(workflow.get("scenarios"))
    scenario_mapping = workflow.get("technology_scenarios") or {}
    if not isinstance(scenario_mapping, dict):
        scenario_mapping = {}

    for configured_region in configured_regions:
        region = canonical_region_name(configured_region)
        data_directory = root / "data" / region
        local_crs_path = data_directory / f"{region}_local_CRS.pkl"
        region_plan: dict[str, Any] = {
            "configured_region": configured_region,
            "region": region,
            "ready": True,
            "jobs": [],
            "required_files": [],
            "issues": [],
            "components": {},
        }
        custom_template = str(config.get("custom_study_area_filename") or "").strip()
        if custom_template:
            try:
                study_area_path, used_legacy_name = resolve_custom_study_area_path(
                    configured_region=configured_region,
                    filename_template=custom_template,
                    project_root=root,
                )
                region_plan["study_area"] = {
                    "path": str(study_area_path),
                    "legacy_cleaned_name": used_legacy_name,
                }
                if not study_area_path.is_file():
                    issue = {
                        "path": str(study_area_path),
                        "reason": (
                            "custom study-area source is missing; {region_name} "
                            "is resolved with the original configured region name"
                        ),
                        "repairable": False,
                    }
                    region_plan["issues"].append(issue)
                    plan["external_issues"].append({"region": region, **issue})
            except ValueError as exc:
                issue = {
                    "path": custom_template,
                    "reason": str(exc),
                    "repairable": False,
                }
                region_plan["issues"].append(issue)
                plan["external_issues"].append({"region": region, **issue})
        if not local_crs_path.is_file():
            region_plan["issues"].append(
                {
                    "path": str(local_crs_path),
                    "reason": "local CRS checkpoint is missing",
                    "repairable": True,
                }
            )
        else:
            required_files: list[str] = []
            for technology in technologies:
                scenarios = resolve_selected_scenarios(
                    technology, global_scenarios, scenario_mapping
                )
                for scenario in scenarios:
                    try:
                        job_files = resolve_exclusion_inputs(
                            region=region,
                            technology=technology,
                            scenario=scenario,
                            local_crs_path=local_crs_path,
                            project_root=root,
                        )
                    except Exception as exc:
                        region_plan["issues"].append(
                            {
                                "path": str(local_crs_path),
                                "reason": (
                                    f"cannot resolve {technology}/{scenario} inputs: {exc}"
                                ),
                                "repairable": False,
                            }
                        )
                        continue
                    region_plan["jobs"].append(
                        {
                            "technology": technology,
                            "scenario": scenario,
                            "files": job_files,
                        }
                    )
                    required_files.extend(job_files)
            required_files = _deduplicate(required_files)
            region_plan["required_files"] = required_files
            for path_text, reason in inspect_prepared_input_files(required_files).items():
                path = Path(path_text)
                repairable = _is_within(path, data_directory)
                issue = {
                    "path": path_text,
                    "reason": reason,
                    "repairable": repairable,
                }
                region_plan["issues"].append(issue)
                if not repairable:
                    plan["external_issues"].append(
                        {"region": region, **issue}
                    )

            landcover_required = any(
                Path(path).name.startswith(f"landcover_openeo_{region}_")
                for path in required_files
            )
            if landcover_required:
                landcover = inspect_landcover_bundle(
                    region=region,
                    project_root=root,
                    config=config,
                    local_crs_path=local_crs_path,
                )
                region_plan["components"]["landcover"] = landcover
                existing_issue_paths = {
                    str(item.get("path")) for item in region_plan["issues"]
                }
                for component_issue in landcover["issues"]:
                    if str(component_issue["path"]) not in existing_issue_paths:
                        region_plan["issues"].append(
                            {**component_issue, "repairable": True}
                        )

        repairable_issues = [
            issue for issue in region_plan["issues"] if issue.get("repairable")
        ]
        blocking_issues = [
            issue for issue in region_plan["issues"] if not issue.get("repairable")
        ]
        region_plan["requires_preparation"] = bool(repairable_issues)
        region_plan["ready"] = not region_plan["issues"]
        region_plan["blocking"] = bool(blocking_issues)
        plan["regions"][region] = region_plan
        if repairable_issues:
            plan["invalid_regions"].append(region)

    plan["invalid_regions"] = _deduplicate(plan["invalid_regions"])
    plan["requires_preparation"] = bool(plan["invalid_regions"])
    plan["ready"] = all(
        region_plan["ready"] for region_plan in plan["regions"].values()
    )
    return plan


def format_spatial_prep_plan(plan: Mapping[str, Any]) -> list[str]:
    """Return concise human-readable lines for logs and the UI."""
    if not plan.get("applicable"):
        return [str(plan.get("message", "Spatial preparation check is not applicable."))]
    if plan.get("ready"):
        return ["Spatial preparation check: all required prepared inputs are compatible."]
    lines: list[str] = []
    invalid_regions = plan.get("invalid_regions") or []
    if invalid_regions:
        lines.append(
            "Spatial preparation will rerun for: " + ", ".join(invalid_regions) + "."
        )
    for region, region_plan in (plan.get("regions") or {}).items():
        issues = region_plan.get("issues") or []
        if not issues:
            continue
        lines.append(f"{region}:")
        for issue in issues:
            path = Path(str(issue.get("path", ""))).name or str(issue.get("path", ""))
            lines.append(f"  - {path}: {issue.get('reason', 'incompatible')}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--workflow", default="configs/config_snakemake.yaml")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    plan = build_spatial_prep_plan(
        project_root=args.project_root,
        config_path=args.config,
        workflow_path=args.workflow,
    )
    if args.as_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print("\n".join(format_spatial_prep_plan(plan)))
    return 0 if plan.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
