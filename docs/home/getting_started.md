# Getting Started

This section will guide you through setting up the LAVA project on your local system. It covers the prerequisites, environment setup, and an overview of the repository structure to help you get started quickly. For a general introduction to Python click [here](https://fneum.github.io/data-science-for-esm/dsesm/workshop-python/).

## Prerequisites

Before installing and running **LAVA**, ensure you have the following:

- [Pixi](https://pixi.prefix.dev/latest/) (recommended) or [Conda](https://docs.conda.io/projects/conda/en/stable/user-guide/install/index.html) (Anaconda or Miniconda) or  installed on your system for managing the environment and Python.

!!! note
    Having installed Conda check that you have access to conda in your terminal (or Anaconda Prompt on Windows) with the command `conda --version`. Furthermore, make sure to add conda to your system PATH (search for the following folders in your machine).

    ```console
    # add to system PATH ("users" might differ on your machine)
    set PATH=C:\users\miniconda
    set PATH=C:\users\miniconda\Scripts
    ```

- [Git](https://git-scm.com/install/) (optional) if you plan to clone the repository using Git.
- [VSCode](https://code.visualstudio.com/download) or another code editor for editing configuration files and scripts. In VSCode you should link the command prompt to the terminal by doing the following: a) Press *Ctrl + Shift + P* to show all commands. b) Type *Select Terminal: Select Default Profile* and click it. c) Click on "Command Prompt".
- A system with sufficient disk space (min. 15 GB) and RAM (16 GB or higher), especially if processing large datasets.

More information on the setup of git can be found [here](https://fneum.github.io/data-science-for-esm/dsesm/setup/#git-option-more-advanced).

!!! note "Command line navigation"
    The command line (also known as terminal, shell, or console) is a text-based interface that allows you to interact with your computer's operating system by typing commands. The following are some basic commands:

    - `cd my_directory` — change directory to `my_directory`
    - `cd ..` — move up one directory
    - `ls` (Linux/Mac) or `dir` (Windows) — list files and directories in the current directory
    - `mkdir my_new_directory` — create a new directory named `my_new_directory`

    Paths can be **absolute** (e.g., `C:\Users\YourName\Documents` on Windows or `/home/yourname/documents` on Linux/Mac) or **relative** to the current directory. On Windows, you use backslashes `\` to separate directories, while on Linux and macOS you use forward slashes `/`.

    For a more detailed introduction, see [this tutorial](https://tutorials.codebar.io/command-line/introduction/tutorial.html).

## Installation

You can find the LAVA GitHub repository [here](https://github.com/DEA-GE/LAVA).

**Clone the repository**: Open a terminal, navigate to a location of your choice and run:
```bash
git clone https://github.com/DEA-GE/LAVA.git
```
```bash
cd LAVA
```
This will create a local copy of the project in a folder named `LAVA` and opens that folder in the terminal.

**Recommended: Environment management using Pixi**. This reads the `pixi.toml` file and creates the required environment:
```bash
pixi install
```
This will install all dependencies defined for the project.

You can activate the environment with the following commnad:
```bash
pixi shell
```

**Alternative: Environment management using Conda** using the provided environment file that lists all necessary dependencies:
```bash
conda env create -f envs/requirements.yaml
```

This will create a new Conda environment (named `lava`) with all required packages.

You can activate the environment with the following commnad:
```bash
conda activate lava
```

## Data Setup

Most input data is downloaded automatically in the workflow except the DEM from GEBCO which must be retrieved manually and placed in the right folder. Furthermore a Copernicus account for the automatic download of landcover data is required.

- **DEM**: Download the DEM for your study region from [GEBCO](https://download.gebco.net/). Use the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder **DEM** (digital elevation model) in the **Raw_Spatial_Data** folder and name it **gebco_cutout.tif**. This data provides the elevation in each pixel. It is also possible to use a different dataset.
- **ESAworldcover**: In order to automatically download landcover data you need to create an account [here](https://documentation.dataspace.copernicus.eu/Registration.html). The very first time you run the LAVA tool you need to click on a link in the terminal and login to Copernicus. Afterwards, your login will be remembered.
- **ERA5 Copernicus**: If you want to download ERA5 data via Copernicus to be used for generating timeseries data, you need to install the Copernicus Climate Data Store `cdsapi` package (`pip install cdsapi`) and register and setup your CDS API key as described [on their website here](https://cds.climate.copernicus.eu/how-to-api).

The tool is now ready to be used. The first step is to fill out the `config.yaml` file.

## Folder Structure

Understanding the repository layout will help in navigating the project and configuring it. Below is an overview of the **LAVA** folder structure. The **data** folder only appears after the first run, when data for a study region has been downloaded.
```text
📁 LAVA/
├── 📁 configs
│   ├── config_template.yaml
│   ├── advanced_settings/
│   │   ├── advanced_data_prep_settings_template.py
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
```

Key folders for users:

- **configs** — multiple configuration files
- **Raw_Spatial_Data** — raw input data required by the pipeline (boundary shapefiles, DEM, etc.)
- **data** — outputs produced by the pipeline, organised by study region. Only appears after the first tool run.