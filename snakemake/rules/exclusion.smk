from utils.exclusion_inputs import resolve_exclusion_inputs


def exclusion_inputs(wildcards):
    spatial_checkpoint = checkpoints.spatial_data_prep.get(
        region=wildcards.region
    )
    return resolve_exclusion_inputs(
        region=wildcards.region,
        technology=wildcards.technology,
        scenario=wildcards.scenario,
        local_crs_path=spatial_checkpoint.output.local_crs,
    )


rule exclusion:
    input:
        exclusion_inputs
    output:
        raster=Path("data")
        / "{region}"
        / "available_land"
        / "{region}_{technology}_{scenario}_available_land.tif",
        info=Path("data")
        / "{region}"
        / "available_land"
        / "{region}_{technology}_{scenario}_exclusion_info.json",
    params:
        method="snakemake"
    shell:
        (
            "python Exclusion.py --region {wildcards.region} "
            "--technology {wildcards.technology} --method {params.method} --scenario {wildcards.scenario}"
        )
