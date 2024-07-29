# land-analysis-and-eligibility

This repo provides tools to calculate the eligible area in a user defined study region for building renewable energies like solar PV and wind onshore.
To do so, multiple steps need to be caried out including a detailed land analysis to have a better understanding of the study region.

# :construction: :warning: Work in progress! :construction_worker:

## 1. Download the necessary raw spatial data
Create a folder named __"Raw_Spatial_Data"__. Inside that folder create two more folder named __"gebco"__ and __"OSM"__.

Following data must be downloaded:
* [GEBCO Gridded Bathymetry Data](https://download.gebco.net/) using the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder __"gebco"__. This data provides the elevation in each pixel.
* [CORINE land cover global dataset](https://zenodo.org/records/3939050) from zenodo, leave the name as it is and put it in the __"Raw_Spatial_Data"__ folder.
* [OpenStreetMap Shapefile](https://download.geofabrik.de/) of the country where your study region is located. Click on the relevant continent and then country to download the ´.shp.zip´. Unzip and put the country folder inside the __"OSM"__-folder.



## 2. Spatial data preparation
The script `spatial_data_prep_JOM.py` performs multiple data preprocessing steps to facilitate the land analysis and land eligibility study:
* download administrative boundary of the study region from gadm.org using the package pygadm
* calculate the local UTM zone
* clip and reproject to local UTM zone OSM railways, land cover data and elevation data
The files are saved to a folder within the __"data"__-folder.

In the beginning of the script you can select:
* `only_mainland = ` __0__ (use all polygons of the study region) or __1__ (use only the biggest polygon). This comes in handy when looking at countries with Island like Portugal and you only want to study the mainland of Portugal.
* `GOAS =` __0__ (don't change, work in progress)
* `consider_OSM =` __0__ (don't use OSM data in study region) or __1__ (clip OSM data to study region). Currently, only railways are considered.
* `EPSG_manual =` __*'EPSG-Code'*__ (insert EPSG code like 3035 for Europe if you want to set it manually instead of using the calculated UTM zone) or keep it an __*empty string*__

Moreover, you have to select your study region. It has to be an official administrative region from GADM.org:
* `country_code =` __*'country_code_as_string'*__ (3 letters ISO code)
* `gadm_level =` __*int*__ (administrative level)
* `region_name =` __*'region_name_as_string'*__ (name of the region)
Ideally you download the geopackage of the country you are interested in and load it in QGIS to find the right `gadm_level` and `region_name`.
