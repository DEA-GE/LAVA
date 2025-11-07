rule exclusion:
    input:
        logpath("{region}", "spatial_data_prep.done")
    output:
        touch(logpath("{region}", "exclusion_{technology}_{scenario}.done"))
    params:
        method="snakemake",
        scenario=scenario 
    shell:
        (
            "python Exclusion.py --region {wildcards.region} "
            "--technology {wildcards.technology} --method {params.method} --scenario {params.scenario}"
        )
