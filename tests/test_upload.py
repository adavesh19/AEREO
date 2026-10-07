"""
Tests for the upload endpoint (POST /api/files/).
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient


class TestUploadEndpoint:
    """Tests for POST /api/files/."""

    def test_valid_kml_upload_returns_201(self, client: TestClient, valid_kml_bytes: bytes):
        """A valid KML file should return HTTP 201 with a file ID."""
        response = client.post(
            "/api/files/",
            files={"file": ("sample.kml", io.BytesIO(valid_kml_bytes), "application/octet-stream")},
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["filename"] == "sample.kml"
        assert data["status"] == "COMPLETED"

    def test_valid_kml_upload_has_feature_count(self, client: TestClient, valid_kml_bytes: bytes):
        """Uploaded KML should report at least 1 feature."""
        response = client.post(
            "/api/files/",
            files={"file": ("sample.kml", io.BytesIO(valid_kml_bytes), "application/octet-stream")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["feature_count"] >= 1

    def test_valid_kml_upload_has_crs(self, client: TestClient, valid_kml_bytes: bytes):
        """Uploaded KML should detect EPSG:4326."""
        response = client.post(
            "/api/files/",
            files={"file": ("sample.kml", io.BytesIO(valid_kml_bytes), "application/octet-stream")},
        )
        assert response.status_code == 201
        assert response.json()["crs"] == "EPSG:4326"

    def test_valid_shapefile_zip_upload_returns_201(
        self, client: TestClient, multi_feature_zip_bytes: bytes
    ):
        """A valid Shapefile ZIP should return HTTP 201."""
        response = client.post(
            "/api/files/",
            files={"file": ("survey.zip", io.BytesIO(multi_feature_zip_bytes), "application/zip")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["feature_count"] == 3

    def test_invalid_extension_returns_400(self, client: TestClient):
        """An unsupported file extension should return HTTP 400."""
        response = client.post(
            "/api/files/",
            files={"file": ("data.csv", io.BytesIO(b"a,b,c"), "text/csv")},
        )
        assert response.status_code == 400
        assert "extension" in response.json()["detail"].lower()

    def test_txt_extension_returns_400(self, client: TestClient):
        """A .txt file should be rejected."""
        response = client.post(
            "/api/files/",
            files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert response.status_code == 400

    def test_jpg_extension_returns_400(self, client: TestClient):
        """An image file should be rejected."""
        response = client.post(
            "/api/files/",
            files={"file": ("photo.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        )
        assert response.status_code == 400

    def test_corrupt_zip_returns_400(self, client: TestClient, corrupt_zip_bytes: bytes):
        """A corrupt ZIP archive should return HTTP 400."""
        response = client.post(
            "/api/files/",
            files={"file": ("bad.zip", io.BytesIO(corrupt_zip_bytes), "application/zip")},
        )
        assert response.status_code == 400

    def test_zip_without_shp_returns_400(self, client: TestClient, zip_without_shp_bytes: bytes):
        """A ZIP without a .shp file should return HTTP 400."""
        response = client.post(
            "/api/files/",
            files={"file": ("no_shp.zip", io.BytesIO(zip_without_shp_bytes), "application/zip")},
        )
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "shapefile" in detail or "shp" in detail

    def test_zip_slip_returns_400(self, client: TestClient, zip_slip_bytes: bytes):
        """A Zip Slip attack archive should be rejected with HTTP 400."""
        response = client.post(
            "/api/files/",
            files={"file": ("evil.zip", io.BytesIO(zip_slip_bytes), "application/zip")},
        )
        assert response.status_code == 400

    def test_file_size_limit(self, client: TestClient):
        """A file exceeding the size limit should return HTTP 400."""
        settings_import = __import__("app.config", fromlist=["get_settings"]).get_settings
        settings = settings_import()
        oversized = b"<?xml version" + b"x" * (settings.max_upload_size_bytes + 1)
        response = client.post(
            "/api/files/",
            files={"file": ("huge.kml", io.BytesIO(oversized), "application/octet-stream")},
        )
        assert response.status_code == 400
        assert "size" in response.json()["detail"].lower()

    def test_upload_response_schema(self, client: TestClient, valid_kml_bytes: bytes):
        """Response should have all required fields."""
        response = client.post(
            "/api/files/",
            files={"file": ("sample.kml", io.BytesIO(valid_kml_bytes), "application/octet-stream")},
        )
        assert response.status_code == 201
        data = response.json()
        for field in ("id", "filename", "feature_count", "crs", "status"):
            assert field in data, f"Missing field: {field}"

    def test_invalid_kml_content_returns_400(self, client: TestClient):
        """A file with .kml extension but non-XML content should be rejected."""
        response = client.post(
            "/api/files/",
            files={"file": ("fake.kml", io.BytesIO(b"NOT XML AT ALL"), "application/octet-stream")},
        )
        assert response.status_code == 400
