# land-analysis-and-eligibility

This repo provides tools to calculate the eligible area in a user defined study region for building renewable energies like solar PV and wind onshore.
To do so, multiple steps need to be caried out including a detailed land analysis to have a better understanding of the study region.

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
Create a folder named __"Raw_Spatial_Data"__. Inside that folder create two more folder named __"gebco"__ and __"OSM"__.

Following data must be downloaded:
* [GEBCO Gridded Bathymetry Data](https://download.gebco.net/) using the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder __"gebco"__ and name it *gebco_cutout.tif*. This data provides the elevation in each pixel.
* [CORINE land cover global dataset](https://zenodo.org/records/3939050) from zenodo the file named *PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif*. Leave the name as it is and put it in the __"Raw_Spatial_Data"__ folder. :warning: Attention: the file size is 1.7 GB
* [OpenStreetMap Shapefile](https://download.geofabrik.de/) of the country where your study region is located. Click on the relevant continent and then country to download the ´.shp.zip´. Somtimes you can go even more granular by clicking on the country. The best is, to use the smallest available area where your study region is still inside to save storage space. Be aware of the files naming. Unzip and put the downloaded OSM data folder inside the __"OSM"__-folder.  
The OSM data is used to extract railways and roads. Be aware, that this files can quickly become big make the calculation slow. Handle roads with caution. Often there are many roads which can become big files.



## 2. Spatial data preparation
The script `spatial_data_prep_JOM.py` performs multiple data preprocessing steps to facilitate the land analysis and land eligibility study:
* download administrative boundary of the study region from gadm.org using the package pygadm
* calculate the local UTM zone
* clip and reproject to local UTM zone OSM railways and roads (roads are also filtered to only consider main roads)
* clip and reproject land cover data and elevation data. Elevation data is also co-registered to the land cover data using bilinear resampling. More on working with multiple raster files (resampling and registering): [here](https://pygis.io/docs/e_raster_resample.html)

The files are saved to a folder within the __"data"__-folder named according to the study region.

In the beginning of the script you can select:
* `only_mainland = ` __0__ (use all polygons of the study region) or __1__ (use only the biggest polygon). This comes in handy when looking at countries with Island like Portugal and you only want to study the mainland of Portugal.
* `GOAS =` __0__ (don't change, work in progress)
* `consider_OSM_railways =` __0__ (don't use OSM data in study region) or __1__ (clip OSM data to study region)
* `consider_OSM_roads =` __0__  or __1__  Be careful with roads. The file size can quickly become big and the proessing takes more time. 
* `EPSG_manual =` __*'EPSG-Code'*__ (insert EPSG code like 3035 for Europe if you want to set it manually instead of using the calculated UTM zone) or keep it an __*empty string*__

Moreover, you have to select your study region. It has to be an official administrative region from GADM.org:
* `country_code =` __*'country_code_as_string'*__ (3 letters ISO code)
* `OSM_folder_name =` __*'name_as_string'*__ (#usually same as country_code)
* `gadm_level =` __*int*__ (administrative level)
* `region_name =` __*'region_name_as_string'*__ (name of the region)
Ideally you download the geopackage of the country you are interested in and load it in QGIS to find the right `gadm_level` and `region_name`.



## 3. Land analysis
With the JupyterNotebook `data_exploration.ipynb` you can inspect the spatial data of your study region.
In the second code cell just put the name of your study region as the folder with the preprocessed data is named. Additionally, put the right name of your landcover_source to fetch the correct legend and color dictionary.




