Full workflow
=============

This guide walks through the end-to-end workflow for running the Land Availability Analysis (LAVA)
tool on a new study region. 

.. contents:: Table of contents
   :local:
   :depth: 2

Overview of the basic workflow
-------------------------------

0. Complete the tool and basic data setup.
1. Create the study-region configuration files in ``configs/``.
2. Run :mod:`spatial_data_prep.py` to download and prepare necessary data.
3. Inspect the pre-processed data (optional but recommended) with ``data_explore.ipynb``.
4. Run :mod:`Exclusion.py` for each technology to create available-land rasters.


Prerequisites
-------------

The Usage steps below assume that you have already cloned the repository, created the
``lava`` Conda environment from ``envs/requirements.yaml``, and downloaded the manual datasets. Those steps are documented in the
``Getting Started`` instructions.

Configuration files
-------------------

In the **configs-folder** copy the file ``config_template.yaml``, rename it to ``config.yaml`` and fill it out. This is your main configuration file for the data download.
Under the headline *#--exclusions--* in the configuration the variables ``scenario`` and ``technology`` are used to control the available land output.

For the exclusion criterias copy the files ``onshorewind_template.yaml`` and ``solar_template.yaml``. Rename them to ``onshorewind.yaml`` and ``solar.yaml`` respectively. Fill these files out in order to set the exclusion parameters.


Prepare spatial data
---------------------

Run the preprocessing script  ``spatial_data_prep.yaml`` after configuring the study region. It clips the raw inputs to the
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

Inspect data inputs
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
--------------------------------

Run :mod:`suitability.py` after both solar and wind exclusions are available. The script aligns
resource layers, applies terrain and region modifiers, and exports cost multipliers together with
thresholded resource-grade rasters in ``data/<RegionName>/suitability/``.

.. code-block:: bash

   python suitability.py --region <RegionName> --scenario ref

Energy profile simulation
---------------------------

Energy profiles combine the available land, suitability grades, and weather cut-outs. Ensure that
``configs/config.yaml`` points ``weather_data_path`` to the directory that contains the prepared
atlite cut-outs. Then run:

.. code-block:: bash

   python energy_profiles.py --region <RegionName> --technology onshorewind --scenario ref --weather_year 2019
   python energy_profiles.py --region <RegionName> --technology solar --scenario ref --weather_year 2019

Outputs are written to ``data/<RegionName>/energy_profiles/`` and include resource-grade time series
as well as diagnostic plots documenting the available area shares.

Batch processing with Snakemake
---------------------------------

For large-scale studies the ``snakemake/Snakefile`` orchestrates all stages across multiple regions,
technologies, and weather years. The workflow creates ``snakemake_log`` sentinels to prevent reruns
of completed steps. Launch it (after customising the region lists at the top of the Snakefile) with:

.. code-block:: bash

   snakemake --cores 4 --resources openeo_req=1

Use ``--snakefile snakemake/Snakefile_short`` or ``Snakefile_short_short`` for alternative presets.
The ``openeo_req`` resource serialises ESA WorldCover downloads to avoid rate limits while still
parallelising the remaining steps.

