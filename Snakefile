from pathlib import Path
import json

def logpath(region, filename):
    return Path("data") / region / "snakemake_log" / filename

# Load regions from JSON file produced from "extract_china_provinces" script in utils folder
#regions_filepath = Path("Raw_Spatial_Data/custom_study_area/China_provinces_list.json")
#with open(regions_filepath, "r") as f:
#    regions= json.load(f)


#define parameters
regions = ["Anhui", "Beijing", "Chongqing", "Fujian", "Gansu", "Guangdong", "Guangxi", "Guizhou",
          "Hainan", "Hebei", "Heilongjiang", "Henan", "Hubei", "Hunan", "Jiangsu","Jiangxi",
          "Jilin", "Liaoning", "NeiMongol", "NingxiaHui", "Qinghai", "Shaanxi", "Shandong", "Shanghai",
          "Shanxi", "Sichuan", "Tianjin", "XinjiangUygur", "Xizang", "Yunnan", "Zhejiang"]
technologies = ["solar", "onshorewind"]
weather_years = [str(y) for y in range(2010, 2011)]
scenarios= "ref"

#short term fix for testing
regions=["Beijing"]
weather_years=1990

# Create directories for each region and snakemake log
for r in regions:
    Path(f"data/{r}/snakemake_log").mkdir(parents=True, exist_ok=True)


#script to run in terminal
#the resources are limited to openeo cause the api is throwing problems with parallelization. The snakemake workflow will parallelize everything else but the spatial_data_prep script. 
# snakemake --cores 4 --resources openeo_req=1


rule all:
    input:
        expand(logpath("{region}", "spatial_data_prep.done"), region=regions),
        expand(logpath("{region}", "exclusion_{technology}.done"), region=regions, technology=technologies),
        expand(logpath("{region}", "suitability.done"), region=regions),
        expand(logpath("{region}", "energy_profiles_{technology}_{weather_year}.done"), region=regions, technology=technologies, weather_year=weather_years)

rule spatial_data_prep:
    output:
        touch(logpath("{region}", "spatial_data_prep.done"))
    resources:
        openeo_req=1
    shell:
        "python spatial_data_prep.py --region {wildcards.region}"

rule exclusion:
    input:
        logpath("{region}", "spatial_data_prep.done")
    output:
        touch(logpath("{region}", "exclusion_{technology}.done"))
    shell:
        (
            "python Exclusion.py --region {wildcards.region} "
            "--technology {wildcards.technology}"
        )

rule suitability:
    input:
        expand(logpath("{region}", "exclusion_{technology}.done"), region=regions, technology=technologies)
    output:
        touch(logpath("{region}", "suitability.done"))

    shell:
        "python suitability.py --region {wildcards.region}"


rule energy_profiles:
    input:
         logpath("{region}", "suitability.done")
    output:
        touch(logpath("{region}", "energy_profiles_{technology}_{weather_year}.done"))
    shell:
        (
            "python energy_profiles.py --region {wildcards.region} "
            "--technology {wildcards.technology} "
            "--weather_year {wildcards.weather_year} "
        )
