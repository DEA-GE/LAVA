# LAAVA - *L*and *A*nalysis *A*nd a*VA*ilability

This repo provides tools to calculate the available area in a user defined study region for building renewable energies like solar PV and wind onshore.
First, all needed data is preprocessed to bring it into the right format. This data can be analyzed to get a better understanding of the study region. Finally, the land eligibility analysis is done with [`atlite`](https://github.com/PyPSA/atlite) or [`GLAES`](https://github.com/FZJ-IEK3-VSA/glaes) (GLAES does not work fully yet).

# :construction: :warning: Work in progress! :construction_worker:


## 0. Files setup
__a) clone the repository:__

`% git clone https://github.com/jome1/land-analysis-and-eligibility.git`

After cloning, navigate to the top-level folder of the repo.

__b) install python dependencies__

The Python package requirements to use these tools are in the `requirements.yml` file. You can install these requirements in a new environment using `conda`:

`conda env create -f envs/requirements.yaml`

Then activate this new environment using

`conda activate land_analysis`

You are now ready to run the scripts in this repository.


## 1. Download the necessary raw spatial data
The folders for the data input are already created in this repo. Download the need data to the correct place within the folder __"Raw_Spatial_Data"__. 

Following data must be downloaded:
* [GEBCO Gridded Bathymetry Data](https://download.gebco.net/) using the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder __"DEM"__ (digital elevation model) and name it __*gebco_cutout.tif*__. This data provides the elevation in each pixel.
* [CORINE land cover global dataset](https://zenodo.org/records/3939050) from zenodo the file named __*PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif*__. Leave the name as it is and put it in the __"Raw_Spatial_Data"__ folder. :warning: Attention: the file size is 1.7 GB
You can also use landcover data from a different data source (then the coloring needs to be adjusted).

Be aware with land cover data: This type of data is good to estimate the potential but is still away from a precise local measurement. The land cover data is derived from satellite images and prone to erros. Note, that there is often only the category "built-up area" which includes all areas with buildings. So, there is no differentiation between urban areas and stand-alone industrial or agricultural complexes, which may not need so much buffer distance to renewable energy installations. For a detailed analysis to derive something like priority zones for renewables, detailed local geospatial data is needed, which has a high resolution and differentiates between areas more detailed. 

* [OpenStreetMap Shapefile](https://download.geofabrik.de/) of the country where your study region is located. Click on the relevant continent and then country to download the ´.shp.zip´. Somtimes you can go even more granular by clicking on the country. The best is, to use the smallest available area where your study region is still inside to save storage space. Be aware of the files naming. Unzip and put the downloaded OSM data folder inside the __"OSM"__-folder.  
The OSM data is used to extract railways, roads and airports. Be aware, that these files can quickly become big making the calculations slow. Handle roads with caution. Often there are many roads which can become big files.

For a sophisticated potential analysis more data is needed like specific local exclusion zones or protected areas. This depends on the study region and data research as well as engagement with local authorities is needed. A good global dataset for protected areas is [protected planet](https://www.protectedplanet.net/en/thematic-areas/wdpa?tab=WDPA). Moreover, waterways and water areas could be used from OSM Data, because land cover data does not always recognize waterbodies.



## 2. Spatial data preparation
The script `spatial_data_prep_JOM.py` performs multiple data preprocessing steps to facilitate the land analysis and land eligibility study:
* download administrative boundary of the study region from gadm.org using the package pygadm
* use a custom polygon instead if wished
* calculate the local UTM zone
* clip and reproject to local UTM zone OSM railways, roads and airports (roads are also filtered to only consider main roads)
* clip and reproject land cover data and elevation data. Elevation data is also co-registered to the land cover data using bilinear resampling. More on working with multiple raster files (resampling and registering): [here](https://pygis.io/docs/e_raster_resample.html)
* create a slope map from the elevation data (calculated internally using `richdem`)
* create an aspects map from the elevation data (calculated internally using `richdem`)

For the preprocessing, some functions are used which are defined in the file __*data_preprocessing.py*__ in the folder "utils".

The files are saved to a folder within the __"data"__-folder named according to the study region. The GIS-files will be saved in the coordinate reference system of the local UTM zone or in the user defined CRS. Some files are also stored in EPSG 4326 as well. 

In the beginning of the script you can select:
* `consider_OSM_railways =` __0__ (don't use OSM data in study region) or __1__ (clip OSM data to study region)
* `consider_OSM_roads =` __0__  or __1__  Be careful with roads. The file size can quickly become big and the proessing takes more time.
* `consider_OSM_airports =` __0__ (don't use OSM data in study region) or __1__ (clip OSM data to study region)
* `EPSG_manual =` __*'EPSG-Code'*__ (insert EPSG code like 3035 for Europe if you want to set it manually instead of using the calculated UTM zone) or keep it an __*empty string*__

Moreover, you have to select your study region:
* `region_name =` __*'region_name_as_string'*__ (name of the region, also the name of the output folder)
* `OSM_folder_name =` __*'name_as_string'*__
* `country_code =` __*'country_code_as_string'*__ (3 letters ISO code)
* `gadm_level =` __*int*__ (administrative level)

* `custom_polygon_filename =` __*'filename'*__ or keep it an __*empty string*__. The custom polygon must be in .geojson format lying in a folder named "custom_polygon" within the folder "Raw_Spatial_Data"

Ideally you download the geopackage of the country you are interested in and load it in QGIS to find the right `gadm_level` and `region_name`.



## 3. Land analysis
With the JupyterNotebook `data_exploration.ipynb` you can inspect the spatial data of your study region.
In the second code cell just put the name of your study region as the folder with the preprocessed data is named. Additionally, put the right name of your landcover_source to fetch the correct legend and color dictionary.

You need to run this notebook also to get the land use codes and the pixel size stored in seperate .json files.


## 4. Land eligibility





