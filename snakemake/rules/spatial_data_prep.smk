import subprocess

from utils.exclusion_inputs import validate_region_exclusion_inputs


ADVANCED_DATA_PREP_CONFIG = Path(
    "configs/advanced_settings/advanced_data_prep_settings.yaml"
)
if not ADVANCED_DATA_PREP_CONFIG.is_file():
    ADVANCED_DATA_PREP_CONFIG = Path(
        "configs/advanced_settings/advanced_data_prep_settings_template.yaml"
    )


checkpoint spatial_data_prep:
    input:
        config="configs/config.yaml",
        advanced_config=ADVANCED_DATA_PREP_CONFIG,
        script="spatial_data_prep.py",
        validator="utils/exclusion_inputs.py"
    output:
        local_crs=Path("data") / "{region}" / "{region}_local_CRS.pkl"
    resources:
        openeo_req=1
    params:
        method="snakemake",
        configured_region=lambda wildcards: configured_region_name(wildcards.region)
    run:
        checkpoint_path = Path(output.local_crs)
        checkpoint_valid = False
        try:
            # If Snakemake scheduled this checkpoint, an older completion file
            # must not survive a failed refresh.
            checkpoint_path.unlink(missing_ok=True)
            subprocess.run(
                [
                    sys.executable,
                    "-u",
                    str(input.script),
                    "--region",
                    str(params.configured_region),
                    "--method",
                    str(params.method),
                ],
                cwd=PROJECT_ROOT,
                check=True,
            )
            if not checkpoint_path.is_file():
                raise RuntimeError(
                    "Spatial data preparation did not create its CRS checkpoint "
                    f"output: {checkpoint_path}"
                )

            if stages.get("exclusion"):
                selected_scenarios = {
                    technology: get_scenarios_for_technology(technology)
                    for technology in technologies
                }
                invalid_by_job = validate_region_exclusion_inputs(
                    region=str(wildcards.region),
                    technology_scenarios=selected_scenarios,
                    local_crs_path=checkpoint_path,
                    project_root=PROJECT_ROOT,
                )
                if invalid_by_job:
                    details = []
                    for (technology, scenario), invalid in invalid_by_job.items():
                        details.append(f"  {technology} / {scenario}:")
                        details.extend(
                            f"    - {path} ({reason})"
                            for path, reason in invalid.items()
                        )
                    raise RuntimeError(
                        "Spatial data preparation is incomplete for "
                        f"{wildcards.region}. Required exclusion inputs failed "
                        "validation:\n"
                        + "\n".join(details)
                    )
            checkpoint_valid = True
        finally:
            if not checkpoint_valid:
                checkpoint_path.unlink(missing_ok=True)
