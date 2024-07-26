# land-analysis-and-eligibility

This repo provides tools to calculate the eligible area in a user defined study region for building renewable energies like solar PV and wind onshore.
To do so, multiple steps need to be caried out including a detailed land analysis to have a better understanding of the study region.

# Work in progress!

## 1. Download the necessary raw spatial data
Create a folder named __"Raw_Spatial_Data"__. Inside that folder create two more folder named __"gebco"__ and __"OSM"__.

Following data must be downloaded:
* [GEBCO Gridded Bathymetry Data](https://download.gebco.net/) using the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder __"gebco"__.
* [CORINE land cover global dataset](https://zenodo.org/records/3939050) from zenodo, leave the name as it is and put it in the __"Raw_Spatial_Data"__ folder.
* [OpenStreetMap Shapefile](https://download.geofabrik.de/) of the country where your study region is located. Click on the relevant continent and then country to download the ´.shp.zip´. Unzip and put the country folder inside the __"OSM"__-folder.

