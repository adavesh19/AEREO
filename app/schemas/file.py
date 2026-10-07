"""
Pydantic schemas for API request/response models.

All public-facing types live here so that routes stay thin and the
API contract is fully documented via OpenAPI/Swagger.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class FileStatus(StrEnum):
    """Lifecycle status of an uploaded geospatial file."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Measurement models
# ---------------------------------------------------------------------------


class AreaMeasurement(BaseModel):
    """Area measurement for Polygon / MultiPolygon features."""

    area: float = Field(..., description="Area in square metres (m²).", ge=0)
    unit: str = Field(default="m²", description="Unit of measurement.")


class LengthMeasurement(BaseModel):
    """Length measurement for LineString / MultiLineString features."""

    length: float = Field(..., description="Length in metres (m).", ge=0)
    unit: str = Field(default="m", description="Unit of measurement.")


# ---------------------------------------------------------------------------
# Feature model
# ---------------------------------------------------------------------------


class FeatureResponse(BaseModel):
    """
    Representation of a single geospatial feature.

    The *geometry* field contains a GeoJSON-compatible dictionary and the
    *measurement* field contains area/length/null depending on geometry type.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    feature_id: int = Field(..., description="Zero-based feature index.")
    geometry_type: str = Field(
        ...,
        description=("Geometry type as reported by Shapely (e.g. Polygon, LineString, Point)."),
    )
    geometry: dict[str, Any] | None = Field(
        default=None,
        description="GeoJSON geometry object.",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Feature attributes / properties.",
    )
    crs: str | None = Field(
        default=None,
        description="Coordinate reference system (e.g. EPSG:4326).",
    )
    measurement: AreaMeasurement | LengthMeasurement | None = Field(
        default=None,
        description=(
            "Calculated measurement. null for Point features or unsupported geometry types."
        ),
    )
    measurement_note: str | None = Field(
        default=None,
        description=("Human-readable note, e.g. for unsupported geometry types."),
    )


# ---------------------------------------------------------------------------
# File-level models
# ---------------------------------------------------------------------------


class FileUploadResponse(BaseModel):
    """Response returned after a successful file upload and processing."""

    id: str = Field(..., description="Unique file identifier (UUID).")
    filename: str = Field(..., description="Original filename.")
    feature_count: int = Field(..., description="Total number of features.", ge=0)
    crs: str | None = Field(
        default=None,
        description="Detected CRS (e.g. EPSG:4326). Null if undetectable.",
    )
    status: FileStatus = Field(..., description="Processing status.")


class FileInfoResponse(BaseModel):
    """Response returned by the file information endpoint."""

    id: str = Field(..., description="Unique file identifier (UUID).")
    filename: str = Field(..., description="Original filename.")
    feature_count: int = Field(..., description="Total number of features.", ge=0)
    crs: str | None = Field(
        default=None,
        description="Detected CRS (e.g. EPSG:4326). Null if undetectable.",
    )
    status: FileStatus = Field(..., description="Processing status.")


class MeasurementsResponse(BaseModel):
    """Response returned by the measurements endpoint."""

    file_id: str = Field(..., description="Unique file identifier (UUID).")
    filename: str = Field(..., description="Original filename.")
    crs: str | None = Field(
        default=None,
        description="Detected CRS of the source file.",
    )
    features: list[FeatureResponse] = Field(
        default_factory=list,
        description="List of all processed features with measurements.",
    )


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str = Field(..., description="Human-readable error description.")
