import yaml
from utils.data_preprocessing import clean_region_name

with open('configs/config.yaml') as f:
    cfg = yaml.safe_load(f)

region_folder = cfg['region_folder_name']
region_clean = clean_region_name(cfg['region_name'])

spatial_done = f"data/{region_folder}/spatial_data_prep.done"
wind_done = f"data/{region_folder}/wind_exclusion.done"
solar_done = f"data/{region_folder}/solar_exclusion.done"
suitability_done = f"data/{region_folder}/suitability.done"

rule all:
    input: suitability_done

rule spatial_data_prep:
    output: spatial_done
    shell: 'python spatial_data_prep.py && touch {output}'

rule exclusion_wind:
    input: spatial_done
    output: wind_done
    params: tech='wind'
    shell: 'python Exclusion.py configs/wind.yaml {params.tech} && touch {output}'

rule exclusion_solar:
    input: spatial_done
    output: solar_done
    params: tech='solar'
    shell: 'python Exclusion.py configs/solar.yaml {params.tech} && touch {output}'

rule suitability:
    input: wind_done, solar_done
    output: suitability_done
    shell: 'python suitability.py && touch {output}'
