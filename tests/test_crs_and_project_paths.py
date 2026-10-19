from pathlib import Path

import pytest
from pyproj import CRS

from lava.project import PROJECT_ROOT, resolve_project_path
from lava.utils.crs import crs_tag, load_crs, save_crs


@pytest.mark.parametrize(
    "crs",
    [
        CRS.from_epsg(4326),
        CRS.from_user_input("ESRI:102003"),
        CRS.from_proj4(
            "+proj=eqc +lat_ts=35 +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs"
        ),
    ],
)
def test_crs_wkt_round_trip_preserves_identity_and_tag(
    crs: CRS, tmp_path: Path
) -> None:
    path = tmp_path / "crs.wkt"

    save_crs(crs, path)
    loaded_crs = load_crs(path)

    assert loaded_crs.equals(crs)
    assert crs_tag(loaded_crs, path) == crs_tag(crs)
    assert crs_tag(CRS.from_epsg(3857), path) == crs_tag(CRS.from_epsg(3857))


def test_resolve_project_path_anchors_relative_paths_at_repository_root(
    tmp_path: Path,
) -> None:
    assert resolve_project_path("configs/config.yaml") == (
        PROJECT_ROOT / "configs" / "config.yaml"
    )
    assert resolve_project_path(tmp_path) == tmp_path
