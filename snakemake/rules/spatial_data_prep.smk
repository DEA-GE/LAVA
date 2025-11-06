rule spatial_data_prep:
    output:
        touch(logpath("{region}", "spatial_data_prep.done"))
    resources:
        openeo_req=1
    params:
        method="snakemake"
    shell:
        "python spatial_data_prep.py --region {wildcards.region} --method {params.method}"