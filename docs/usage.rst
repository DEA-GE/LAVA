Usage
=====

This guide walks through the end-to-end workflow for running the Land Availability Analysis (LAVA)
tool on a new study region. The steps below mirror the order implemented in the repository
scripts and the Snakemake pipeline.

.. contents:: Table of contents
   :local:
   :depth: 2

Overview of the workflow
------------------------

1. Complete the repository and environment setup covered in the Getting Started guide.
2. Create the study-region configuration files in ``configs/``.
3. Populate the ``Raw_Spatial_Data`` folders with the required input datasets.
4. Run :mod:`spatial_data_prep.py` to clip, harmonise, and derive helper rasters and vectors.
5. Inspect the pre-processed data (optional but recommended) with ``data_explore.ipynb``.
6. Run :mod:`Exclusion.py` for each technology to create available-land rasters.
7. Use :mod:`suitability.py` to derive cost-modified resource grades.
8. Generate energy profiles with :mod:`energy_profiles.py` once weather cut-outs are available.
9. (Optional) Automate the workflow across many regions with the Snakemake rules in
   ``snakemake/``.

Prerequisites
-------------

The Usage steps below assume that you have already cloned the repository, created the
``lava`` Conda environment from ``envs/requirements.yaml``, and activated it. Those steps, along
with repository layout and configuration template locations, are documented in the
``Getting Started`` instructions.

Configuration files
-------------------

Copy the study-region templates referenced in the Getting Started guide if you have not done so
yet, then review the configuration entries before running the scripts. Key items in
``configs/config.yaml`` include:

* ``study_region_name`` and ``country_code`` which define the output directory and support
  catalogue downloads.
* ``landcover_source`` (``openeo`` for ESA WorldCover or ``file`` for local rasters) together
  with ``resolution_landcover`` or ``landcover_filename``.
* Flags for each OpenStreetMap feature class, coastline buffers, and atlas layers (wind, solar).
* ``protected_areas_source`` which can use the WDPA downloader or a local file.
* Optional helper layers such as ``compute_substation_proximity``, ``compute_road_proximity``,
  ``compute_terrain_ruggedness``, and ``forest_density``.
* ``scenario`` and ``technology`` settings that control filenames and the downstream exclusion
  runs.

Technology-specific exclusion and suitability thresholds reside in ``configs/onshorewind.yaml``
and ``configs/solar.yaml``. Adjust the resource-grade definitions, minimum area filters, and
modifier weights before running exclusions and suitability calculations.

Data inputs
-----------

Populate ``Raw_Spatial_Data/`` according to the data sources described in the README. The most
commonly used inputs are:

* **Digital elevation model (DEM)** – Download a terrain model such as the GEBCO gridded bathymetry
  raster, rename it to ``gebco_cutout.tif``, and place it in ``Raw_Spatial_Data/DEM/``. Higher
  resolution DTMs can be substituted when available.
* **Land-cover rasters** – Use ESA WorldCover via ``openeo`` or download datasets such as CORINE.
  Place locally sourced rasters in ``Raw_Spatial_Data/landcover/`` and set ``landcover_source`` to
  ``file``.
* **OpenStreetMap extracts** – Fetch shapefiles from Geofabrik for the study region, unzip them,
  and copy the folder into ``Raw_Spatial_Data/OSM/``. The scripts derive roads, railways, and
  airports from these layers.
* **Coastline buffers** – Download the Global Oceans and Seas geopackage, rename it ``goas.gpkg``,
  and store it in ``Raw_Spatial_Data/GOAS/`` for coastal studies.
* **Protected areas** – Either provide WDPA downloads in ``Raw_Spatial_Data/protected_areas/`` or
  configure the automated download via ``protected_areas_source: wdpa``.
* **Atlas layers** – Mean wind speed and solar resource rasters can be fetched automatically when
  the corresponding flags are enabled; cached copies are saved in
  ``Raw_Spatial_Data/global_solar_wind_atlas/``.
* **Additional exclusions** – Place any custom polygons or rasters in the
  ``Raw_Spatial_Data/additional_exclusion_polygons/`` and
  ``Raw_Spatial_Data/additional_exclusion_rasters/`` folders and reference them from the configs.
* **Weather cut-outs** – Store atlite-ready NetCDF files under ``weather_data/``. Use
  :mod:`weather_data_prep.py` as a template for preparing ERA5 cut-outs.

Spatial preprocessing
---------------------

Run the preprocessing script after configuring the study region. It clips the raw inputs to the
study area, aligns rasters, and computes helper layers such as slope, terrain ruggedness, and
proximity rasters.

.. code-block:: bash

   python spatial_data_prep.py --region <RegionName>

When ``landcover_source`` is ``openeo`` the script will prompt for Copernicus Data Space
credentials the first time it runs. Outputs are written to ``data/<RegionName>/`` and include:

* CRS definitions (``*_global_CRS.pkl``, ``*_local_CRS.pkl``) used downstream.
* Co-registered rasters for DEM, landcover, wind, solar, terrain ruggedness, and optional layers.
* ``derived_from_DEM/`` containing slope, aspect, terrain ruggedness, and north-facing masks.
* ``OSM_Infrastructure/`` geopackages for each enabled infrastructure category.
* ``landuses_<RegionName>.json`` and ``pixel_size_<RegionName>_<CRS>.json`` describing the
  land-cover codes and raster resolution required by the exclusion routines.

Inspecting the outputs
----------------------

Use ``data_explore.ipynb`` to verify the preprocessing results. The notebook loads data from the
``data/<RegionName>/`` folder, visualises selected layers, and summarises the available land-cover
codes to support tuning of exclusion thresholds.

Land eligibility exclusions
---------------------------

Create technology-specific available-land rasters by running :mod:`Exclusion.py`. The command-line
flags mirror the configuration entries so that single technologies or scenarios can be processed
independently.

.. code-block:: bash

   python Exclusion.py --region <RegionName> --technology onshorewind --scenario ref
   python Exclusion.py --region <RegionName> --technology solar --scenario ref

The script loads the prepared rasters and vector layers, applies the filters defined in the
technology configuration, and writes ``*_available_land_*.tif`` files under
``data/<RegionName>/available_land/``. A log of each scenario run is stored in the region folder
for traceability.

Suitability and resource grades
-------------------------------

Run :mod:`suitability.py` after both solar and wind exclusions are available. The script aligns
resource layers, applies terrain and region modifiers, and exports cost multipliers together with
thresholded resource-grade rasters in ``data/<RegionName>/suitability/``.

.. code-block:: bash

   python suitability.py --region <RegionName> --scenario ref

Energy profile simulation
-------------------------

Energy profiles combine the available land, suitability grades, and weather cut-outs. Ensure that
``configs/config.yaml`` points ``weather_data_path`` to the directory that contains the prepared
atlite cut-outs. Then run:

.. code-block:: bash

   python energy_profiles.py --region <RegionName> --technology onshorewind --scenario ref --weather_year 2019
   python energy_profiles.py --region <RegionName> --technology solar --scenario ref --weather_year 2019

Outputs are written to ``data/<RegionName>/energy_profiles/`` and include resource-grade time series
as well as diagnostic plots documenting the available area shares.

Batch processing with Snakemake
-------------------------------

For large-scale studies the ``snakemake/Snakefile`` orchestrates all stages across multiple regions,
technologies, and weather years. The workflow creates ``snakemake_log`` sentinels to prevent reruns
of completed steps. Launch it (after customising the region lists at the top of the Snakefile) with:

.. code-block:: bash

   snakemake --cores 4 --resources openeo_req=1

Use ``--snakefile snakemake/Snakefile_short`` or ``Snakefile_short_short`` for alternative presets.
The ``openeo_req`` resource serialises ESA WorldCover downloads to avoid rate limits while still
parallelising the remaining steps.

