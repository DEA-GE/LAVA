# Data Sources

The folders for the data input are already created in the repo. Download the needed data to the correct place within the folder "Raw_Spatial_Data".

Following data must be downloaded (partly manually 🔧, partly automatically 🤖 by the script):

- **DEM** 🔧: [GEBCO Gridded Bathymetry Data](https://download.gebco.net/) is a continuous, global terrain model for ocean and land with a spatial resolution of 15 arc seconds (ca. 450m). Use the download tool. Select a larger area around your study region. Set a tick for a GeoTIFF file under "Grid" and download the file from the basket. Put the file into the folder "DEM" (digital elevation model) and name it `gebco_cutout.tif`. This data provides the elevation in each pixel. It is also possible to use a different dataset.

- **Landcover** 🔧 🤖: The user can decide to automatically fetch ESAworldcover data (resolution of ~10m) via the openEO-API (see instructions later on this page) or to use a local file. This needs to be specified in the `config.yaml` file. [CORINE landcover global dataset](https://zenodo.org/records/3939050) is a recommended file with global landcover data. But it only has a resolution of ~100m. If you want to use it, you need to download the file from zenodo named **PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif**. Leave the name as it is and put it in the **"Raw_Spatial_Data"** folder. ⚠️ Attention: the file size is 1.7 GB. You can also use landcover data from a different data source (then the coloring needs to be adjusted).

- **OSM** 🔧 🤖: The default setting uses overpass which automatically downloads the needed spatial features from OSM. Alternatively, you can download a file from [Geofabrik](https://download.geofabrik.de/). Download the file of the country or region where your study region is located. Click on the relevant continent and then country to download the `.shp.zip`. Sometimes you can go even more granular by clicking on the country. The best is to use the smallest available area where your study region is still inside to save storage space. Be aware of the file naming. Unzip and put the downloaded OSM data folder inside the **"OSM"**-folder. The OSM data is used to extract railways, roads and airports. Be aware that these files can quickly become big making the calculations slow. Handle roads with caution. Often there are many roads which leads to big files.

- **Coastlines** 🤖: [Global Oceans and Seas](https://marineregions.org/downloads.php) contains all oceans and seas. It is used to buffer the coastlines. This file is automatically downloaded.

- **Protected Areas** 🔧 🤖: [World Database of Protected Areas](https://www.protectedplanet.net/en/search-areas?geo_type=country&filters%5Bdb_type%5D%5B%5D=wdpa) is a global database on protected areas. The data for the country of your study area is automatically downloaded. You can also use your own, locally stored file with protected areas by setting the right options in `config.yaml`.

- **Mean wind speeds** 🤖: [Global Wind Atlas](https://globalwindatlas.info/en/download/gis-files) has data on mean wind speeds with high spatial resolution. The data is automatically downloaded and processed by the script. If it is not working, try checking if the 3-letter country code used in `config.yaml` and in the Global Wind Atlas match.

- **Solar radiation** 🤖: [Global Solar Atlas](https://globalsolaratlas.info/download) has data on longterm yearly average of potential photovoltaic electricity production (PVOUT) in kWh/kWp with high spatial resolution. The data is automatically downloaded and processed by the script.
  
  ⚠️ For some areas there is no data, especially for many areas north of 60°N (e.g. Greenland, Iceland, parts of Sweden, Norway, Finland, Russia).
  
  ⚠️ For some countries you cannot download the default measure "LTAym_YearlyMonthlyTotals" which lets the script fail. Check the used measure directly in the download area of Global Solar Atlas and replace it in `config.yaml` under "advanced details" (e.g. "LTAy_YearlySum" instead of "LTAym_YearlyMonthlyTotals").

---

> **Note — Landcover data and openEO:**
>
> Landcover data can be read from a local file or automatically fetched via the [openEO API](https://openeo.org/). This powerful API can connect to multiple back-ends. Data processing can be done on the back-end if wanted. Here is some general information about openEO:
>
> - [API documentation](https://open-eo.github.io/openeo-python-client/)
> - [openEO recorded Webinar](https://terrascope.be/en/news-events/joint-openeo-terrascope-webinar), [another webinar](https://www.youtube.com/watch?v=A35JHj8LM2k&list=PLNxdHvTE74Jy18qTecMcNruUjODMCiEf_&index=3)
>
> In the LAVA-tool, the openEO-connection to ESA WorldCover data is implemented. In order to use it, one needs to be registered with the Copernicus Data Space Ecosystem. Follow [these instructions](https://documentation.dataspace.copernicus.eu/Registration.html) to register.
>
> When running the LAVA-tool for the first time, you will be asked to authenticate using your Copernicus account. Click on the link printed by the script and login to authenticate. When running the tool again, a locally stored refresh token is used for authentication.
>
> More information about the openEO connection with Copernicus:
>
> - Every user gets [10000 credits per month](https://dataspace.copernicus.eu/analyse/openeo) to carry out processes on this backend. In your [Copernicus Data Space account](https://marketplace-portal.dataspace.copernicus.eu/billing) you can see your credits balance.
> - [Copernicus Dataspace Forum](https://forum.dataspace.copernicus.eu/)
> - [General limitations openEO](https://documentation.dataspace.copernicus.eu/APIs/openEO/openEO.html): tested up to 100x100km at 10m resolution; free tier synchronous requests and batch jobs limited to 2 concurrent requests.
> - [openEO Web Editor](https://editor.openeo.org/?server=openeo.dataspace.copernicus.eu) where you can see all your batch jobs.

> **Note — DEM:**
>
> DEM (digital elevation model) is a generic term. More precisely, one can distinguish between Digital Surface Models (DSM) and Digital Terrain Models (DTM). Since ground-mounted PV and wind turbines are built on the ground, a DTM is more suitable.
>
> The [Copernicus Global 30 meter DEM](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) is available through the openEO-API but is only a DSM.
>
> The [MERIT DEM](https://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_DEM/) is close to a global DTM (SRTM with forest removed but no buildings removed). The best global DTM is [FABDEM](https://www.fathom.global/product/global-terrain-data-fabdem/), based on the Copernicus Global 30m DEM with forests and buildings removed. Free API access may be possible under some circumstances ([details](https://www.fathom.global/insight/fabdem-download/)).
>
> The tiles are freely accessible here: [University of Bristol data](https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn).
>
> Because the FABDEM API is not always freely accessible, it is not implemented in the LAVA tool.

> **Note — Landcover data accuracy:**
>
> This type of data is good for estimating potential but far from precise local measurements. Landcover data is derived from satellite images and prone to errors. Often the only category is *"built-up area"*, which mixes urban areas with isolated industrial or agricultural sites. Even parts of roads or PV parks may be classified as "built-up area".
>
> For detailed renewable energy site analysis, high-resolution local geospatial data is needed. It is possible to use gridded population data as a proxy, but this may miss some housing areas.

> **Note:** Take additional care when using a study region with a **coastline**. Coastlines can be very complex. Always cross-check the results.

---

**Additional ideas for data to be included if available:**

- historical and touristic monuments
- archaeological sites
- earthquake zones
- landslide zones
- indigenous areas
- seismological stations
- radar and rotating beacon
- ...