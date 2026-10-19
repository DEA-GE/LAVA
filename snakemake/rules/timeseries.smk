rule timeseries:
    input:
        Path("data")
        / "{region}"
        / "available_land"
        / "{region}_{technology}_{scenario}_available_land.tif",
    output:
        touch(logpath("{region}", "timeseries_{technology}_{weather_year}_{scenario}.done"))
    shell:
        (
            "python -m lava.timeseries --region {wildcards.region} "
            "--weather_year {wildcards.weather_year} "
            "--technology {wildcards.technology} "
            "--scenario {wildcards.scenario} "
        )
