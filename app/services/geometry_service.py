"""
Geometry service.

Handles extraction of geospatial features from a GeoDataFrame and
serialises them to JSON-safe dictionaries suitable for API responses.

Responsibilities
----------------
- Iterate features in a GeoDataFrame.
- Convert each geometry to a GeoJSON dictionary.
- Sanitise properties (NaN, numpy types, datetimes, etc.).
- Delegate measurement computation to measurement_service.
- Delegate CRS transformation to crs_service.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import geopandas as gpd
import numpy as np
from shapely.geometry import mapping

from app.schemas.file import FeatureResponse
from app.services import crs_service, measurement_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _sanitise_value(value: Any) -> Any:
    """
    Recursively convert a value to a JSON-serialisable Python primitive.

    Handles:
    - numpy integer / float scalars
    - numpy arrays
    - float NaN / Inf
    - datetime / date objects
    - None pass-through

    Args:
        value: Any property value from a geospatial feature.

    Returns:
        A JSON-safe Python object.
    """
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(value, np.ndarray):
        return [_sanitise_value(v) for v in value.tolist()]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitise_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitise_value(v) for v in value]
    # Fallback: attempt str conversion for exotic types
    if not isinstance(value, (str, int, float, bool)):
        try:
            return str(value)
        except Exception:  # noqa: BLE001
            return None
    return value


def _sanitise_properties(row_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Remove the 'geometry' key and sanitise all remaining property values.

    Args:
        row_dict: Raw row dictionary from GeoDataFrame.iterfeatures().

    Returns:
        Clean properties dictionary.
    """
    return {key: _sanitise_value(val) for key, val in row_dict.items() if key != "geometry"}


def geometry_to_geojson(geometry: Any) -> dict[str, Any] | None:
    """
    Convert a Shapely geometry to a GeoJSON-compatible dictionary.

    Args:
        geometry: Shapely geometry or None.

    Returns:
        GeoJSON dict or None if the geometry is null/empty.
    """
    if geometry is None or (hasattr(geometry, "is_empty") and geometry.is_empty):
        return None
    try:
        return dict(mapping(geometry))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to convert geometry to GeoJSON: %s", exc)
        return None


def extract_features(
    gdf: gpd.GeoDataFrame,
    source_crs_str: str | None,
) -> list[FeatureResponse]:
    """
    Extract and process all features from a GeoDataFrame.

    For each row:
    1. Reads geometry and properties.
    2. Reprojects to metric CRS.
    3. Calculates measurement on the projected geometry.
    4. Returns the geometry in the *original* CRS (for API response).

    Args:
        gdf: Source GeoDataFrame (in its original CRS).
        source_crs_str: String representation of the source CRS.

    Returns:
        List of FeatureResponse objects.
    """
    features: list[FeatureResponse] = []
    total = len(gdf)
    logger.info("Processing %d features.", total)

    # Pre-compute the projected GeoDataFrame once for all features.
    # If CRS is missing, we cannot measure – we still extract and note the issue.
    projected_gdf: gpd.GeoDataFrame | None = None
    projection_error: str | None = None

    if gdf.crs is not None:
        try:
            projected_gdf = crs_service.transform_to_measurement_crs(gdf)
        except Exception as exc:  # noqa: BLE001
            logger.error("CRS transformation failed: %s", exc)
            projection_error = str(exc)
    else:
        projection_error = (
            "CRS information is missing. Measurements cannot be calculated accurately."
        )

    for idx, row in gdf.iterrows():
        int_idx = int(idx)  # type: ignore[arg-type]
        original_geom = row.geometry

        # Build properties dict (excluding geometry column)
        props = _sanitise_properties(row.drop(labels=["geometry"]).to_dict())

        # Convert original geometry to GeoJSON dict
        geojson_geom = geometry_to_geojson(original_geom)

        geom_type = original_geom.geom_type if original_geom is not None else "Unknown"

        # Compute measurement on projected geometry
        measurement = None
        note = projection_error  # default note if projection failed

        if projected_gdf is not None:
            try:
                proj_geom = projected_gdf.loc[idx, "geometry"]  # type: ignore[index]
                measurement, note = measurement_service.compute_measurement(proj_geom)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Measurement failed for feature %d (%s): %s",
                    int_idx,
                    geom_type,
                    exc,
                )
                note = f"Measurement failed: {exc}"

        features.append(
            FeatureResponse(
                feature_id=int_idx,
                geometry_type=geom_type,
                geometry=geojson_geom,
                properties=props,
                crs=source_crs_str,
                measurement=measurement,
                measurement_note=note,
            )
        )
        logger.debug("Feature %d (%s) processed.", int_idx, geom_type)

    logger.info("Measurement processing completed for %d features.", total)
    return features
