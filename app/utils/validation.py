"""
File and content validation utilities.

Centralises all input-validation logic so that routes stay thin.
"""

import io
import re
import zipfile
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger(__name__)

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".kml", ".zip"})

# Byte signatures (magic numbers)
_KML_SIGNATURES: tuple[bytes, ...] = (
    b"<?xml",
    b"\xef\xbb\xbf<?xml",  # UTF-8 BOM
    b"<kml",
)
_ZIP_MAGIC: bytes = b"PK\x03\x04"


def validate_extension(filename: str) -> str:
    """
    Return the lowercase file extension if allowed; raise ValueError otherwise.

    Args:
        filename: Original filename from the upload.

    Returns:
        Lowercase extension including the leading dot (e.g. ".kml").

    Raises:
        ValueError: If the extension is not in the allowed set.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension '{ext}'. "
            f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    logger.debug("Extension '%s' is valid.", ext)
    return ext


def validate_file_size(content: bytes, max_bytes: int) -> None:
    """
    Raise ValueError if *content* exceeds *max_bytes*.

    Args:
        content: Raw file bytes.
        max_bytes: Maximum allowed size in bytes.

    Raises:
        ValueError: If the file is larger than allowed.
    """
    size = len(content)
    if size > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        actual_mb = size / (1024 * 1024)
        raise ValueError(f"File size {actual_mb:.1f} MB exceeds maximum allowed {max_mb:.0f} MB.")
    logger.debug("File size %d bytes is within limit.", size)


def validate_kml_content(content: bytes) -> None:
    """
    Perform a lightweight content check for KML files.

    We verify the byte-level signature only – full XML/KML validation
    happens later when GeoPandas/Pyogrio parses the file.

    Args:
        content: Raw KML file bytes.

    Raises:
        ValueError: If the content does not look like a KML/XML document.
    """
    stripped = content.lstrip()
    if not any(stripped.startswith(sig) for sig in _KML_SIGNATURES):
        raise ValueError(
            "File does not appear to be a valid KML document. Expected an XML/KML header."
        )
    logger.debug("KML content signature check passed.")


def validate_zip_content(content: bytes) -> None:
    """
    Validate that the bytes represent a well-formed ZIP archive containing
    at least one .shp file.

    Also guards against Zip Slip / path traversal by checking all member
    paths before extraction occurs here.

    Args:
        content: Raw ZIP file bytes.

    Raises:
        ValueError: For any structural or security issue.
    """
    if not content.startswith(_ZIP_MAGIC):
        raise ValueError("File does not appear to be a valid ZIP archive.")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile as exc:
        raise ValueError(f"ZIP archive is corrupt or unreadable: {exc}") from exc

    # Zip Slip check – reject any entry that would escape the target directory.
    # Handles POSIX (/), Windows (\\), drive letters (C:), and relative escapes (..).
    for name in names:
        clean = name.replace("\\", "/")
        parts = clean.split("/")
        if (
            clean.startswith("/")
            or bool(re.match(r"^[a-zA-Z]:", name))
            or any(part == ".." for part in parts)
            or Path(name).is_absolute()
            or any(part == ".." for part in Path(name).parts)
        ):
            raise ValueError(
                f"ZIP archive contains a potentially unsafe path: '{name}'. Archive rejected."
            )

    shp_files = [n for n in names if n.lower().endswith(".shp")]
    if not shp_files:
        raise ValueError(
            "ZIP archive does not contain a Shapefile (.shp). "
            "Please upload a ZIP that includes at least one .shp file."
        )

    logger.debug(
        "ZIP content validation passed. Found %d .shp file(s): %s",
        len(shp_files),
        shp_files,
    )


def validate_upload(filename: str, content: bytes, max_bytes: int) -> str:
    """
    Run all validation steps for an uploaded file and return the extension.

    Args:
        filename: Original filename.
        content: Raw file bytes.
        max_bytes: Maximum allowed file size in bytes.

    Returns:
        Lowercase extension (".kml" or ".zip").

    Raises:
        ValueError: On any validation failure.
    """
    ext = validate_extension(filename)
    validate_file_size(content, max_bytes)

    if ext == ".kml":
        validate_kml_content(content)
    elif ext == ".zip":
        validate_zip_content(content)

    return ext
