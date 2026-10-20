import geopandas as gpd
import pygadm
from space2stats_client import Space2StatsClient


def _download_admin_boundary_wb(
    country_code: str,
    level: int | None = 0,
    admin_name: str | None = None,
    source: str = "WB",
) -> gpd.GeoDataFrame:
    """
    Download administrative boundaries using Space2Stats client (WorldBank).
    https://www.arcgis.com/apps/mapviewer/index.html?layers=d1b630859ed84e92a3782fed6a612b63

    Parameters:
    -----------
    country_code : str
        ISO 3166-1 alpha-3 country code (e.g., 'KEN', 'TUR', 'DEU')
    level : int, default=0
        Administrative level:
        - 0: Country boundary (entire country)
        - 1: Level 1 subdivisions (NAM_1) - e.g., states, provinces
        - 2: Level 2 subdivisions (NAM_2) - e.g., districts, counties
    admin_name : str, optional
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
    country_boundary = download_admin_boundary_wb('KEN')

    # Get all level 1 regions
    level1_regions = download_admin_boundary_wb('KEN', level=1)

    # Get specific level 1 region
    nairobi = download_admin_boundary_wb('KEN', level=1, admin_name='Nairobi')

    # Get specific level 2 region
    specific_district = download_admin_boundary_wb('KEN', level=2, admin_name='Mombasa')
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
        boundaries = client.fetch_admin_boundaries(
            country_code, adm_string, source=source
        )
    except TypeError as e:
        if "source" not in str(e):
            raise
        if source != "WB":
            print(
                f"Warning: installed space2stats_client version does not support source={source!r}; "
                "falling back to default source (WB)."
            )
        boundaries = client.fetch_admin_boundaries(country_code, adm_string)

    # Filter by region name if specified
    if admin_name is not None:
        if level == 0:
            print("Warning: admin_name is ignored when level=0 (country boundary)")
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

            available = boundaries[name_col].unique().tolist()
            boundaries = boundaries[boundaries[name_col] == admin_name]

            if boundaries.empty:
                print(f"Warning: No region found with {name_col}='{admin_name}'")
                print(f"Available regions: {available}")

    return boundaries


def _download_admin_boundary_gadm(
    country_code: str, level: int | None, admin_name: str | None = None
) -> gpd.GeoDataFrame:
    """
    Download GADM administrative boundaries using pygadm.

    Parameters:
    -----------
    country_code : str
        ISO 3166-1 alpha-3 country code (e.g., 'KEN', 'TUR', 'DEU')
    level : int or None
        Administrative level: 0 for the whole country, 1 or higher for
        subdivisions (matched against the NAME_<level> column).
    admin_name : str, optional
        Name of the region to select at the given level. If None, returns all
        subdivisions; ignored when level=0.

    Returns:
    --------
    gpd.GeoDataFrame
        GeoDataFrame containing the requested boundaries in EPSG:4326.
        Empty if no region matches admin_name.
    """
    if level == 0:
        region = pygadm.Items(admin=country_code)
    else:
        region = pygadm.Items(admin=country_code, content_level=level)
        name_column = f"NAME_{level}"
        if admin_name is not None:
            region = region.loc[region[name_column] == admin_name].copy()
    return region.set_crs("EPSG:4326", allow_override=True)


def get_study_area_polygon(
    source: str | None = None,
    country_code: str | None = None,
    level: int | None = None,
    admin_name: str | None = None,
    custom_polygon_path: str | None = None,
) -> gpd.GeoDataFrame:
    """
    Retrieve the custom or administrative study boundary in EPSG:4326.

    If custom_polygon_path is given, all other arguments are ignored and
    can be omitted.

    Parameters:
    -----------
    source : {'gadm', 'wb', 'gb'}, optional
        Administrative boundary source (GADM, World Bank, geoBoundaries).
        Required unless custom_polygon_path is given.
    country_code : str, optional
        ISO 3166-1 alpha-3 country code (e.g., 'KEN', 'TUR', 'DEU').
        Required unless custom_polygon_path is given.
    level : int or None, optional
        Administrative level (0 = country). Required for 'wb' and 'gb'.
    admin_name : str or None, optional
        Name of the administrative area to select at the given level.
        If None, returns all boundaries at the specified level.
    custom_polygon_path : str, optional
        Path to a custom polygon file; dissolved into a single geometry.

    Returns:
    --------
    gpd.GeoDataFrame
        Non-empty GeoDataFrame in EPSG:4326.

    Raises:
    -------
    ValueError
        If the source is unknown, a CRS is missing, or no boundary is found.
    """
    if custom_polygon_path:
        region = gpd.read_file(custom_polygon_path).dissolve()
        if region.crs is None:
            raise ValueError(
                f"Custom study-area polygon has no CRS: {custom_polygon_path}"
            )
        region = region.to_crs("EPSG:4326")
        if region.empty:
            raise ValueError(
                f"Custom study-area polygon is empty: {custom_polygon_path}"
            )
        return region

    if source is None or country_code is None:
        raise ValueError(
            "'source' and 'country_code' are required when no custom_polygon_path is given."
        )
    if source == "gadm":
        region = _download_admin_boundary_gadm(country_code, level, admin_name)
    elif source in {"wb", "gb"}:
        region = _download_admin_boundary_wb(
            country_code=country_code,
            level=level,
            admin_name=admin_name,
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
            f"with name '{admin_name}'"
        )
    return region
