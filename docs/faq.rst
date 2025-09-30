FAQ
===

This section answers some frequently asked questions about the LAVA_china pipeline.

- **How do I re-run a failed rule?**  
  If a specific rule fails or you want to run a particular step again, you do not need to delete all outputs. Instead, you can instruct Snakemake to re-run the rule. The simplest way is to use the rule name. For example, if a rule named ``process_data`` failed and you have fixed the issue, run:  
  ``snakemake -R process_data``  
  This tells Snakemake to **force rerun** that rule and any downstream rules that depend on its output. Snakemake will skip rules whose outputs are still valid and up-to-date. If some outputs were only partially generated (marked as incomplete), you might need to use ``snakemake --rerun-incomplete`` to rerun those. Always ensure to address the root cause of the failure (check error messages and fix the config or code as needed) before re-running.

- **Where are outputs stored?**  
  By default, all outputs from the pipeline are stored under the ``results/`` directory in the project. Within this folder, outputs may be organized into subdirectories (for example, by region or by data product). You can navigate the ``results/`` folder to find generated files such as maps, tables, or logs. The exact structure and naming of output files are defined in the Snakefile and can be adjusted via the config if necessary. If you configured a custom output path in the config, then outputs will be in that specified location instead.

- **How do I add a new region to process?**  
  To add a new region (area of interest) for analysis, follow these steps:
  1. **Prepare the region data:** Obtain a vector file (e.g., a shapefile or GeoJSON) that delineates the new region's boundary. Place this file in the ``data/`` directory (or another location, but remember the path for the config).
  2. **Create a config file for the region:** In ``config/regions/``, create a new YAML file (you can copy an existing one as a template). Name it something indicative (for example, ``myregion.yaml`` for region "myregion"). Inside this file, specify the required parameters for the region – at minimum, the region name/identifier and the path to the boundary file. Also include any region-specific settings like the time range or analysis parameters, similar to the examples provided.
  3. **Update global config (if needed):** Open ``config/config.yaml`` and ensure that the new region is included in the list of regions or set as the target region to run. Depending on how the pipeline is designed, you might have a list like `regions: [region1, region2, myregion]` or a variable to specify the active region.
  4. **Run the pipeline:** Activate the environment and run Snakemake as usual. If the pipeline is configured to run multiple regions in one go, it will include the new region. Otherwise, run the pipeline specifically for that region (this could be done by setting a parameter or simply ensuring the config is pointed to that region).

  Once the pipeline runs, verify that outputs for the new region appear in the results.

- **Do I need to download satellite images manually?**  
  No, in general you do not need to manually download raw satellite imagery for LAVA_china. The pipeline leverages the OpenEO platform to fetch the required Earth observation data. As long as your configuration (and OpenEO credentials, if needed) is set up correctly, the Snakemake rules will handle data retrieval. You just need to ensure your config specifies the right data sources (e.g., Sentinel-2, etc.) and covers the region/time you want. The pipeline will download or stream only the data needed for your analysis. However, if you have specific local data you want to use instead of OpenEO (or to complement it), you can place it in the data directory and adjust the config to use those files.

- **Can I run the pipeline on a computing cluster?**  
  Yes, since Snakemake supports various execution modes, you can run LAVA_china on a cluster or cloud environment if needed. The simplest approach is to use Snakemake's built-in cluster support or executor. For example, you can use the ``--cluster`` option with a scheduler command or use profiles. You might need to adjust paths (especially if using a shared filesystem) and ensure the conda environment or containers are available on cluster nodes. Check Snakemake documentation for cluster execution. The pipeline itself doesn't change – it's mostly about how you invoke Snakemake. Always test on a small job before scaling out to the cluster.

