rule results_analysis:
    input:
        rasters=lambda wildcards: exclusion_result_targets(),
        metadata=lambda wildcards: exclusion_metadata_targets(),
    output:
        gpkg=Path("aggregated_available_land.gpkg"),
        json=Path("aggregated_available_land.json"),
        csv=Path("aggregated_available_land.csv"),
    shell:
        (
            "python -u -m lava.utils.results_analysis --root . "
            "--output {output.gpkg} --json-output {output.json} "
            "--csv-output {output.csv}"
        )
