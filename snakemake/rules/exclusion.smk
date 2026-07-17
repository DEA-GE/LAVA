rule exclusion:
    output:
        touch(logpath("{region}", "exclusion_{technology}_{scenario}.done"))
    params:
        method="snakemake"
    shell:
        (
            "python Exclusion.py --region {wildcards.region} "
            "--technology {wildcards.technology} --method {params.method} --scenario {wildcards.scenario}"
        )
