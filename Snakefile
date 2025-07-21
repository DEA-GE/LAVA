from pathlib import Path

regions = ["Anhui", "Beijing", "Chongqing", "Fujian", "Gansu", "Guangdong", "Guangxi", "Guizhou",
          "Hainan", "Hebei", "Heilongjiang", "Henan", "Hubei", "Hunan", "Jiangsu","Jiangxi",
          "Jilin", "Liaoning", "NeiMongol", "NingxiaHui", "Qinghai", "Shaanxi", "Shandong", "Shanghai",
          "Shanxi", "Sichuan", "Tianjin", "XinjiangUygur", "Xizang", "Yunnan", "Zhejiang"]


technologies = ["solar", "onshorewind"]
scenarios = ["ref"]
weather_years = [str(y) for y in range(2010, 2019)]

def logpath(region, filename):
    return Path("data") / region / "snakemake_log" / filename

for region in regions:
    Path(f"data/{region}/snakemake_log").mkdir(parents=True, exist_ok=True)


rule all:
    input:
        expand(logpath("{region}", "exclusion_{technology}_{scenario}.done"), region=regions, technology=technologies, scenario=scenarios)
        expand(logpath(region, "suitability.done"), region=regions, scenario=scenarios)
        expand(logpath(region, "energy_profiles_{technology}_{weather_year}.done"), region=regions, technology=technologies, scenario=scenarios, weather_year=weather_years)

rule spatial_data_prep:
    output:
        touch(logpath("{region}", "spatial_data_prep.done"))
    params:
        region=lambda wc: wc.region
    script:
        "spatial_data_prep.py"

rule exclusion:
    input:
        logpath("{region}", "spatial_data_prep.done")
    output:
        touch(logpath("{region}", "exclusion_{technology}_{scenario}.done"))
    params:
        region=lambda wc: wc.region,
        technology=lambda wc: wc.technology,
        scenario=lambda wc: wc.scenario
    script:
        "Exclusion.py"

rule suitability:
    input:
        expand(logpath("{region}", "exclusion_{technology}_{scenario}.done"))
    output:
        touch(logpath("{region}", "suitability.done"))
    params:
        region=lambda wc: wc.region,
        scenario=lambda wc: wc.scenario
    script:
        "suitability.py"

rule energy_profiles:
    input:
        logpath("{region}", "suitability.done")
    output:
        touch(logpath("{region}", "energy_profiles_{technology}_{weather_year}_{scenario}.done"))
    params:
        region=lambda wc: wc.region,
        technology=lambda wc: wc.technology,
        scenario=lambda wc: wc.scenario,
        weather_year=lambda wc: wc.weather_year
    script:
        "energy_profiles.py"


