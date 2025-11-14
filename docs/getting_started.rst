Getting Started
===============

This section will guide you through setting up the LAVA project on your local system. It covers the prerequisites, environment setup, and an overview of the repository structure to help you get started quickly.

Prerequisites
-------------

Before installing and running **LAVA**, ensure you have the following:

- `Conda <https://docs.conda.io/projects/conda/en/stable/user-guide/install/index.html>`_ (Anaconda or Miniconda) installed on your system for managing the environment and python.
When installing Conda make sure to add it to your system PATH (search for the following folders in your machine)

.. code-block:: console

    set PATH=C:\users\miniconda
    set PATH=C:\users\miniconda\Scripts

- `Git <https://git-scm.com/install/>`_ (optional) if you plan to clone the repository using Git.
- `VSCode <https://code.visualstudio.com/download>`_ or another code editor for editing configuration files and scripts.
- A system with sufficient disk space (min. 15 GB) and RAM (16 GB or higher), especially if processing large datasets.

Installation of LAVA tool
--------------------------------

1. **Clone the repository**: Open a terminal, navigate to a location of your choice using :code:`cd {folder_name_in_directory}` and run:

   .. code-block:: bash

      git clone https://github.com/jome1/LAVA.git
      cd LAVA

   This will create a local copy of the project in a folder named ``LAVA`` and opens that folder in the terminal.

2. **Create the Conda environment** using the provided environment file that lists all necessary dependencies. Run the following command from the repository root:

   .. code-block:: bash

      conda env create -f envs/win-64.lock.yaml

   This will create a new Conda environment (named ``lava``) with all required packages.

3. **Activate the environment**:

   .. code-block:: bash

      conda activate lava


LAVA Folder Structure
------------------------

Understanding the repository layout will help in navigating the project and configuring it. Below is an overview of the **LAVA** folder structure (using relative paths from the repository root):

.. code-block:: text

    📁 LAVA/
    ├── 📁 configs
    │   ├── config_template.yaml
    │   ├── config_advanced_settings_template.yaml
    │   ├── onshorewind_template.yaml
    │   ├── solar_template.yaml
    │   └── config_snakemake.yaml
    ├── 📁 docs
    ├── 📁 envs
    ├── 📁 Raw_Spatial_Data/
    │   ├── 📁 additional_exclusion_polygons
    │   ├── 📁 custom_study_area
    │   ├── 📁 DEM
    │   ├── 📁 global_solar_wind_atlas
    │   ├── 📁 GOAS
    │   ├── 📁 landcover
    │   ├── 📁 OSM
    │   └── 📁 protected_areas
    ├── 📁 snakemake
    ├── 📁 tkinter_app
    ├── 📁 utils
    ├── 📁 weather_data
    └── 📁 data/
        └── 📁 "region_name"/
            ├── 📁 available_land/
            ├── 📁 derived_from_DEM/
            │   ├── slope
            │   └── aspect
            ├── 📁 OSM_infrastructure/
            ├── 📁 proximity/
            ├── DEM
            ├── region_polygon
            ├── solar
            ├── wind
            ├── protected_areas
            ├── landcover
            ├── EPSG
            ├── landuses
            └── pixel_size

Main folders important for user:
- **configs**: multiple configuration files 
- **Raw_spatial_data/**: Intended for raw input data required by the pipeline. For example, if the pipeline requires a boundary shapefile or other input datasets, they should be placed here, in the specified folders.
- **data/**: Outputs produced by the pipeline will be stored here. The pipeline will create subdirectories or files in this folder to organize results. This folder only appears after the first tool run.


LAVA data setup
------------------------
Most input data is downloaded automatically in the workflow except the following two datasets which must be retrieved manually and placed in the right folder.

- **DEM**: Download the DEM for your study region from `GEBCO <https://download.gebco.net/>`_. Use the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder **"DEM"** (digital elevation model) and name it ***gebco_cutout.tif***. This data provides the elevation in each pixel. It is also possible to use a different dataset.
- **Coastlines**: On `marineregions.org/downloads <https://marineregions.org/downloads.php/>`_ click on "Global Oceans and Seas" and download the geopackage. Unzip, name the file ***"goas.gpkg"*** and put it into the folder **"GOAS"** in the **"Raw_Spatial_Data"** folder.

