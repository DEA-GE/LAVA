# LAVA - *LA*nd a*VA*ilability for Renewable Energies

LAVA is a tool to calculate the available area in a user defined study region for building renewable energy generators like utility-scale solar PV and wind onshore.
First, all needed data is preprocessed to bring it into the right format. This data can be analyzed to get a better understanding of the study region. Finally, the land eligibility analysis is done with [`atlite`](https://github.com/PyPSA/atlite) or [`GLAES`](https://github.com/FZJ-IEK3-VSA/glaes) (GLAES does not work fully yet).


# :construction: :warning: Work in progress! :construction_worker:


## 0. Files setup
__a) clone the repository (using Git Bash):__

`git clone https://github.com/jome1/LAVA.git`

After cloning, navigate to the top-level folder of the repo in your command window.

__b) install python dependencies__

The Python package requirements to use the LAVA tool are in the `requirements.yaml` file. You can install these requirements in a new environment using `conda`:

`conda env create -f envs/requirements.yaml`

Then activate this new environment using

`conda activate lava`

You are now ready to run the scripts in this repository.


## 1. Download the necessary raw spatial data
The folders for the data input are already created in this repo. Download the needed data to the correct place within the folder __"Raw_Spatial_Data"__. 

Following data must be downloaded (partly manually :wrench:, partly automatically :robot: by the script):
* __DEM__ :wrench:: [GEBCO Gridded Bathymetry Data](https://download.gebco.net/) is a continuous, global terrain model for ocean and land with a spatial resolution of 15 arc seconds (ca. 450m). Use the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder __"DEM"__ (digital elevation model) and name it __*gebco_cutout.tif*__. This data provides the elevation in each pixel. It is also possible to use a different dataset.

* __landcover__ :wrench: :robot:: The user can decide to automatically fetch ESAworldcover data (resolution of ~10m) via the openEO-API (see instructions later on this page) or to use a local file. This needs to be specified in the config.yaml file. 
[CORINE landcover global dataset](https://zenodo.org/records/3939050) is a recommended file with global landcover data. But it only has a resolution of ~100m. If you want to use it, you need to download the file from zenodo named __*PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif*__. Leave the name as it is and put it in the __"Raw_Spatial_Data"__ folder. :warning: Attention: the file size is 1.7 GB
You can also use landcover data from a different data source (then the coloring needs to be adjusted). 

* __OSM__ :wrench:: [OpenStreetMap Shapefile](https://download.geofabrik.de/) contains tons of geodata. Download the file of the country or region where your study region is located. Click on the relevant continent and then country to download the ´.shp.zip´. Somtimes you can go even more granular by clicking on the country. The best is, to use the smallest available area where your study region is still inside to save storage space. Be aware of the files naming. Unzip and put the downloaded OSM data folder inside the __"OSM"__-folder.  
The OSM data is used to extract railways, roads and airports. Be aware, that these files can quickly become big making the calculations slow. Handle roads with caution. Often there are many roads which leads to big files.

* __Coastlines__ :wrench:: [Global Oceans and Seas](https://marineregions.org/downloads.php) contains all oceans and seas. It is used to buffer the coastlines. This file is only needed, when the study region has a coastline. Click on "Global Oceans and Seas" and download the geopackage. Unzip, name the file __*"goas.gpkg"*__ and put it into the folder __"GOAS"__ in the __"Raw_Spatial_Data"__ folder.

*  __Protected Areas__ :wrench: :robot:: [World Database of Protected Areas](https://www.protectedplanet.net/en/search-areas?filters%5Bdb_type%5D%5B%5D=wdpa&geo_type=country) is a global database on protected areas. Search the country your study area is located in. Click on "Download" > "File Geodatabase" > "Continue" under Non Commercial Use, then right click on the download button and copy the link address behind the download button. Paste this link in the `config.yaml` behind "WDPA_url". This will automatically download, clip and reproject the protected areas within your study area. You can also use your own, locally stored file with protected areas by setting the right options in `config.yaml`.

* __Mean wind speeds__ :robot:: [Global Wind Atlas](https://globalwindatlas.info/en/download/gis-files) has data on mean wind speeds with high-spatial resolution. The data is automatically downloaded and processed by the script. If it is not working, try checking if the 3-letter country code used in the config.yaml and in the Global Wind Atlas match.

* __Solar radiation__ :robot:: [Global Solar Atlas](https://globalsolaratlas.info/download) has data on longterm yearly average of potential photovoltaic electricity production (PVOUT) in kWh/kWp with high-spatial resolution. The data is automatically downloaded and processed by the script.<br>
⚠️ For some areas there is no data, especially for many areas north of 60°N (e.g. Greenland, Iceland, parts of Sweden, Norway, Finnland, Russia).<br>
⚠️ For some countries you cannot download the default measure "LTAym_YearlyMonthlyTotals" which lets the script fail. Check the used measure directly in the download area of Global Solar Atlas and replace it in config.yaml under "advanced details" (e.g. "LTAy_YearlySum" instead of "LTAym_YearlyMonthlyTotals").

> [!NOTE]
> __Landcover data__ can be read from a local file or automatically fetched via the [openEO API](https://openeo.org/).  
> This powerful API can connect to multiple back-ends. Data processing can be done on the back-end if wanted. Here is some general information about openEO:  
> * [API documentation](https://open-eo.github.io/openeo-python-client/)
> * [openEO recorded Webinar](https://terrascope.be/en/news-events/joint-openeo-terrascope-webinar), [another webinar](https://www.youtube.com/watch?v=A35JHj8LM2k&list=PLNxdHvTE74Jy18qTecMcNruUjODMCiEf_&index=3)  
> 
> In the LAVA-tool, the openEO-connection to ESAworldcover data is implemented. In order to use it, one needs to be registered with the Copernicus Data Space Ecosystem. Follow [these instructions](https://documentation.dataspace.copernicus.eu/Registration.html) to register. When running the LAVA-tool for the first time, you will be asked to authenticate using your Copernicus account. Click on the link printed by the script and login to authenticate. When runnning the tool again, a locally stored refresh token is used for authentication, so you don't have to login again.
>
> More information about openEO-connection with Copernicus:
> * Every user gets [10000 credits per months](https://dataspace.copernicus.eu/analyse/openeo) to carry out processes on this backend. In your [copernicus dataspace account](https://marketplace-portal.dataspace.copernicus.eu/billing) you can see your credits balance and how many credits your copernicus jobs costed.  
> * [Copernicus Dataspace Forum](https://forum.dataspace.copernicus.eu/)  
> * [General limitations openEO](https://documentation.dataspace.copernicus.eu/APIs/openEO/openEO.html): tested up to 100x100km at 10m resolution, free tier synchronous requests and batch jobs limited to 2 concurrent requests/jobs.  
> * [openeo Web Editor](https://editor.openeo.org/?server=openeo.dataspace.copernicus.eu) where you can see all your batch jobs.



> [!NOTE]
__DEM__ (digital elevation model) is just a generic term. To be more precise, one can distinguish between Digital Surface Models (DSM) and Digital Terrain Models (DTM). DSMs also include vegetation like forests and buildings. Since ground-mounted PV and wind turbines are built on the ground and not on trees, a DTM is much better suited. When deriving the slope map from a high resolution DSM, then it can happen that you get pixels with high slopes at the edge of forests and fields or at the edge of buildings. This is unnecessary and for the tools purpose false data. Unfortunately, many easily accessible DEMs are just DSMs but not DTMs. The above mentioned GEBCO dataset is in fact a DTM but with a rather low resolution. There may be local DTMs with a higher resolution, which can also be used in the tool.\
The [Copernicus Global 30 meter Digital Elevation Model dataset](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) is accessible through the `openEO-API` but only a DSM. There is the [MERIT DEM](https://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_DEM/) which is close to be a global DTM. It is based on SRTM with forest removed but no buildings removed. The best global DTM is the [FABDEM](https://www.fathom.global/product/global-terrain-data-fabdem/). It is based on the Copernicus Global 30m DEM with buildings and forests removed. Unfortunately it is commercial. Under certain circumstances, a [free API access](https://www.fathom.global/insight/fabdem-download/) is possible. The FABDEM originated at the University of Bristol. So, the tiles are freely accessible [here](https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn). However, since the FABDEM API is not always freely accessible, the FABDEM is not implemented in the LAVA tool. 

> [!NOTE]  
Be aware with __landcover data__: This type of data is good to estimate the potential but is still away from a precise local measurement. The landcover data is derived from satellite images and prone to erros. Note, that there is often only the category "built-up area" which includes all areas where something is built on the land. So, there is no differentiation between urban areas and stand-alone industrial or agricultural complexes, which may not need so much buffer distance to renewable energy installations. Sometimes even parts of roads or solar PV parks are classified as "built-up area" in the landcover data. For a detailed analysis to derive something like priority zones for renewables, detailed local geospatial data is needed, which has a high resolution and differentiates between areas in a more detailed way.\
> It is possible to use gridded population data as a proxy dataset, but that might miss some areas with houses. Careful consideration must be given to which data is used.

> [!NOTE]
Take additional care when using a study region with a __coastline__. Coastlines can be very difficult and complex. Always cross check the results.


## 2. Configuration
In the __"configs"__-folder copy the file `config_template.yaml` and rename it to `config.yaml`.
In the `config.yaml` file you can configure the data preprocessing and the land exclusion. You can also copy and rename the `config.yaml` if you want to test multiple settings. Be aware that the name of the `config.yaml` file needs to be the same in the scripts.

In the `config.yaml` file you can choose which data you want to consider in the preprocessing.
You also have to select your study region. When using the automatic download from gadm.org, you have to specify the name of the region (region_name) and the GADM level as it is used by gadm.org. Ideally you download the geopackage of the country you are interested in from [gadm.org](gadm.org) and load it into QGIS to find the right `gadm_level` and `region_name`. For some countries there are troubles downloading administrative boundaries from gadm.org. Then you must use your own custom study area file.
Finally, you have to specify the land exclusions and buffer zones.


## 3. Spatial data preparation
The script `spatial_data_prep.py` performs multiple data preprocessing steps to facilitate the land analysis and land eligibility study:
* download administrative boundary of the study region from [gadm.org](gadm.org) using the package pygadm or use a custom polygon instead if wished (custom polygon needs to be put to the right folder wihtin __"Raw_Spatial_Data"__ folder) (alternative sources for administrative boundaries [here](https://x.com/yohaniddawela/status/1828026372968603788); nice tool with online visualization and download [here](https://mapscaping.com/country-boundary-viewer/))
* calculate the local UTM zone (you can also set the projected CRS manually)
* clip and reproject to local UTM zone OSM railways, roads, airports and waterways (roads are also filtered to only consider main roads; hard-coded in the script)
* clip and reproject landcover data and elevation data. 
* create a slope map from the elevation data (calculated internally using `richdem`)
* Elevation, slope and aspect are the also co-registered to the landcover data using nearest resampling. More on working with multiple raster files (resampling and registering): [here](https://pygis.io/docs/e_raster_resample.html)

If you want to estimate the available land for solar PV, then the orientation of the pixels is also important:
* create an aspects map from the elevation data (calculated internally using `richdem`)
* create map showing pixels with slope bigger X and aspect between Y and Z (north facing pixels with slope where you would not build PV) (default: X=10°, Y=310°, Z=50°)

* download and clip protected areas from WDPA or use your own local file
* download, clip and co-register mean wind speed data to landcover (used to exclude areas with low wind speeds)
* download, clip and co-register potential solar PV generation data to landcover (used to exclude areas with low solar PV production potential)


For the preprocessing, some functions are used which are defined in the file `data_preprocessing.py` in the folder "utils".

The files are saved to a folder within the __"data"__-folder named according to the study region. The GIS-files will be saved in the coordinate reference system of the local UTM zone or in the user defined CRS. Some files are also stored in EPSG 4326 as well. 


## 4. Land analysis
:warning: use with caution, some functions were copied to spatial_data_prep.py (e.g. coloring of ESAworldcover from openeo, pixel size, ...)

With the JupyterNotebook `data_exploration.ipynb` you can inspect the spatial data of your study region.
In the second code cell just put the name of your study region as the folder with the preprocessed data is named. Additionally, put the right name of your landcover_source to fetch the correct legend and color dictionary.

You need to run this notebook also to get the land use codes and the pixel size stored in seperate .json files.


## 5. Land eligibility
With the JupyterNotebook `Atlite_custom_region.ipynb` you can finally derive the available area of your study region. You can use the predefined exclusions or customize it yourself. 
The code automatically recognizes if a file does not exist and thus does not take into account the respective file for the exclusion (e.g. there is no coastlines files when having a study region without a coast).


## 6. Bring all files in a QGIS project together
The script `create_qgis_project.py` puts all files together into a QGIS project to easily display them. This script needs to be used in the 'QGIS environment'. You can install it from the `requirements_qgis.yaml`. Additionally, you have to install the QGIS python package with the same version as your current QGIS installation in that environment. Sometimes you need to uninstall the python version in your environment and then install the QGIS python package inside in order to avoid trouble with package dependencies.

`conda install -c conda-forge qgis=VERSIONNUMBER`


## 7. More info / notes
* Terrascope API: not implemented because of limited functionalities (e.g. only downloads tiles, data cannot be clipped to area of interest). [API documentation](https://vitobelgium.github.io/terracatalogueclient/api.html), [ESAworldvcover Product](https://docs.terrascope.be/#/DataProducts/WorldCover/WorldCover),

* [adding basemaps to QGIS](https://gis.stackexchange.com/questions/20191/adding-basemaps-in-qgis)
* [Download DEMs in QGIS for a Specified Extent with the OpenTopography DEM Downloader Plugin](https://www.youtube.com/watch?v=EMwPT7tABCg)
* [Quick Review FABDEM with QGIS](https://www.youtube.com/watch?v=E3zKe81UOl8&t=3s)
* [Meadows et al.](https://doi.org/10.1080/17538947.2024.2308734) conclude: "In conclusion, we found FABDEM to be the most accurate DEM overall (especially for forests and low-slope terrain), suggesting that its error correction methodology is effective at reducing large positive errors in particular and that it generalises well to new application sites. Where FABDEM is not an option (given licensing costs for commercial applications), GLO-30 DGED is the clear runner-up under most conditions, with the exception of forests, where NASADEM (re-processed SRTM data) is more accurate."
For a more nuanced assessment read the articel (for some applications FABDEM might not be the most accurate one).
* [GEDTM30](https://github.com/openlandmap/GEDTM30): GEDTM30 is a global 1-arc-second (~30m) Digital Terrain Model (DTM) built using a machine-learning-based data fusion approach. It can be used as an alternative to the GEBCO DEM. GEDTM30 will hopefully integrated with openeo soon. 

