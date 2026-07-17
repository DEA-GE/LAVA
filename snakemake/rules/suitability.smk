rule suitability:
    input:
        lambda wildcards: expand(
            logpath("{region}", "exclusion_{technology}_{scenario}.done"),
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