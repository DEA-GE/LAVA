rule exclusion:
    output:
        Path("data")
        / "{region}"
        / "available_land"
        / "{region}_{technology}_{scenario}_available_land.tif"
    params:
        method="snakemake"
    shell:
        (
            "python Exclusion.py --region {wildcards.region} "
            "--technology {wildcards.technology} --method {params.method} --scenario {wildcards.scenario}"
        )
