"""
CRS (Coordinate Reference System) service.

Responsibilities
----------------
- Detect whether a CRS is geographic (degrees-based) or projected (metres-based).
- Select an appropriate UTM projected CRS based on the dataset centroid.
- Transform a GeoDataFrame to a measurement-safe CRS.

Design decision
---------------
We use UTM zone projection derived from the dataset centroid longitude/latitude.
UTM gives accurate metric measurements for areas up to roughly one UTM zone wide
(~6° longitude), which covers the typical extents of single survey files.

If the source CRS is already projected and uses metres (e.g. EPSG:32643,
EPSG:27700), we reuse it directly to avoid unnecessary reprojection noise.

If the CRS is missing, we raise a ValueError rather than silently assuming
EPSG:4326. Geographic coordinate interpretation without a known datum is
ambiguous, and silently guessing leads to silent measurement errors.
"""

from __future__ import annotations

import math

import geopandas as gpd
from pyproj import CRS, Transformer

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Geometry types that are used to compute centroid for UTM selection.
_CENTROID_GEOM_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
    "GeometryCollection",
}


def _utm_epsg_from_lonlat(lon: float, lat: float) -> int:
    """
    Return the EPSG code for the UTM zone covering *lon*, *lat*.

    Formula:
        zone = floor((longitude + 180) / 6) + 1

    Clamped to [1, 60] to ensure boundary longitudes (such as +180.0°) never
    generate an invalid UTM zone 61.

    Args:
        lon: Longitude in decimal degrees (WGS 84).
        lat: Latitude in decimal degrees (WGS 84).

    Returns:
        Integer EPSG code (e.g. 32643 for UTM 43N).
    """
    zone = math.floor((lon + 180.0) / 6.0) + 1
    # Clamp to valid UTM zone range (1-60)
    zone = max(1, min(60, zone))
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    logger.debug(
        "UTM zone %d selected for lon=%.4f lat=%.4f → EPSG:%d",
        zone,
        lon,
        lat,
        epsg,
    )
    return epsg


def _gdf_centroid_lonlat(gdf: gpd.GeoDataFrame) -> tuple[float, float]:
    """
    Return the (lon, lat) in WGS 84 of the union centroid of *gdf*.

    Args:
        gdf: GeoDataFrame whose CRS is already set.

    Returns:
        Tuple (longitude, latitude) in decimal degrees.

    Raises:
        ValueError: If the GeoDataFrame is empty or has no valid geometry.
    """
    valid = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if valid.empty:
        raise ValueError("GeoDataFrame contains no valid geometries.")

    src_crs = gdf.crs
    if src_crs is None:
        raise ValueError("GeoDataFrame has no CRS set.")

    # Compute union centroid in source CRS
    union_centroid = valid.geometry.union_all().centroid

    # Transform centroid to WGS 84 for UTM zone selection
    wgs84 = CRS.from_epsg(4326)
    if src_crs.equals(wgs84):
        return union_centroid.x, union_centroid.y

    transformer = Transformer.from_crs(src_crs, wgs84, always_xy=True)
    lon, lat = transformer.transform(union_centroid.x, union_centroid.y)
    return float(lon), float(lat)


def is_geographic_crs(crs: CRS) -> bool:
    """
    Return True if *crs* uses angular units (degrees), False if projected (metres).

    Args:
        crs: PyProj CRS object.

    Returns:
        bool
    """
    return crs.is_geographic


def select_measurement_crs(gdf: gpd.GeoDataFrame) -> CRS:
    """
    Select the best projected CRS for accurate metric measurements.

    Strategy
    --------
    1. If source CRS is missing → raise ValueError.
    2. If source CRS is already projected in metres → return it as-is.
    3. If source CRS is geographic → compute UTM zone from centroid.

    Args:
        gdf: GeoDataFrame with CRS set.

    Returns:
        PyProj CRS object suitable for area/length calculations.

    Raises:
        ValueError: If CRS is missing.
    """
    src_crs = gdf.crs
    if src_crs is None:
        raise ValueError(
            "CRS information is missing from the geospatial file. "
            "Cannot perform accurate metric measurements without a known CRS. "
            "Please ensure your file includes projection information (e.g. a "
            ".prj file for Shapefiles or a CRS declaration in KML)."
        )

    if not is_geographic_crs(src_crs):
        # Already projected – check if units are metres
        axis_info = src_crs.axis_info
        unit_names = {a.unit_name.lower() for a in axis_info}
        if "metre" in unit_names or "meter" in unit_names:
            logger.info(
                "Source CRS '%s' is already projected in metres – using it directly.",
                src_crs.to_epsg() or src_crs.name,
            )
            return src_crs
        # Projected but not in metres (unusual) – fall through to UTM
        logger.warning(
            "Source CRS '%s' is projected but not in metres. Falling back to UTM projection.",
            src_crs.name,
        )

    # Geographic CRS or non-metre projected CRS → select UTM zone
    lon, lat = _gdf_centroid_lonlat(gdf)
    utm_epsg = _utm_epsg_from_lonlat(lon, lat)
    utm_crs = CRS.from_epsg(utm_epsg)
    logger.info(
        "Selected measurement CRS: EPSG:%d (%s) from centroid lon=%.4f lat=%.4f",
        utm_epsg,
        utm_crs.name,
        lon,
        lat,
    )
    return utm_crs


def transform_to_measurement_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Return a new GeoDataFrame reprojected to the measurement CRS.

    Args:
        gdf: Input GeoDataFrame with CRS set.

    Returns:
        New GeoDataFrame in the selected measurement CRS.

    Raises:
        ValueError: If CRS is missing.
    """
    target_crs = select_measurement_crs(gdf)
    if gdf.crs.equals(target_crs):
        logger.debug("GeoDataFrame is already in measurement CRS – no reprojection needed.")
        return gdf
    projected = gdf.to_crs(target_crs)
    logger.info("Reprojected GeoDataFrame to %s.", target_crs.name)
    return projected


def crs_to_string(crs: CRS | None) -> str | None:
    """
    Convert a PyProj CRS to a human-readable string like 'EPSG:4326'.

    Falls back to the CRS name if no EPSG code is available.

    Args:
        crs: PyProj CRS object or None.

    Returns:
        String representation or None.
    """
    if crs is None:
        return None
    epsg = crs.to_epsg()
    if epsg:
        return f"EPSG:{epsg}"
    return crs.name
