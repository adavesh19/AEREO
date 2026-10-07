"""
Measurement service.

Calculates metric measurements (area in m², length in m) for geospatial
features using *projected* geometries.

IMPORTANT: This module only accepts geometries that have already been
reprojected to a metric CRS by the CRS service.  Do NOT pass raw
EPSG:4326 geometries here – calculations on degree-based coordinates
are geometrically meaningless.
"""

from __future__ import annotations

from shapely.geometry.base import BaseGeometry

from app.schemas.file import AreaMeasurement, LengthMeasurement
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Geometry types that we can measure
_AREA_TYPES = frozenset({"Polygon", "MultiPolygon"})
_LENGTH_TYPES = frozenset({"LineString", "MultiLineString"})
_POINT_TYPES = frozenset({"Point", "MultiPoint"})

# All geometry types we explicitly support
_SUPPORTED_TYPES = _AREA_TYPES | _LENGTH_TYPES | _POINT_TYPES


def compute_measurement(
    projected_geometry: BaseGeometry,
) -> tuple[AreaMeasurement | LengthMeasurement | None, str | None]:
    """
    Compute the appropriate metric measurement for *projected_geometry*.

    The geometry must already be in a projected CRS with metre units.

    Args:
        projected_geometry: A Shapely geometry in a projected metric CRS.

    Returns:
        A tuple of (measurement, note) where:
        - measurement is an AreaMeasurement, LengthMeasurement, or None.
        - note is a human-readable string for unsupported/point geometry or None.
    """
    if projected_geometry is None or projected_geometry.is_empty:
        logger.warning("Received empty or null geometry – returning null measurement.")
        return None, "Geometry is empty or null; measurement not available."

    geom_type = projected_geometry.geom_type

    if geom_type in _AREA_TYPES:
        area = projected_geometry.area
        logger.debug("Computed area: %.4f m² for %s.", area, geom_type)
        return AreaMeasurement(area=round(area, 2)), None

    if geom_type in _LENGTH_TYPES:
        length = projected_geometry.length
        logger.debug("Computed length: %.4f m for %s.", length, geom_type)
        return LengthMeasurement(length=round(length, 2)), None

    if geom_type in _POINT_TYPES:
        # Points have no meaningful area or length
        logger.debug("Point geometry – no measurement required.")
        return None, None

    # Unsupported geometry type (e.g. GeometryCollection)
    logger.warning("Unsupported geometry type '%s' – returning null measurement.", geom_type)
    return None, (
        f"Geometry type '{geom_type}' is not supported for measurement. "
        "Area and length are only calculated for Polygon, MultiPolygon, "
        "LineString, and MultiLineString."
    )
