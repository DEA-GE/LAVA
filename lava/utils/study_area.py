from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import CRS


@dataclass(frozen=True)
class StudyArea:
    name: str
    boundary_4326: gpd.GeoDataFrame
    local_crs: CRS
    raw_spatial_data_folder: Path
    output_dir: Path
    boundary_mollweide: gpd.GeoDataFrame
    boundary_buffered_4000_4326: gpd.GeoSeries
    bounding_box_4326: np.ndarray

    @property
    def global_crs(self) -> CRS:
        return CRS.from_epsg(4326)

    @property
    def local_crs_tag(self) -> str:
        auth = self.local_crs.to_authority()
        return "".join(auth) if auth else self.local_crs.to_string().replace(":", "_")

    @property
    def global_crs_tag(self) -> str:
        auth = self.global_crs.to_authority()
        return "".join(auth) if auth else self.global_crs.to_string().replace(":", "_")
