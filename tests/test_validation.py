"""
Tests for the validation utilities.

Covers:
- File extension validation
- File size validation
- KML content validation
- ZIP content validation
- Zip Slip protection
"""

from __future__ import annotations

import io
import zipfile

import pytest
from app.utils.validation import (
    validate_extension,
    validate_file_size,
    validate_kml_content,
    validate_upload,
    validate_zip_content,
)


class TestExtensionValidation:
    """Tests for validate_extension()."""

    @pytest.mark.parametrize("filename", ["data.kml", "DATA.KML", "survey.KmL"])
    def test_kml_extension_allowed(self, filename: str):
        """KML files (any case) should be accepted."""
        ext = validate_extension(filename)
        assert ext == ".kml"

    @pytest.mark.parametrize("filename", ["data.zip", "SURVEY.ZIP", "shapefile.Zip"])
    def test_zip_extension_allowed(self, filename: str):
        """ZIP files (any case) should be accepted."""
        ext = validate_extension(filename)
        assert ext == ".zip"

    @pytest.mark.parametrize(
        "filename",
        [
            "data.csv",
            "data.txt",
            "data.json",
            "data.exe",
            "data.jpg",
            "data.png",
            "data.pdf",
            "data.geojson",
            "data.gpx",
            "data",  # no extension
        ],
    )
    def test_invalid_extension_raises(self, filename: str):
        """Unsupported extensions must raise ValueError."""
        with pytest.raises(ValueError, match="extension"):
            validate_extension(filename)


class TestFileSizeValidation:
    """Tests for validate_file_size()."""

    def test_file_within_limit_passes(self):
        """File within limit should pass without error."""
        validate_file_size(b"x" * 1000, max_bytes=5000)

    def test_file_at_exact_limit_passes(self):
        """File exactly at the limit should pass."""
        validate_file_size(b"x" * 5000, max_bytes=5000)

    def test_file_over_limit_raises(self):
        """File over limit must raise ValueError."""
        with pytest.raises(ValueError, match=r"[Ss]ize"):
            validate_file_size(b"x" * 5001, max_bytes=5000)

    def test_zero_byte_file_passes(self):
        """Empty file (0 bytes) is within limit."""
        validate_file_size(b"", max_bytes=100)


class TestKmlContentValidation:
    """Tests for validate_kml_content()."""

    @pytest.mark.parametrize(
        "content",
        [
            b'<?xml version="1.0"?><kml/>',
            b'\xef\xbb\xbf<?xml version="1.0"?>',  # UTF-8 BOM
            b'<kml xmlns="...">',
        ],
    )
    def test_valid_kml_content_passes(self, content: bytes):
        """Valid KML/XML headers should pass."""
        validate_kml_content(content)

    @pytest.mark.parametrize(
        "content",
        [
            b"NOT XML",
            b"PK\x03\x04",  # ZIP magic
            b"\xff\xd8\xff",  # JPEG magic
            b"CSV,data,here",
            b'{"type": "geojson"}',  # JSON
        ],
    )
    def test_invalid_kml_content_raises(self, content: bytes):
        """Non-XML content should raise ValueError."""
        with pytest.raises(ValueError):
            validate_kml_content(content)


class TestZipContentValidation:
    """Tests for validate_zip_content()."""

    def test_valid_zip_with_shp_passes(self):
        """A valid ZIP containing a .shp file should pass."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("survey.shp", b"fake shp content")
            zf.writestr("survey.dbf", b"fake dbf content")
        validate_zip_content(buf.getvalue())

    def test_zip_without_shp_raises(self):
        """A ZIP with no .shp file should raise ValueError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "no shapefile here")
        with pytest.raises(ValueError, match=r"[Ss]hapefile"):
            validate_zip_content(buf.getvalue())

    def test_corrupt_zip_raises(self):
        """Corrupt ZIP bytes should raise ValueError."""
        with pytest.raises(ValueError, match=r"[Cc]orrupt|[Zz][Ii][Pp]"):
            validate_zip_content(b"PK\x03\x04" + b"\x00" * 20 + b"garbage")

    def test_non_zip_bytes_raises(self):
        """Bytes that don't start with ZIP magic should raise ValueError."""
        with pytest.raises(ValueError, match=r"[Zz][Ii][Pp]"):
            validate_zip_content(b"<?xml version")

    def test_zip_slip_path_traversal_raises(self):
        """ZIP entry with '..' path traversal should be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../evil.sh", "rm -rf /")
        with pytest.raises(ValueError, match=r"[Tt]raversal|[Uu]nsafe|[Pp]ath"):
            validate_zip_content(buf.getvalue())

    def test_zip_absolute_path_raises(self):
        """ZIP entry with absolute path should be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            info = zipfile.ZipInfo("/etc/evil.sh")
            zf.writestr(info, "evil")
        # Absolute path detection
        with pytest.raises(ValueError):
            validate_zip_content(buf.getvalue())


class TestValidateUpload:
    """Integration tests for the combined validate_upload() function."""

    def test_valid_kml_passes(self, valid_kml_bytes: bytes):
        """Full validation pipeline should pass for valid KML."""
        ext = validate_upload("survey.kml", valid_kml_bytes, max_bytes=10_000_000)
        assert ext == ".kml"

    def test_valid_zip_passes(self):
        """Full validation pipeline should pass for valid ZIP with .shp."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("survey.shp", b"fake")
        ext = validate_upload("survey.zip", buf.getvalue(), max_bytes=10_000_000)
        assert ext == ".zip"

    def test_invalid_extension_raises(self):
        """Invalid extension should raise in the combined function."""
        with pytest.raises(ValueError, match=r"[Ee]xtension"):
            validate_upload("data.csv", b"a,b,c", max_bytes=10_000_000)

    def test_oversized_file_raises(self, valid_kml_bytes: bytes):
        """Oversized file should be caught before content validation."""
        with pytest.raises(ValueError, match=r"[Ss]ize"):
            validate_upload("survey.kml", valid_kml_bytes, max_bytes=10)
