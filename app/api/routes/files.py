"""
API routes for geospatial file operations.

Endpoints
---------
POST   /api/files/                      Upload and process a file.
GET    /api/files/{id}/                 Retrieve file information.
GET    /api/files/{id}/measurements/    Retrieve feature measurements.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.config import get_settings
from app.schemas.file import (
    ErrorResponse,
    FileInfoResponse,
    FileUploadResponse,
    MeasurementsResponse,
)
from app.services import file_service
from app.utils.logging import get_logger
from app.utils.validation import validate_upload

logger = get_logger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])


@router.post(
    "/",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a geospatial file",
    description=(
        "Accept a `.kml` or `.zip` (Shapefile) file, process all features, "
        "compute CRS-aware measurements, and return a file ID for subsequent queries."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file or content"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Unexpected processing error"},
    },
)
async def upload_file(
    file: Annotated[UploadFile, File(description="KML or Shapefile ZIP to upload.")],
) -> FileUploadResponse:
    """Upload and process a geospatial file."""
    settings = get_settings()

    logger.info("File upload started: filename='%s'", file.filename)

    # Read file bytes
    content = await file.read()
    filename = file.filename or "unknown"

    # Validate extension, size, and basic content
    try:
        extension = validate_upload(filename, content, settings.max_upload_size_bytes)
    except ValueError as exc:
        logger.warning("Upload validation failed for '%s': %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    logger.info("Uploaded file validated: filename='%s' size=%d bytes", filename, len(content))

    # Run full processing pipeline
    try:
        file_id = file_service.process_upload(filename, content, extension)
    except ValueError as exc:
        logger.error("Processing failed for '%s': %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.error("Unexpected error processing '%s': %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the file.",
        ) from exc

    # Build response
    meta = file_service.get_metadata(file_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Processing completed but metadata was not stored.",
        )

    return FileUploadResponse(
        id=meta["id"],
        filename=meta["filename"],
        feature_count=meta["feature_count"],
        crs=meta["crs"],
        status=meta["status"],
    )


@router.get(
    "/{file_id}/",
    response_model=FileInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get file information",
    description="Return metadata for a previously uploaded geospatial file.",
    responses={
        404: {"model": ErrorResponse, "description": "File not found"},
    },
)
async def get_file_info(file_id: str) -> FileInfoResponse:
    """Retrieve metadata for an uploaded file by ID."""
    meta = file_service.get_metadata(file_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        )

    return FileInfoResponse(
        id=meta["id"],
        filename=meta["filename"],
        feature_count=meta["feature_count"],
        crs=meta["crs"],
        status=meta["status"],
    )


@router.get(
    "/{file_id}/measurements/",
    response_model=MeasurementsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get feature measurements",
    description=(
        "Return all features with their geometry, properties, and metric measurements "
        "(area in m² for polygons, length in m for linestrings)."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "File not found"},
    },
)
async def get_measurements(file_id: str) -> MeasurementsResponse:
    """Retrieve feature-level measurements for an uploaded file."""
    meta = file_service.get_metadata(file_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        )

    return MeasurementsResponse(
        file_id=meta["id"],
        filename=meta["filename"],
        crs=meta["crs"],
        features=meta["features"],
    )
