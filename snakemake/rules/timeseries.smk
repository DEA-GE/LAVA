def timeseries_raster_input(wildcards):
    if not config_main["available_land"]["enable"]:
        return []
    template = config_main["available_land"]["raster"]
    return template.format(
        study_region_name=wildcards.region,
        technology=wildcards.technology,
        scenario=wildcards.scenario,
    )


def timeseries_weather_input(wildcards):
    if stages.get("weather_data_prep"):
        return logpath(
            wildcards.region,
            f"weather_data_prep_{wildcards.weather_year}.done",
        ).as_posix()
    return str(
        Path(config_main["cutout_dir"])
        / f"{config_main['cutout_name'].format(year=wildcards.weather_year)}.nc"
    )


rule timeseries:
    input:
        spatial=Path("data") / "{region}" / "{region}_local_CRS.pkl",
        weather=timeseries_weather_input,
        raster=timeseries_raster_input,
    output:
        profile=Path("data")
        / "{region}"
        / "0_profiles"
        / "{region}_{technology}_{scenario}_profile_{weather_year}.csv",
        done=touch(logpath(
            "{region}",
            "timeseries_{technology}_{weather_year}_{scenario}.done",
        )),
    shell:
        (
            "python timeseries.py --region {wildcards.region} "
            "--technology {wildcards.technology} "
            "--weather_year {wildcards.weather_year} "
            "--scenario {wildcards.scenario}"
        )
