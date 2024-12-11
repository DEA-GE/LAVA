# LAVA - *L*and *A*nalysis and a*VA*ilability

LAVA is a tool to calculate the available area in a user defined study region for building renewable energies like solar PV and wind onshore.
First, all needed data is preprocessed to bring it into the right format. This data can be analyzed to get a better understanding of the study region. Finally, the land eligibility analysis is done with [`atlite`](https://github.com/PyPSA/atlite) or [`GLAES`](https://github.com/FZJ-IEK3-VSA/glaes) (GLAES does not work fully yet).


# :construction: :warning: Work in progress! :construction_worker:


## 0. Files setup
__a) clone the repository:__

`% git clone https://github.com/jome1/LAVA.git`

After cloning, navigate to the top-level folder of the repo.

__b) install python dependencies__

The Python package requirements to use these tools are in the `requirements.yaml` file. You can install these requirements in a new environment using `conda`:

`conda env create -f envs/requirements.yaml`

Then activate this new environment using

`conda activate lava`

You are now ready to run the scripts in this repository.


## 1. Download the necessary raw spatial data
The folders for the data input are already created in this repo. Download the need data to the correct place within the folder __"Raw_Spatial_Data"__. 

Following data must be downloaded:
* __DEM__: [GEBCO Gridded Bathymetry Data](https://download.gebco.net/) is a continuous, global terrain model for ocean and land with a spatial resolution of 15 arc seconds (ca. 450m). Use the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder __"DEM"__ (digital elevation model) and name it __*gebco_cutout.tif*__. This data provides the elevation in each pixel. It is also possible to use a different dataset.

* __landcover__: The user can decide to automatically fetch ESAworldcover data (resolution of ~10m) via the openEO-API (see instructions later on this page) or to use a local file. This needs to be specified in the config.yaml file. 
[CORINE land cover global dataset](https://zenodo.org/records/3939050) is a recommended file with global landcover data. But it only has a resolution of ~100m. Download the file from zenodo named __*PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif*__. Leave the name as it is and put it in the __"Raw_Spatial_Data"__ folder. :warning: Attention: the file size is 1.7 GB
You can also use landcover data from a different data source (then the coloring needs to be adjusted). Instead of using the CORINE global land cover dataset you can also setup a connection vie `openEO` to use the ESAworldcover data with a resolution of ~10m.

* __OSM__: [OpenStreetMap Shapefile](https://download.geofabrik.de/) contains tons of geodata. Download the file of the country or region where your study region is located. Click on the relevant continent and then country to download the ´.shp.zip´. Somtimes you can go even more granular by clicking on the country. The best is, to use the smallest available area where your study region is still inside to save storage space. Be aware of the files naming. Unzip and put the downloaded OSM data folder inside the __"OSM"__-folder.  
The OSM data is used to extract railways, roads and airports. Be aware, that these files can quickly become big making the calculations slow. Handle roads with caution. Often there are many roads which leads to big files.

* __Coastlines__: [Global Oceans and Seas](https://marineregions.org/downloads.php) contains all oceans and seas. It is used to buffer the coastlines. This file is only needed, when the study region has a coastline. Click on "Global Oceans and Seas" and download the geopackage. Unzip, name the file __*"goas.gpkg"*__ and put it into the folder __"GOAS"__ in the __"Raw_Spatial_Data"__ folder.

*  __Protected Areas__: [World Database of Protected Areas](https://www.protectedplanet.net/en/search-areas?filters%5Bdb_type%5D%5B%5D=wdpa&geo_type=country) is a global database on protected areas. Search the country your study area is located in. Click on "Download" > "File Geodatabase" > "Continue" under Non Commercial Use, then right click on the download button and copy the link address behind the download button. Paste this link in the `config.yaml` behind "WDPA_link". This will automatically download, clip and reproject the protected areas within your study area.

> [!NOTE]
Landcover data can be read from a local file or automatically fetched via the [openEO API](https://openeo.org/): 
This powerful API can connect to multiple back-ends. Data processing can be done on the back-end if wanted.
> * [API documentation](https://open-eo.github.io/openeo-python-client/)
> * [openEO recorded Webinar](https://terrascope.be/en/news-events/joint-openeo-terrascope-webinar), [another webinar](https://www.youtube.com/watch?v=A35JHj8LM2k&list=PLNxdHvTE74Jy18qTecMcNruUjODMCiEf_&index=3) 

In order to use ESAworldcover data via openEO, one needs to connect to the copernicus dataspace as the backend. Every user gets [10000 credits per months](https://dataspace.copernicus.eu/analyse/openeo) to carry out processes on this backend. In your [copernicus dataspace account](https://marketplace-portal.dataspace.copernicus.eu/billing) you can see your credits balance and how many credits your copernicus jobs costed. There is also a [Copernicus Dataspace Forum](https://forum.dataspace.copernicus.eu/)\
[General limitations openEO](https://documentation.dataspace.copernicus.eu/APIs/openEO/openEO.html): tested up to 100x100km at 10m resolution, free tier synchronous requests and batch jobs limited to 2 concurrent requests/jobs.\
There is also an [openeo Web Editor](https://editor.openeo.org/?server=openeo.dataspace.copernicus.eu) where you can see all your batch jobs.


> [!NOTE]
__DEM__ (digital elevation model) is just a generic term. To be more precise, one can distinguish between Digital Surface Models (DSM) and Digital Terrain Models (DTM). DSMs also include vegetation like forests and buildings. Since ground-mounted PV and wind turbines are built on the ground and not on trees, a DTM is much better suited. When deriving the slope map from a high resolution DSM, then it can happen that you get pixels with high slopes at the edge of forests and fields or at the edge of buildings. This is unnecessary and for the tools purpose false data. Unfortunately, many easily accessible DEMs are just DSMs but not DTMs. The above mentioned GEBCO dataset is in fact a DTM but with a rather low resolution. There may be local DTMs with a higher resolution, which can also be used in the tool.\
The [Copernicus Global 30 meter Digital Elevation Model dataset](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) is accessible through the `openEO-API` but only a DSM. There is the [MERIT DEM](https://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_DEM/) which is close to be a global DTM. It is based on SRTM with forest removed but no buildings removed. The best global DTM is the [FABDEM](https://www.fathom.global/product/global-terrain-data-fabdem/). It is based on the Copernicus Global 30m DEM with buildings and forests removed. Unfortunately it is commercial. Under certain circumstances, a [free API access](https://www.fathom.global/insight/fabdem-download/) is possible. The FABDEM originated at the University of Bristol. So, the tiles are freely accessible [here](https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn). However, since the FABDEM API is not always freely accessible, the FABDEM is not implemented in the LAVA tool. 

> [!NOTE]  
Be aware with __land cover data__: This type of data is good to estimate the potential but is still away from a precise local measurement. The land cover data is derived from satellite images and prone to erros. Note, that there is often only the category "built-up area" which includes all areas with buildings. So, there is no differentiation between urban areas and stand-alone industrial or agricultural complexes, which may not need so much buffer distance to renewable energy installations. Sometimes even parts of roads are classified as "built-up area" in the land cover data. For a detailed analysis to derive something like priority zones for renewables, detailed local geospatial data is needed, which has a high resolution and differentiates between areas in a more detailed way.

> [!NOTE]
Take additional care when using a study region with a __coastline__. Coastlines can be very difficult and complex. Always cross check the results.


## 2. Configuration


## 3. Spatial data preparation
The script `spatial_data_prep_JOM.py` performs multiple data preprocessing steps to facilitate the land analysis and land eligibility study:
* download administrative boundary of the study region from [gadm.org](gadm.org) using the package pygadm
* use a custom polygon instead if wished
* calculate the local UTM zone
* clip and reproject to local UTM zone OSM railways, roads and airports (roads are also filtered to only consider main roads)
* clip and reproject land cover data and elevation data. Elevation data is also co-registered to the land cover data using bilinear resampling. More on working with multiple raster files (resampling and registering): [here](https://pygis.io/docs/e_raster_resample.html)
* create a slope map from the elevation data (calculated internally using `richdem`)

If you want to estimate the available land for solar PV, then the orientation of the pixels is also important:
* create an aspects map from the elevation data (calculated internally using `richdem`)
* create map showing pixels with slope bigger X and aspect between Y and Z (north facing pixels with slope where you would not build PV) (default: X=10°, Y=310°, Z=50°)

For the preprocessing, some functions are used which are defined in the file `data_preprocessing.py` in the folder "utils".

The files are saved to a folder within the __"data"__-folder named according to the study region. The GIS-files will be saved in the coordinate reference system of the local UTM zone or in the user defined CRS. Some files are also stored in EPSG 4326 as well. 

In the beginning of the script you can select:
* `consider_OSM_railways =` __0__ (don't use OSM data in study region) or __1__ (clip OSM data to study region)
* `consider_OSM_roads =` __0__  or __1__  Be careful with roads. The file size can quickly become big and the proessing takes more time.
* `consider_OSM_airports =` __0__ (don't use OSM data in study region) or __1__ (clip OSM data to study region)
* `EPSG_manual =` __*'EPSG-Code'*__ (insert EPSG code like 3035 for Europe if you want to set it manually instead of using the calculated UTM zone) or keep it an __*empty string*__

Moreover, you have to select your study region. When using the automatic download from gadm.org, you have to specify the name of the region (region_name) and the GADM level as it is used by gadm.org. You can just browse the [gadm-pages](https://gadm.org/maps.html) by clicking on the respective country and click through the "sub-divisions" until you found your study region.
* `region_name =` __*'region_name_as_string'*__ (name of the region, also the name of the output folder)
* `OSM_folder_name =` __*'name_as_string'*__
* `country_code =` __*'country_code_as_string'*__ (3 letters ISO code)
* `gadm_level =` __*int*__ (administrative level)

* `custom_polygon_filename =` __*'filename'*__ or keep it an __*empty string*__. The custom polygon must be in .geojson format lying in a folder named "custom_polygon" within the folder "Raw_Spatial_Data"

Ideally you download the geopackage from [gadm.org](gadm.org) of the country you are interested in and load it in QGIS to find the right `gadm_level` and `region_name`.



## 4. Land analysis
With the JupyterNotebook `data_exploration.ipynb` you can inspect the spatial data of your study region.
In the second code cell just put the name of your study region as the folder with the preprocessed data is named. Additionally, put the right name of your landcover_source to fetch the correct legend and color dictionary.

You need to run this notebook also to get the land use codes and the pixel size stored in seperate .json files.


## 5. Land eligibility
With the JupyterNotebook `Atlite_custom_region.ipynb` you can finally derive the available area of your study region. Set the name of your region with `region_name` and if necessary also set the EPSG code with `EPSG_custom` or leave it as an empty string. You can then run all cells. You can use the predefined exclusions or customize it yourself. 
The code automatically recognizes if a file does not exist and thus does not take into account the respective file for the exclusion (e.g. there is no coastlines files when having a study region without a coast).


### More info
* Terrascope API: not implemented because of limited functionalities (e.g. only downloads tiles, data cannot be clipped to area of interest). [API documentation](https://vitobelgium.github.io/terracatalogueclient/api.html), [ESAworldvcover Product](https://docs.terrascope.be/#/DataProducts/WorldCover/WorldCover), 

