ADVANCED_DATA_PREP_CONFIG = Path(
    "configs/advanced_settings/advanced_data_prep_settings.yaml"
)
if not ADVANCED_DATA_PREP_CONFIG.is_file():
    ADVANCED_DATA_PREP_CONFIG = Path(
        "configs/advanced_settings/advanced_data_prep_settings_template.yaml"
    )


checkpoint spatial_data_prep:
    input:
        config="configs/config.yaml",
        advanced_config=ADVANCED_DATA_PREP_CONFIG,
        script="spatial_data_prep.py"
    output:
        local_crs=Path("data") / "{region}" / "{region}_local_CRS.pkl"
    resources:
        openeo_req=1
    params:
        method="snakemake",
        configured_region=lambda wildcards: configured_region_name(wildcards.region)
    shell:
        "python -u spatial_data_prep.py --region {params.configured_region:q} --method {params.method:q}"
