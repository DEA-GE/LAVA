Getting Started
===============

This section will guide you through setting up the LAVA_china project on your local system. It covers the prerequisites, environment setup, and an overview of the repository structure to help you get started quickly.

Prerequisites
-------------

Before installing and running **LAVA_china**, ensure you have the following:

- **Conda** (Anaconda or Miniconda) installed on your system for managing the environment.
- **Git** (optional) if you plan to clone the repository using Git.
- A system (Linux or macOS recommended) with sufficient disk space and memory, especially if processing large datasets.

Setting up the Conda Environment
--------------------------------

1. **Clone the repository** (if you haven't done so): Open a terminal and run:

   .. code-block:: bash

      git clone https://github.com/m-dandrea/LAVA_china.git
      cd LAVA_china

   This will create a local copy of the project in a folder named ``LAVA_china``.

2. **Create the Conda environment** using the provided environment file. The repository includes an environment file (e.g., ``environment.yml``) that lists all necessary dependencies. Run the following command from the project root:

   .. code-block:: bash

      conda env create -f environment.yml

   This will create a new Conda environment (often named ``lava_china`` or similar) with all required packages, including Snakemake and geospatial libraries (GDAL/OGR, OpenEO client, etc.).

3. **Activate the environment**:

   .. code-block:: bash

      conda activate lava_china

   Replace ``lava_china`` with the actual name of the environment if it differs. Activating the environment ensures that you can run the pipeline and its dependencies.

4. *(Optional)* **Update the environment** in the future: If the environment file changes (for example, new dependencies are added), you can update your environment with:

   .. code-block:: bash

      conda env update -f environment.yml

Project Folder Structure
------------------------

Understanding the repository layout will help in navigating the project and configuring it. Below is an overview of the **LAVA_china** folder structure (using relative paths from the repository root):

.. code-block:: text

   LAVA_china/ 
   ├── Snakefile
   ├── environment.yml
   ├── config/
   │   ├── config.yaml            # Main configuration file for the pipeline
   │   └── regions/               # Directory for region-specific config files (if applicable)
   │       ├── example_region.yaml    # Example region configuration (YAML format)
   │       └── ...                   # (Additional region config files)
   ├── data/
   │   └── ...                    # Directory for input data (e.g., shapefiles, ancillary data)
   ├── results/
   │   └── ...                    # Directory where output results will be stored
   ├── scripts/
   │   └── ...                    # Custom scripts or modules used by the pipeline
   └── README.md                  # Project README with additional info

Key components of the structure:

- **Snakefile**: The main Snakemake workflow definition. It describes all the rules (steps) in the pipeline.
- **environment.yml**: Conda environment specification with all required dependencies.
- **config/**: Contains configuration files. The main ``config.yaml`` defines global settings. The ``regions`` subfolder holds YAML files for specific regions or scenarios (you will modify or add files here to run the pipeline for different regions or datasets).
- **data/**: Intended for raw input data required by the pipeline. For example, if the pipeline requires a boundary shapefile or other input datasets, they should be placed here (or in a specified path defined in the config).
- **results/**: Outputs produced by the pipeline will be stored here. The pipeline will create subdirectories or files in this folder to organize results (e.g., per region or per data product).
- **scripts/**: Custom Python scripts or utilities that are executed as part of the Snakemake rules. These implement specific processing tasks (such as data download via OpenEO, data preprocessing, analysis, plotting, etc.).
- **README.md**: A markdown file with basic information about the project (often includes a brief description and possibly a summary of setup instructions).

With the environment set up and an understanding of the folder structure, you are now ready to use the pipeline. Proceed to the next section for instructions on running the workflow and configuring it for your data.
