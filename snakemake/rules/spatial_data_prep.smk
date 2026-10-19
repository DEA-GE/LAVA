rule spatial_data_prep:
    output:
        touch(logpath("{region}", "spatial_data_prep.done"))
    resources:
        openeo_req=1
    params:
        method="snakemake"
    shell:
        "python -m lava.spatial_data_prep --region {wildcards.region:q} --method {params.method:q}"