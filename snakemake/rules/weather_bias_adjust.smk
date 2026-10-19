rule weather_bias_adjust:
    input:
        expand(logpath("{region}", "weather_data_prep_{weather_year}.done"), region=regions, weather_year=weather_years)
    output:
        touch(logpath("{region}", "weather_bias_adjust.done"))
    params:
        method="snakemake"
    shell:
        "python -m lava.weather_bias_adjust --region {wildcards.region} --method {params.method}"