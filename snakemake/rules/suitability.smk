rule suitability:
    input:
        expand(logpath("{region}", "exclusion_{technology}_{scenario}.done"), region=regions, technology=technologies, scenario=scenario)
    output:
        touch(logpath("{region}", "suitability_{scenario}.done"))
    params:
        method="snakemake",
        scenario=scenario
    shell:
        "python suitability.py --region {wildcards.region} --method {params.method} --scenario {params.scenario}"