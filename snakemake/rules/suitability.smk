rule suitability:
    input:
        lambda wildcards: expand(
            Path("data")
            / "{region}"
            / "available_land"
            / "{region}_{technology}_{scenario}_available_land.tif",
            region=[wildcards.region],
            technology=technologies,
            scenario=[wildcards.scenario],
        )
    output:
        touch(logpath("{region}", "suitability_{scenario}.done"))
    params:
        method="snakemake"
    shell:
        "python suitability.py --region {wildcards.region} --method {params.method} --scenario {wildcards.scenario}"