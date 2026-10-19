import geopandas as gpd
import pygadm
from space2stats_client import Space2StatsClient


def download_admin_boundary_WB(
    iso3_code: str, level: int = 0, region_name: str = None, source: str = "WB"
) -> gpd.GeoDataFrame:
    """
    Download administrative boundaries using Space2Stats client (WorldBank).
    https://www.arcgis.com/apps/mapviewer/index.html?layers=d1b630859ed84e92a3782fed6a612b63

    Parameters:
    -----------
    iso3_code : str
        ISO 3166-1 alpha-3 country code (e.g., 'KEN', 'TUR', 'DEU')
    level : int, default=0
        Administrative level:
        - 0: Country boundary (entire country)
        - 1: Level 1 subdivisions (NAM_1) - e.g., states, provinces
        - 2: Level 2 subdivisions (NAM_2) - e.g., districts, counties
    region_name : str, optional
        Name of specific region to filter (NAM_1 or NAM_2 value).
        If None, returns all regions at the specified level.
    source : {'WB', 'GB'}, default='WB'
        Boundary source: 'WB' for World Bank or 'GB' for geoBoundaries.

    Returns:
    --------
    gpd.GeoDataFrame
        GeoDataFrame containing the requested administrative boundaries.

    Examples:
    ---------
    # Get entire country boundary
    country_boundary = download_admin_boundary('KEN')

    # Get all level 1 regions
    level1_regions = download_admin_boundary('KEN', level=1)

    # Get specific level 1 region
    nairobi = download_admin_boundary('KEN', level=1, region_name='Nairobi')

    # Get specific level 2 region
    specific_district = download_admin_boundary('KEN', level=2, region_name='Mombasa')
    """
    source = source.upper()
    if source not in {"WB", "GB"}:
        raise ValueError(f"source must be 'WB' or 'GB'. Got {source!r}")

    client = Space2StatsClient()

    # Map level to ADM string
    if level == 0:
        adm_string = "ADM0"
    elif level == 1:
        adm_string = "ADM1"
    elif level == 2:
        adm_string = "ADM2"
    else:
        raise ValueError(f"Level must be 0, 1, or 2. Got {level}")

    # Fetch boundaries from Space2Stats.
    # Older space2stats_client versions don't accept a `source` kwarg, so fall back if needed.
    try:
        boundaries = client.fetch_admin_boundaries(iso3_code, adm_string, source=source)
    except TypeError as e:
        if "source" not in str(e):
            raise
        if source != "WB":
            print(
                f"Warning: installed space2stats_client version does not support source={source!r}; "
                "falling back to default source (WB)."
            )
        boundaries = client.fetch_admin_boundaries(iso3_code, adm_string)

    # Filter by region name if specified
    if region_name is not None:
        if level == 0:
            print("Warning: region_name is ignored when level=0 (country boundary)")
        else:
            # Column name varies between API versions
            if "shapeName" in boundaries.columns:
                name_col = "shapeName"
            elif f"NAM_{level}" in boundaries.columns:
                name_col = f"NAM_{level}"
            else:
                raise ValueError(
                    f"No recognized name column found. Available columns: {boundaries.columns.tolist()}"
                )

            boundaries = boundaries[boundaries[name_col] == region_name]

            if boundaries.empty:
                print(f"Warning: No region found with {name_col}='{region_name}'")
                print(f"Available regions: {boundaries[name_col].unique().tolist()}")

    return boundaries


def get_study_area_polygon(
    source: str,
    country_code: str,
    level: int | None,
    region_name: str | None,
    custom_polygon_path: str | None = None,
) -> gpd.GeoDataFrame:
    """Retrieve the custom or administrative study boundary in EPSG:4326."""
    if custom_polygon_path:
        region = gpd.read_file(custom_polygon_path).dissolve()
        if region.crs is None:
            raise ValueError(
                f"Custom study-area polygon has no CRS: {custom_polygon_path}"
            )
        region = region.to_crs("EPSG:4326")
    elif source == "gadm":
        if level == 0:
            region = pygadm.Items(admin=country_code)
            region = region.set_crs("EPSG:4326", allow_override=True)
        else:
            region = pygadm.Items(admin=country_code, content_level=level)
            name_column = f"NAME_{level}"
            region = region.loc[region[name_column] == region_name].copy()
            region = region.set_crs("EPSG:4326", allow_override=True)
    elif source in {"wb", "gb"}:
        if level is None:
            raise ValueError(
                "An administrative level is required for World Bank boundaries."
            )
        region = download_admin_boundary_WB(
            iso3_code=country_code,
            level=level,
            region_name=region_name,
            source=source,
        )
        if not region.empty:
            if region.crs is None:
                raise ValueError("Downloaded administrative boundary has no CRS.")
            region = region.to_crs("EPSG:4326")
    else:
        raise ValueError(f"ADM_source must be 'gadm', 'wb' or 'gb', got: {source}")

    if region.empty:
        raise ValueError(
            f"No administrative boundary found for {country_code} at level {level} "
            f"with name '{region_name}'"
        )
    return region


def get_country_bounds_from_code(country_code: str) -> list[float]:
    """Return a country's EPSG:4326 bounds from its GADM boundary."""
    region = pygadm.Items(admin=country_code)
    region = region.set_crs("EPSG:4326", allow_override=True)
    return region.total_bounds.tolist()
