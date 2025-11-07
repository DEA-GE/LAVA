rule weather_data_prep:
    output:
        # one .done per region
        touch(logpath("{region}", "weather_data_prep_{weather_year}.done"))
    params:
        method="snakemake"
    shell:
        (
            "python weather_data_prep.py --region {wildcards.region} "
            "--weather_year {wildcards.weather_year} "
            "--method {params.method} "
        )