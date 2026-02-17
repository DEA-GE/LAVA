# LAVA - *L*and *AV*ailability *A*nalysis 

LAVA is a tool to calculate the available area in a user defined study region for building renewable energy generators like utility-scale ground-mounted solar PV and wind onshore.
First, all needed data is downloaded and preprocessed to bring it into the right format. Then the land eligibility analysis is done with the help of [`atlite`](https://github.com/PyPSA/atlite). Additionally, a suitable analysis can be performed and timeseries data for the available area derived.
The LAVA tool is flexible research software with a limited user-interface. For user-friendly online GIS tools to identify available land have a look at [Energy Access Explorer](https://www.energyaccessexplorer.org/tool/s/) and [REZoning](https://rezoning.energydata.info/). 

## Documentation
Find the tool documentation [here](https://lava-tool.readthedocs.io/en/latest/).


## Tool setup
__a) clone the repository (using Git Bash):__

`git clone https://github.com/DEA-GE/LAVA.git`

After cloning, navigate to the top-level folder of the repo in your command window.

__b) install python dependencies__

The Python package requirements to use the LAVA tool are in the `requirements.yaml` file. You can install these requirements in a new environment using `conda`:

`conda env create -f envs/requirements.yaml`

Then activate this new environment using

`conda activate lava`

You are now ready to run the scripts in this repository.

__c) input data setup__

In order to run the tool with the default data setup do the following:
* Download the Digital Elevation Model (DEM) for you study region from [GEBCO Gridded Bathymetry Data](https://download.gebco.net/). Use the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder __"DEM"__ (digital elevation model) and name it __*gebco_cutout.tif*__. This data provides the elevation in each pixel.
* Create a Copernicus account. In the LAVA-tool, the openEO-connection to ESAworldcover data is implemented. In order to use it, one needs to be registered with the Copernicus Data Space Ecosystem. Follow [these instructions](https://documentation.dataspace.copernicus.eu/Registration.html) to register. When running the LAVA-tool for the first time, you will be asked to authenticate using your Copernicus account. Click on the link printed by the script and login to authenticate. When runnning the tool again, a locally stored refresh token is used for authentication, so you don't have to login again.


## Quick start - Basic workflow
The basic workflow identifies suitable areas for solar PV and onshore wind based on user-defined parameters. 
1. Adjust configuration files (or use default values for test case).
2. Data download and pre-processing: run the script `spatial_data_prep.py`. You can run from the terminal via<br>
   `python spatial_data_prep.py`
4. Exclusion of non-suitable land: run the script `exclusion.py`. Run from the terminal to select technology and name the scenario via<br>
   `python exclusion.py --technology solar --scenario test`

With the advanced workflow it is also possible to perform a suitability analysis and derive timeseries data for the available area.



## Default input data
| Data name            | Data source |
|----------------------|-------------|
| DEM (Elevation)      | [GEBCO Gridded Bathymetry Data](https://download.gebco.net/) |
| Landcover            | [ESA WorldCover](https://esa-worldcover.org/en) via openEO API (Copernicus Data Space)|
| Population raster    | [worldpop](https://hub.worldpop.org/project/categories?id=3) |
| Spatial features <br>(road, railways, airports, waterbodies,<br>military, substations, power lines, generators)     | OpenStreetMap via overpass or [Geofabrik](https://download.geofabrik.de/) |
| Coastlines           | Global Oceans and Seas ([Marine Regions](https://marineregions.org/downloads.php)) |
| Protected Areas      | [World Database of Protected Areas (WDPA) – Protected Planet](https://www.protectedplanet.net/) |
| Mean Wind Speeds     | [Global Wind Atlas](https://globalwindatlas.info/en/download/gis-files) |
| Solar Radiation      | [Global Solar Atlas](https://globalsolaratlas.info/download) |





## More info / notes
* Terrascope API: not implemented because of limited functionalities (e.g. only downloads tiles, data cannot be clipped to area of interest). [API documentation](https://vitobelgium.github.io/terracatalogueclient/api.html), [ESAworldvcover Product](https://docs.terrascope.be/#/DataProducts/WorldCover/WorldCover),

* [adding basemaps to QGIS](https://gis.stackexchange.com/questions/20191/adding-basemaps-in-qgis)
* [Download DEMs in QGIS for a Specified Extent with the OpenTopography DEM Downloader Plugin](https://www.youtube.com/watch?v=EMwPT7tABCg)
* [Quick Review FABDEM with QGIS](https://www.youtube.com/watch?v=E3zKe81UOl8&t=3s)
* [Meadows et al.](https://doi.org/10.1080/17538947.2024.2308734) conclude: "In conclusion, we found FABDEM to be the most accurate DEM overall (especially for forests and low-slope terrain), suggesting that its error correction methodology is effective at reducing large positive errors in particular and that it generalises well to new application sites. Where FABDEM is not an option (given licensing costs for commercial applications), GLO-30 DGED is the clear runner-up under most conditions, with the exception of forests, where NASADEM (re-processed SRTM data) is more accurate."
For a more nuanced assessment read the articel (for some applications FABDEM might not be the most accurate one).



## Interesting additional datasets
* [GEDTM30](https://github.com/openlandmap/GEDTM30): GEDTM30 is a global 1-arc-second (~30m) Digital Terrain Model (DTM) built using a machine-learning-based data fusion approach. It can be used as an alternative to the GEBCO DEM. GEDTM30 will hopefully integrated with openeo soon.
* [Global Lakes and Wetlands Database](https://essd.copernicus.org/articles/17/2277/2025/#section6): comprehensive global map of 33 different types of wetlands around the world.
* [LCM-10](https://land.copernicus.eu/en/products/global-dynamic-land-cover/land-cover-2020-raster-10-m-global-annual#general_info): Land Cover 2020 (raster 10 m), global, annual - version 1. See this [LinkedIn post](https://www.linkedin.com/posts/activity-7427245076168323072-RDP4?utm_source=share&utm_medium=member_desktop&rcm=ACoAACUh41YBBCZkBQ_CcPYGaBOBZTkcbQ70IbA). Soon to be available on CDSE via openEO.

__useful to identify residential areas__:
* [World Settlement Footprint (WSF®) 2019](https://geoservice.dlr.de/web/datasets/wsf_2019): 10m resolution binary mask outlining the extent of human settlements globally derived by means of 2019 multitemporal Sentinel-1 (S1) and Sentinel-2 (S2) imagery.
* [GHS-BUILT-C - R2023A](https://human-settlement.emergency.copernicus.eu/ghs_buC2023.php): The spatial raster dataset delineates the boundaries of the human settlements at 10m resolution, and describe their inner characteristics in terms of the morphology of the built environment and the functional use. Derived from Sentinel2 composite and Landsat, multitemporal (1975-2030). (Might have higher accuracy than WSF accrording to [this paper](https://doi.org/10.1080/17538947.2024.2390454))
* [EMC-BUILT - R2025A](https://human-settlement.emergency.copernicus.eu/emc_built_s.php): Exposure Mapping Component built-up surface grid, derived from Sentinel-2 year 2022. EMC-BUILT-R2025A is more accurate than GHS-BUILT-C-R2023A: "*Compared to its predecessor, the GHSL R2023 built-up product (epoch 2018), the new product [EMC-BUILT-R2025A] shows less issues with overestimation while buildings are delineated more precisely. When comparing quality metrics (both total built-up surface and non-residential built-up surface) the new products show improved results.*" (see products [documentation](https://human-settlement.emergency.copernicus.eu/documents/EMC-BUILT_R2025.pdf?t=1764778621) page 6)

