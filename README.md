# LAVA - *LA*nd a*V*ailability *A*nalysis 

LAVA is a tool to calculate the available area in a user defined study region for building renewable energy generators like utility-scale solar PV and wind onshore.
First, all needed data is preprocessed to bring it into the right format. This data can be analyzed to get a better understanding of the study region. Finally, the land eligibility analysis is done with the help of [`atlite`](https://github.com/PyPSA/atlite).


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

* __OSM__ :wrench: :robot:: [OpenStreetMap Shapefile](https://download.geofabrik.de/) contains tons of geodata. Download the file of the country or region where your study region is located. Click on the relevant continent and then country to download the ´.shp.zip´. Somtimes you can go even more granular by clicking on the country. The best is, to use the smallest available area where your study region is still inside to save storage space. Be aware of the files naming. Unzip and put the downloaded OSM data folder inside the __"OSM"__-folder.  
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

