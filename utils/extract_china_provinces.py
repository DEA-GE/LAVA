
import geopandas as gpd
import os



def save_level_1_areas_to_folder(json_path: str, gadm_level: int, output_folder: str):
    """
    Reads a GeoJSON file, extracts all areas at the specified GADM level,
    and saves each area as a separate GeoJSON file in the output folder.

    Parameters:
        json_path (str): Path to the GeoJSON file.
        gadm_level (int): The GADM level to extract (e.g., 1 for level 1).
        output_folder (str): Folder to save the individual GeoJSON files.
    """
    os.makedirs(output_folder, exist_ok=True)
    gadm_data = gpd.read_file(json_path)
    name_col = f'NAME_{gadm_level}'
    gdf = gadm_data.loc[gadm_data[name_col].notnull()].copy()
    for name, group in gdf.groupby(name_col):
        # Clean filename
        safe_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in str(name)])
        out_path = os.path.join(output_folder, f"gadm41_CHN_1_{safe_name}.geojson")
        group.to_file(out_path, driver="GeoJSON")

# Example usage:
json_path= "Raw_Spatial_Data/custom_study_area/gadm41_CHN_1.json"
save_level_1_areas_to_folder(json_path, 1, "Raw_Spatial_Data\custom_study_area")

