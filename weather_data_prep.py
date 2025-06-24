import atlite
import numpy as np
import xarray as xr
import pandas as pd
import matplotlib.pyplot as plt
import geopandas as gpd
from rasterio.plot import show
import os



### --------- Input data and configuration ------------- ###

class M(object):
    pass

# Store all parameters in model object
def InstantiateModel():

    # Make model object from class
    m = M()

    m.years = [str(y) for y in range(1990,2020)]

    m.region_name = 'China_mainland_'

    # Balmorel time sets and geography
    m.region_file = 'K:/Github/LAVA_Kina/China_provinces.gpkg'

    # Shapefile to define the region downloadet from ERA5
    m.region = gpd.read_file(m.region_file)

    # Define UTC-time
    m.t_start_1 = '-01-01'
    m.t_end_1 = '-04-30'
    m.t_start_2 = '-05-01'
    m.t_end_2 = '-08-31'
    m.t_start_3 = '-09-01'
    m.t_end_3 = '-12-31'

    m.data_path = "D:/ProjectData/Weather data/ERA5 China/"


    return m

### ---------- Request weather data ----------- ###

def api_request(m, year):

    # We create an `atlite.Cutout` which covers the whole regions and builds the backbone for our analysis.
    # Later, it will enable to retrieve the needed weather data. 
    bounds = m.region.union_all().buffer(0).bounds

    cutout_file_1 = m.region_name + year + '_1'
    cutout_1 = atlite.Cutout(m.data_path + cutout_file_1, module="era5", bounds=bounds, time=slice(year + m.t_start_1, year + m.t_end_1))
    
    cutout_file_2 = m.region_name + year + '_2'
    cutout_2 = atlite.Cutout(m.data_path + cutout_file_2, module="era5", bounds=bounds, time=slice(year + m.t_start_2, year + m.t_end_2))

    cutout_file_3 = m.region_name + year + '_3'
    cutout_3 = atlite.Cutout(m.data_path + cutout_file_3, module="era5", bounds=bounds, time=slice(year + m.t_start_3, year + m.t_end_3))

    # Plot gridded map with request
    '''
    plt.rc("figure", figsize=[10, 7])
    fig, ax = plt.subplots()
    m.region.plot(ax=ax)
    cutout.grid.plot(ax=ax, edgecolor="grey", color="None")
    '''

    # After the cutout preparation, we can calculate the static and dynamic capacity factors of each region. 
    print("Preparing cutout 1")
    cutout_1.prepare()
    print("Preparing cutout 2")
    cutout_2.prepare()
    print("Preparing cutout 3")
    cutout_3.prepare()

    #return cutout

def ext_cutout(file_path):
    # Get cutout from external source
    cutout = atlite.Cutout(path=file_path)
    return cutout


def main():
    m = InstantiateModel()

    for y in m.years:
        print("Weather year " + y)
        api_request(m, y)

main()