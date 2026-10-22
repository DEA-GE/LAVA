# FAQ

This section answers some frequently asked questions about the LAVA tool.

## Where are outputs stored?

By default, all outputs from the pipeline are stored under the `data/` directory in the project. When the script spatial_data_prep.py is ran a folder with the name of the study area (variable study_region_name in the config.yaml file) is created. All outputs are then saved in this folder.

## How do I analyse a specific area to process?

To add a new region (area of interest) for analysis, follow these steps:

1. **Prepare the region data:** Obtain a GeoJSON that delineates the new region's boundary. Create a named collection folder below `Raw_Spatial_Data/custom_study_area/` and place the file there, for example `Raw_Spatial_Data/custom_study_area/municipalities/Odense.geojson`. Set `custom_study_area_filename` in `config.yaml` to the path relative to `custom_study_area`, such as `municipalities/Odense.geojson`. For workflows over several files, use a template such as `municipalities/{region_name}.geojson`.

## Do I need to download satellite images manually?

No, in general you do not need to manually download raw satellite imagery for LAVA_china. The pipeline leverages the OpenEO platform to fetch the required Earth observation data. As long as your configuration (and OpenEO credentials, if needed) is set up correctly, the Snakemake rules will handle data retrieval. You just need to ensure your config specifies the right data sources (e.g., Sentinel-2, etc.) and covers the region/time you want. The pipeline will download or stream only the data needed for your analysis. However, if you have specific local data you want to use instead of OpenEO (or to complement it), you can place it in the data directory and adjust the config to use those files.
