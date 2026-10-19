import json
import logging
import os

import openeo
import numpy as np
import rasterio

import pandas as pd
import rasterstats

from lava.utils.study_area import StudyArea
from lava.utils.raster import clip_reproject_raster, reproject_raster


def prepare_landcover_openeo(study_area: StudyArea, aoi_path, resolution_landcover):
    """Download ESA WorldCover via openEO. aoi_path is a GeoJSON polygon in EPSG:4326."""
    print("\nprocessing landcover")
    logging.info("using openeo to get landcover")
    output_dir = study_area.output_dir
    region_name_clean = study_area.name
    local_crs_tag = study_area.local_crs_tag
    global_crs_tag = study_area.global_crs_tag
    openeo_landcover_filePath = os.path.join(
        output_dir, f"landcover_openeo_{region_name_clean}_{global_crs_tag}.tif"
    )

    if not os.path.exists(openeo_landcover_filePath):
        try:
            connection = openeo.connect(
                url="openeo.dataspace.copernicus.eu"
            ).authenticate_oidc()

            with open(aoi_path, "r", encoding="utf-8") as file:
                aoi = json.load(file)  # load polygon for clipping with openeo

            datacube_landcover = connection.load_collection(
                "ESA_WORLDCOVER_10M_2021_V2"
            )
            # clip landcover directly to area of interest
            landcover = datacube_landcover.mask_polygon(aoi)

            # change resolution if wanted (projection also possible, see documentation)
            if resolution_landcover:
                landcover = landcover.resample_spatial(
                    resolution=resolution_landcover
                )  # resolution=0 does not change resolution

            result = landcover.save_result("GTiFF")
            job_options = {
                "do_extent_check": False,
                "executor-memory": "5G",  # set executer-memory higher to process larger regions; see https://forum.dataspace.copernicus.eu/t/batch-process-error-when-using-certain-region/1454
            }  # see also https://discuss.eodc.eu/t/memory-overhead-problem/424
            # Creating a new batch job at the back-end by sending the datacube information.
            job = result.create_job(
                job_options=job_options,
                title=f"landcover_openeo_{region_name_clean}_{global_crs_tag}",
            )
            # Starts the job and waits until it finished to download the result.
            job.start_and_wait()
            job.get_results().download_file(openeo_landcover_filePath)

            # color openeo landcover file
            try:
                from lava.utils import legends

                openeo_landcover_colored_filePath = os.path.join(
                    output_dir,
                    f"landcover_openeo_colored_{region_name_clean}_{global_crs_tag}.tif",
                )
                colors_dict_int = getattr(
                    legends, "colors_dict_esa_worldcover2021_int"
                )  # color codes as RGB integers
                with rasterio.open(openeo_landcover_filePath) as landcover:
                    band = landcover.read(
                        1, masked=True
                    )  # Read the first band, masked=True is masking no data values
                    meta = landcover.meta
                    colors_dict_int_sorted = dict(
                        sorted(colors_dict_int.items())
                    )  # can only write color values as int with rasterio
                    meta.update(
                        {"compress": "DEFLATE", "photometric": "palette"}
                    )  # You can also try 'DEFLATE', 'JPEG', or 'PACKBITS'
                    # save colored version
                    with rasterio.open(
                        openeo_landcover_colored_filePath, "w", **meta
                    ) as dst:
                        dst.write(band, indexes=1)
                        dst.write_colormap(
                            1, colors_dict_int_sorted
                        )  # be aware of dtype: landcover file is saved with int16, so RGB color values also needs to be an integer?
            except Exception as e:
                print(e)
                logging.warning("Something went wrong with coloring the landcover data")

            # reproject landcover to local CRS (grayscale, for DEM calculations)
            landcover_openeo_local_CRS = os.path.join(
                output_dir, f"landcover_openeo_{region_name_clean}_{local_crs_tag}.tif"
            )
            reproject_raster(
                openeo_landcover_filePath,
                region_name_clean,
                study_area.local_crs,
                "mode",
                "uint8",
                landcover_openeo_local_CRS,
            )

            # save pixel size and unique land cover codes
            landcover_information(
                landcover_openeo_local_CRS, output_dir, region_name_clean, local_crs_tag
            )

        except Exception as e:
            logging.error(f"openeo landcover failed: {e}")

    else:
        logging.info(
            "Landcover not downloaded from openeo. There is already a clipped landcover file in the output folder."
        )

    return openeo_landcover_filePath


def prepare_landcover_file(study_area: StudyArea, landcover_filename):
    """Clip and reproject a local landcover raster."""
    print("processing landcover")
    output_dir = study_area.output_dir
    region_name_clean = study_area.name
    local_crs_tag = study_area.local_crs_tag
    try:
        landcoverRasterPath = os.path.join(
            study_area.raw_spatial_data_folder, "landcover", landcover_filename
        )
        local_landcover_filePath = os.path.join(
            output_dir,
            f"landcover_file_{region_name_clean}_{study_area.global_crs_tag}.tif",
        )
        if not os.path.exists(
            local_landcover_filePath
        ):  # process data if file not exists in output folder
            print("processing landcover")
            logging.info("using local file to get landcover")
            clip_reproject_raster(
                landcoverRasterPath,
                region_name_clean,
                study_area.boundary_4326,
                "landcover_file",
                study_area.local_crs,
                "mode",
                "int16",
                output_dir,
            )
            landcover_local_CRS = os.path.join(
                output_dir, f"landcover_file_{region_name_clean}_{local_crs_tag}.tif"
            )
            landcover_information(
                landcover_local_CRS, output_dir, region_name_clean, local_crs_tag
            )
        else:
            print("Local landcover already processed to region.")
        return os.path.join(
            output_dir, f"landcover_file_{region_name_clean}_{local_crs_tag}.tif"
        )
    except Exception as e:
        logging.error(f"local landcover file failed: {e}")


def landcover_information(landcoverRasterPath, data_path, region_name, crs_tag):
    # Open the raster using a context manager
    with rasterio.open(landcoverRasterPath) as landcover:
        band = landcover.read(
            1, masked=True
        )  # Read the first band, masked=True is masking no data values

        res = landcover.transform[0]  # pixel size
        # save pixel size local CRS
        with open(
            os.path.join(data_path, f"pixel_size_{region_name}_{crs_tag}.json"), "w"
        ) as fp:
            json.dump(res, fp)

        # Available land cover codes
        land_codes = np.unique(band.data).tolist()
        # save landuses as json file
        with open(os.path.join(data_path, f"landuses_{region_name}.json"), "w") as fp:
            json.dump(land_codes, fp)


def landcover_stats_df(region_boundary, rasterFilePath, legend_dict, pixel_size):
    stats = rasterstats.zonal_stats(
        region_boundary, rasterFilePath, categorical=True, category_map=legend_dict
    )
    df = pd.DataFrame(stats)
    df_long = df.melt(var_name="category", value_name="count")
    df_long = df_long.groupby("category", as_index=False)["count"].sum()
    category_to_code = {category: code for code, category in legend_dict.items()}
    df_long["code"] = df_long["category"].map(category_to_code)
    df_long["area_km2"] = round(df_long["count"] * pixel_size / 1e6, 0)
    df_long = df_long[["category", "code", "count", "area_km2"]]
    return df_long
