"""
File service.

Orchestrates the complete file-processing pipeline:

Upload → Secure storage → File type detection → GeoPandas loading
→ CRS detection → Feature extraction → Measurement → Metadata storage

In-memory metadata store
-------------------------
File metadata is stored in a module-level dictionary keyed by UUID.
This is intentional for this assignment – it keeps the service simple
and stateless (restarts clear history).

The architecture is deliberately designed for easy migration:
- Replace ``_metadata_store`` with SQLAlchemy / PostgreSQL calls.
- Replace ``_save_file`` with S3/GCS/Azure Blob SDK calls.
See README § Storage for details.
"""

from __future__ import annotations

import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import pyogrio

from app.config import get_settings
from app.schemas.file import (
    FeatureResponse,
    FileStatus,
)
from app.services import crs_service, geometry_service
from app.utils.logging import get_logger

# Explicitly configure GeoPandas to use Pyogrio as the I/O engine
gpd.options.io_engine = "pyogrio"

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# In-memory metadata store
# ---------------------------------------------------------------------------

# Schema: { file_id: { "filename", "feature_count", "crs", "status", "features" } }
_metadata_store: dict[str, dict[str, Any]] = {}


def get_metadata(file_id: str) -> dict[str, Any] | None:
    """Return file metadata dict or None if not found."""
    return _metadata_store.get(file_id)


def list_all_metadata() -> list[dict[str, Any]]:
    """Return all stored metadata entries (for debugging)."""
    return list(_metadata_store.values())


# ---------------------------------------------------------------------------
# Driver verification
# ---------------------------------------------------------------------------


def verify_driver_support() -> None:
    """
    Verify that required GDAL drivers are available in Pyogrio.

    Raises:
        RuntimeError: If KML or ESRI Shapefile driver is unavailable.
    """
    drivers = pyogrio.list_drivers()
    has_kml = "KML" in drivers or "LIBKML" in drivers
    has_shp = "ESRI Shapefile" in drivers

    if not has_kml:
        raise RuntimeError(
            "KML driver is not available in the installed GDAL/Pyogrio build. "
            f"Available drivers: {list(drivers.keys())}"
        )
    if not has_shp:
        raise RuntimeError(
            "ESRI Shapefile driver is not available in the installed GDAL/Pyogrio build. "
            f"Available drivers: {list(drivers.keys())}"
        )
    logger.debug(
        "Pyogrio geospatial drivers verified (GDAL %s, KML, ESRI Shapefile present).",
        pyogrio.__gdal_version_string__,
    )


# ---------------------------------------------------------------------------
# File storage
# ---------------------------------------------------------------------------


def _ensure_upload_dir() -> Path:
    """Create the upload directory if it doesn't exist and return its Path."""
    settings = get_settings()
    path = settings.upload_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_file(file_id: str, original_filename: str, content: bytes) -> Path:
    """
    Save raw uploaded bytes to a unique path under the upload directory.

    Args:
        file_id: UUID string for this upload.
        original_filename: Original filename (for extension preservation).
        content: Raw file bytes.

    Returns:
        Path to the saved file.
    """
    upload_dir = _ensure_upload_dir()
    ext = Path(original_filename).suffix.lower()
    dest = upload_dir / f"{file_id}{ext}"
    dest.write_bytes(content)
    logger.info("Saved uploaded file to '%s' (%d bytes).", dest, len(content))
    return dest


# ---------------------------------------------------------------------------
# Geospatial loading helpers
# ---------------------------------------------------------------------------


def _load_kml(file_path: Path) -> gpd.GeoDataFrame:
    """
    Load a KML file into a GeoDataFrame using Pyogrio.

    KML files may contain multiple layers; we read all layers and
    concatenate them into a single GeoDataFrame.

    Args:
        file_path: Path to the .kml file.

    Returns:
        Combined GeoDataFrame from all KML layers.

    Raises:
        RuntimeError: If KML driver support is missing from GDAL/Pyogrio.
        ValueError: If the file cannot be parsed or contains no features.
    """
    verify_driver_support()

    try:
        raw_layers = pyogrio.list_layers(str(file_path))
    except Exception as exc:
        raise ValueError(f"Cannot read KML file – it may be corrupt or invalid: {exc}") from exc

    if raw_layers is None or len(raw_layers) == 0:
        raise ValueError("KML file contains no readable layers.")

    # pyogrio.list_layers returns a 2D numpy array where [:, 0] are layer names,
    # or an iterable of layer descriptors.
    if hasattr(raw_layers, "shape") and len(raw_layers.shape) == 2:
        layer_names = [str(name) for name in raw_layers[:, 0]]
    else:
        layer_names = [
            str(item[0] if isinstance(item, (list, tuple)) else item) for item in raw_layers
        ]

    gdfs: list[gpd.GeoDataFrame] = []
    for layer in layer_names:
        try:
            gdf = gpd.read_file(str(file_path), layer=layer, engine="pyogrio")
            if not gdf.empty:
                gdfs.append(gdf)
                logger.debug("Loaded KML layer '%s' with %d features.", layer, len(gdf))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping KML layer '%s': %s", layer, exc)

    if not gdfs:
        raise ValueError("KML file was parsed successfully but contains no valid features.")

    first_crs = gdfs[0].crs
    combined = gpd.GeoDataFrame(
        gpd.pd.concat(gdfs, ignore_index=True),
        crs=first_crs,
    )
    logger.info("Loaded KML with %d total features across %d layer(s).", len(combined), len(gdfs))
    return combined


def _extract_zip_safe(zip_path: Path, extract_dir: Path) -> None:
    """
    Extract a ZIP archive safely, preventing Zip Slip / path traversal.

    Args:
        zip_path: Path to the ZIP file.
        extract_dir: Target directory for extraction.

    Raises:
        ValueError: If any path traversal is detected or the archive is corrupt.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                member_path = Path(member.filename)
                # Reject absolute paths and '..'-based traversal
                if member_path.is_absolute() or any(part == ".." for part in member_path.parts):
                    raise ValueError(
                        f"ZIP member '{member.filename}' contains a path traversal "
                        "sequence. Archive rejected for security reasons."
                    )
                target = extract_dir / member_path
                # Final double-check: resolved path must stay inside extract_dir
                resolved_target = target.resolve()
                resolved_extract = extract_dir.resolve()
                if not str(resolved_target).startswith(str(resolved_extract)):
                    raise ValueError(
                        f"ZIP member '{member.filename}' would extract outside the "
                        "target directory. Archive rejected."
                    )
                zf.extract(member, path=extract_dir)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"ZIP archive is corrupt or unreadable: {exc}") from exc

    logger.debug("ZIP extracted safely to '%s'.", extract_dir)


def _load_shapefile_zip(zip_path: Path) -> gpd.GeoDataFrame:
    """
    Extract a Shapefile ZIP and load it into a GeoDataFrame.

    Args:
        zip_path: Path to the uploaded ZIP file.

    Returns:
        GeoDataFrame loaded from the Shapefile.

    Raises:
        ValueError: If no valid Shapefile is found or loading fails.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        _extract_zip_safe(zip_path, tmp_path)

        shp_files = list(tmp_path.rglob("*.shp"))
        if not shp_files:
            raise ValueError("ZIP archive does not contain a valid Shapefile (.shp).")

        # Use the first .shp found
        shp_path = shp_files[0]
        logger.info("Loading Shapefile from '%s'.", shp_path.name)

        verify_driver_support()

        try:
            gdf = gpd.read_file(str(shp_path), engine="pyogrio")
        except Exception as exc:
            raise ValueError(f"Failed to read Shapefile '{shp_path.name}': {exc}") from exc

        if gdf.empty:
            raise ValueError(f"Shapefile '{shp_path.name}' is empty (contains no features).")

        logger.info("Loaded Shapefile '%s' with %d features.", shp_path.name, len(gdf))
        return gdf


def _load_geospatial_file(file_path: Path, extension: str) -> gpd.GeoDataFrame:
    """
    Dispatch to the appropriate loader based on file extension.

    Args:
        file_path: Path to the saved file.
        extension: Lowercase extension (".kml" or ".zip").

    Returns:
        Loaded GeoDataFrame.

    Raises:
        ValueError: For unsupported extensions or loading failures.
    """
    if extension == ".kml":
        return _load_kml(file_path)
    if extension == ".zip":
        return _load_shapefile_zip(file_path)
    raise ValueError(f"Unsupported file extension: '{extension}'.")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def process_upload(
    filename: str,
    content: bytes,
    extension: str,
) -> str:
    """
    Run the full file-processing pipeline and return a file ID.

    Pipeline
    --------
    1. Generate unique file ID.
    2. Save file securely.
    3. Load into GeoDataFrame.
    4. Detect CRS.
    5. Extract features and compute measurements.
    6. Store metadata.
    7. Return file ID.

    Args:
        filename: Original filename.
        content: Raw file bytes (already validated).
        extension: Lowercase file extension (".kml" or ".zip").

    Returns:
        UUID string identifying the processed file.

    Raises:
        ValueError: If geospatial loading or processing fails.
        RuntimeError: For unexpected errors during processing.
    """
    file_id = str(uuid.uuid4())
    logger.info("Starting upload processing: id=%s filename='%s'", file_id, filename)

    # --- Secure storage ---
    file_path = _save_file(file_id, filename, content)

    # --- Load geospatial data ---
    try:
        gdf = _load_geospatial_file(file_path, extension)
    except ValueError:
        # Loading failed – mark as FAILED and re-raise for the route handler
        _metadata_store[file_id] = {
            "id": file_id,
            "filename": filename,
            "feature_count": 0,
            "crs": None,
            "status": FileStatus.FAILED,
            "features": [],
        }
        raise

    # --- CRS detection ---
    raw_crs = gdf.crs
    crs_str = crs_service.crs_to_string(raw_crs)
    if crs_str:
        logger.info("Detected CRS: %s", crs_str)
    else:
        logger.warning("CRS information could not be detected for file '%s'.", filename)

    # --- Feature extraction and measurement ---
    try:
        features: list[FeatureResponse] = geometry_service.extract_features(gdf, crs_str)
    except Exception as exc:
        logger.error("Feature extraction failed for file '%s': %s", filename, exc)
        _metadata_store[file_id] = {
            "id": file_id,
            "filename": filename,
            "feature_count": len(gdf),
            "crs": crs_str,
            "status": FileStatus.FAILED,
            "features": [],
        }
        raise RuntimeError(f"Unexpected error during feature processing: {exc}") from exc

    # --- Store metadata ---
    _metadata_store[file_id] = {
        "id": file_id,
        "filename": filename,
        "feature_count": len(features),
        "crs": crs_str,
        "status": FileStatus.COMPLETED,
        "features": features,
    }

    logger.info(
        "Upload processing complete: id=%s features=%d crs=%s",
        file_id,
        len(features),
        crs_str,
    )
    return file_id
