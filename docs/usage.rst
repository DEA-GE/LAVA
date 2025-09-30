Usage
=====

This section explains how to run the LAVA_china Snakemake workflow, how to configure it for your specific needs, and details about the expected input data and generated outputs.

Running the Pipeline
--------------------

After setting up the conda environment and activating it (see the *Getting Started* section), you can run the Snakemake pipeline. Ensure you are in the project root directory (the one containing the Snakefile).

Here are the basic steps to execute the workflow:

- **Dry Run (optional):** It's good practice to do a dry run first. This will show you which steps would be executed, without actually running them. Use:

  .. code-block:: bash

     snakemake -n

  Review the output to confirm that the workflow is set up as expected and all input files are found.

- **Run the full pipeline:** Once satisfied with the dry run, execute the workflow:

  .. code-block:: bash

     snakemake -j <N>

  Replace ``<N>`` with the number of CPU cores you want to use in parallel. Snakemake will schedule jobs across these cores. For example, use ``-j 4`` for 4 cores, or use ``-j 1`` to run jobs one at a time. If your system has many cores and sufficient memory, you can increase ``N`` to speed up the processing.

  The pipeline's **default target** (if you run `snakemake` without specifying a particular output) is usually configured to produce all main results. Snakemake will automatically determine which intermediate steps (rules) need to run based on the configuration and what outputs already exist.

- **Monitor progress:** Snakemake will print out each rule as it executes. If a rule fails, Snakemake will stop execution and report an error. You can find more details in any log files produced (often specified in the Snakefile for certain rules) or directly in the error message.

- **Resume or re-run:** If the workflow stops due to an error or if you want to re-run specific parts, you do not need to start from scratch. Snakemake will not redo steps whose outputs are already up-to-date. You can fix any issues (e.g., adjust configuration or code) and run `snakemake` again. It will pick up from where it left off, executing only the missing or outdated steps. For forcing a specific rule to re-run, see the FAQ section on re-running failed rules.

Configuration Files
-------------------

LAVA_china is designed to be flexible through configuration. The main configuration is done via YAML files in the `config/` directory. Before running the pipeline for the first time (and whenever you want to change the analysis parameters), you should review and edit these configs:

- **Global config (`config/config.yaml`):** This file contains global settings that apply to the entire pipeline. For example, it may define paths for input/output directories, default analysis parameters, the list of regions or datasets to process, or global flags (such as whether to use a caching mechanism, logging detail, etc.). Ensure that the paths and settings in this file are correct for your system. Many defaults are provided, but you might need to adjust, for instance, the path to your data directory if it’s not the default ``data/`` or output directory if you wish to change it.

- **Region-specific config (`config/regions/*.yaml`):** Typically, each target region or dataset has its own YAML file in the `config/regions/` folder. For example, `config/regions/example_region.yaml` might define parameters for a region called "example_region". These per-region config files likely include:
  
  - **Region name or identifier:** A human-readable name or code for the region.
  - **Spatial extent or boundary:** This could be specified via coordinates (lat/long bounds) or a path to a vector file (such as a Shapefile or GeoJSON) in the `data/` folder that delineates the region of interest.
  - **Time frame or date range:** (If applicable) Dates for which the analysis should be done (e.g., year, season, or specific range of satellite data to retrieve).
  - **Data source parameters:** For remote sensing data via OpenEO or other APIs, this might include collection names, product IDs, or cloud service endpoints. For example, specifying to use Sentinel-2 imagery or a particular data cube.
  - **Processing parameters:** Any algorithm-specific settings (e.g., cloud cover threshold, indices to compute, etc.).
  
  When you want to run the pipeline for a particular region, ensure that the corresponding YAML file is filled out with the correct values. You may use the provided example as a template. If you want to add a new region, you can create a new YAML file in this directory (see the FAQ on adding a new region).

Often, the global config file will have a key that indicates which region or regions to process (for instance, a list of region names). Make sure this reflects the regions you intend to run. In some setups, the pipeline might automatically run all region configs found in the folder; in others, you might specify the target region via a command-line option or by editing the config. Check the comments in `config/config.yaml` or documentation in the file for guidance on how to specify the active region.

**Note:** YAML files are sensitive to formatting. Be careful to follow the indentation pattern and syntax exactly. Strings containing special characters, like Windows paths or colons, should be quoted (e.g., ``C:\\data\\input`` or `"some: value"`). Incorrect YAML formatting is a common source of errors—if you encounter a "YAML decode" or "mapping values not allowed" error, double-check your edits for typos or formatting issues.

Input Data Requirements
------------------------

The pipeline expects certain input data files to be present or accessible, depending on your analysis. Below are the typical raw data requirements and formats:

- **Region boundaries:** If your analysis is region-based, you need to provide the boundary of each region of interest. This is usually a vector file (e.g., ESRI Shapefile, GeoJSON, GeoPackage, etc.) that outlines the area. The config for a region will reference this file. Make sure to place such files in the `data/` directory (or another location and update the path in the config accordingly). The coordinate reference system should be one commonly used (WGS84 latitude/longitude is a safe default unless the project specifies otherwise).

- **Ancillary data:** Depending on the project scope, there may be additional required datasets (for example, a mask for water bodies, administrative boundaries, or land cover classification legends). If so, these should be prepared in the format expected (which could be raster GeoTIFF, CSV tables, etc.) and placed in the appropriate folder (check the config keys or README for clues on where these should go). Ensure file paths in the config match where you've placed these files.

- **Remote sensing data via OpenEO:** One of the key features of LAVA_china is integration with OpenEO for accessing Earth observation data. The pipeline can retrieve satellite imagery or derived products on-the-fly using the OpenEO API, so you typically do **not** need to manually download raw satellite images. However, you might need to provide an account API token or credentials for the OpenEO platform if required. Consult the config file for any fields like `openeo_token` or `openeo_backend`. If the pipeline is configured to use a public OpenEO endpoint (e.g., Sentinel data on a public back-end), it might work without additional credentials. Otherwise, ensure you have the necessary access.

- **Data formats:** For all input files you provide, use standard formats:
  - Vector data: Shapefile (`.shp` with accompanying files), GeoJSON, or GeoPackage are typically supported via GDAL/OGR.
  - Raster data: GeoTIFF (`.tif`) is commonly used for gridded data. NetCDF or HDF5 might be used for certain climate or multi-band data (the pipeline documentation or config would specify if needed).
  - Tabular data: CSV or Excel files if any socioeconomic or reference data is needed. Make sure any such files are properly formatted (headers, delimiter) as expected by the pipeline's scripts.

Before running the pipeline, double-check that all required input files are available. If you run a dry run (`snakemake -n`), Snakemake will list any missing input files for the rules, which can help identify if you forgot to provide something.

Outputs and Results
-------------------

After the pipeline runs, results will be generated in the `results/` directory (unless configured otherwise). The exact outputs depend on what the pipeline is designed to do, but typical outputs could include:

- **Processed raster files:** e.g., GeoTIFF files of analysis results such as indices (NDVI, land cover maps, etc.) or other spatial layers produced for the region.
- **Vector outputs:** e.g., shapefiles or GeoJSON files with extracted features, boundaries, or zonal statistics.
- **Tabular data:** e.g., CSV files summarizing statistics (like area of change, time series of an indicator, etc.).
- **Plots or figures:** If the pipeline generates charts or maps for reporting, these might be saved as PNG/PDF images in a subfolder of `results/` (for example, `results/plots/`).
- **Logs:** The pipeline may produce log files for certain rules (often stored in a `logs/` directory or within `results/` per rule). These can be helpful for debugging or record-keeping.

The output files are usually organized by region and/or by processing date. For instance, you might find a subfolder under `results/` named after the region or analysis name, containing all outputs for that run.

All output locations and filenames are defined in the Snakefile and config. You can change the output directory or file naming by adjusting the configuration, but by default everything will be under `results/` to keep the project directory tidy.

Once the run is complete, you can explore the `results/` folder to inspect the outputs. It's a good idea to verify a few output files (open them in a GIS or viewer) to ensure the results look as expected. If something is off, you may need to adjust the config or troubleshoot (see the next section for common issues).

