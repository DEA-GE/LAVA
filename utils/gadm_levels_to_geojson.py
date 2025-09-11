
import geopandas as gpd
import os
import json


def extract_gadm_levels(
    input_path: str, 
    gadm_level: int =1, 
    output_folder: str ="Raw_Spatial_Data/custom_study_area"
    ):
    """
    Reads a GeoJSON file, extracts all areas at the specified GADM level,
    and saves each area as a separate GeoJSON file in the output folder.
    Also saves a list of area names to a JSON file in the output folder.

    Parameters:
        json_path (str): Path to the GeoJSON file.
        gadm_level (int): The GADM level to extract (e.g., 1 for level 1).
        output_folder (str): Folder to save the individual GeoJSON files.
    """
    os.makedirs(output_folder, exist_ok=True)
    gadm_data = gpd.read_file(input_path)
    name_col = f'NAME_{gadm_level}'
    gdf = gadm_data.loc[gadm_data[name_col].notnull()].copy()
    areas_list= []
    rename_dict = {
        "XinjiangUygur": "Xinjiang",
        "NingxiaHui": "Ningxia"
    }
    for name, group in gdf.groupby(name_col):
        # Rename if in dictionary, otherwise use original name
        name = rename_dict.get(name, name)
        # Clean filename
        safe_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in str(name)])

        out_path = os.path.join(output_folder, f"{safe_name}.geojson")
        group.to_file(out_path, driver="GeoJSON")
        areas_list.append(safe_name)
        list_out = os.path.join(output_folder, "processed_areas_list.json")
        with open(list_out, "w", encoding="utf-8") as f:
            json.dump(areas_list, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    # Run the function with the specified input path and GADM level:
    input_path= "Raw_Spatial_Data/custom_study_area/gadm41_CHN_1.json"
    extract_gadm_levels(input_path, gadm_level=1)


