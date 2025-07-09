from pathlib import Path

regions = ["NeiMongol"]
techs = ["solar", "wind"]

def logpath(region, filename):
    return Path("data") / region / "snakemake_log" / filename


for region in regions:
    Path(f"data/{region}/snakemake_log").mkdir(parents=True, exist_ok=True)

rule all:
    input:
        expand(logpath(region, "suitability.done"), region=regions)

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
        touch(logpath("{region}", "exclusion_{tech}.done"))
    params:
        region=lambda wc: wc.region,
        tech=lambda wc: wc.tech
    script:
        "Exclusion.py"

rule suitability:
    input:
        expand(logpath("{{region}}", "exclusion_{tech}.done"), tech=techs)
    output:
        touch(logpath("{region}", "suitability.done"))
    params:
        region=lambda wc: wc.region
    script:
        "suitability.py"
