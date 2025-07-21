from pathlib import Path
import json

regions_filepath = Path("Raw_Spatial_Data/custom_study_area/China_provinces_list.json")
with open(regions_filepath, "r") as f:
    regions= json.load(f)
regions = ["Gansu"]
technologies = ["solar", "wind"]

def logpath(region, filename):
    return Path("data") / region / "snakemake_log" / filename

for region in regions:
    Path(f"data/{region}/snakemake_log").mkdir(parents=True, exist_ok=True)

rule all:
    input:
        expand(logpath(region, "exclusion_{technology}.done"), region=regions, technology=technologies),
        expand(logpath(region, "suitability.done"), region=regions)

rule spatial_data_prep:
    output:
        touch(logpath("{region}", "spatial_data_prep.done"))
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
        expand(logpath("{{region}}", "exclusion_{technology}.done"), technology=technologies)
    output:
        touch(logpath("{region}", "suitability.done"))
    shell:
        "python suitability.py --region {wildcards.region}"
