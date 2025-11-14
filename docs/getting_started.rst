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

   LAVA/ 
   ├── Snakefile
   ├── 📁envs/requirements.yml       # Requirements for environment
   ├── config/
   │   ├── config.yaml             # Main configuration file for the pipeline
   |   ├── onshore.yaml            # Technology specific configurations
   |   ├── solar.yaml            # Technology specific configurations
   |   └── ...
   ├── Raw_spatial_data/          # Directory for input data (e.g., bathimetry data (DEM), ... )
   │   └── ...                    
   ├── data/                      # Directory where output results will be stored (e.g., land availability)
   │   └── ...                    
   ├── snakemake/                 # Snakemke worflows
   │   └── ...                    
   ├── utils/                    # Collection of supporting scripts storing functions used in the main scripts. 
   │   └── ...                    
   └── README.md                  # Project README with additional info

Key components of the structure:

- **Snakefile**: The main Snakemake workflow definition. It describes all the rules (steps) in the pipeline.
- **requirement.yaml**: Conda environment specification with all required dependencies.
- **config/**: Contains configuration files. The main ``config.yaml`` defines global settings. 
- **Raw_spatial_data/**: Intended for raw input data required by the pipeline. For example, if the pipeline requires a boundary shapefile or other input datasets, they should be placed here, in the specified folders.
- **data/**: Outputs produced by the pipeline will be stored here. The pipeline will create subdirectories or files in this folder to organize results.
- **snakemake/**: Snakemake workflows.
- **utils/**: Collection of supporting scripts storing functions used in the main scripts. 
- **README.md**: A markdown file with basic information about the project (often includes a brief description and possibly a summary of setup instructions).

With the environment set up and an understanding of the folder structure, you are now ready to use the pipeline. Proceed to the next section for instructions on running the workflow and configuring it for your data.
