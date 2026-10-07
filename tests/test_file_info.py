"""
Tests for the file information endpoint (GET /api/files/{id}/).
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient


class TestFileInfoEndpoint:
    """Tests for GET /api/files/{id}/."""

    def _upload_kml(self, client: TestClient, kml_bytes: bytes) -> str:
        """Helper to upload a KML and return the file ID."""
        response = client.post(
            "/api/files/",
            files={"file": ("sample.kml", io.BytesIO(kml_bytes), "application/octet-stream")},
        )
        assert response.status_code == 201
        return response.json()["id"]

    def test_get_existing_file_info(self, client: TestClient, valid_kml_bytes: bytes):
        """GET on a known file ID should return 200 with correct metadata."""
        file_id = self._upload_kml(client, valid_kml_bytes)
        response = client.get(f"/api/files/{file_id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == file_id
        assert data["filename"] == "sample.kml"
        assert data["status"] == "COMPLETED"

    def test_get_file_info_crs(self, client: TestClient, valid_kml_bytes: bytes):
        """File info should include the detected CRS."""
        file_id = self._upload_kml(client, valid_kml_bytes)
        response = client.get(f"/api/files/{file_id}/")
        assert response.status_code == 200
        assert response.json()["crs"] == "EPSG:4326"

    def test_get_file_info_feature_count(self, client: TestClient, valid_kml_bytes: bytes):
        """File info should include the correct feature count."""
        file_id = self._upload_kml(client, valid_kml_bytes)
        response = client.get(f"/api/files/{file_id}/")
        assert response.status_code == 200
        assert response.json()["feature_count"] >= 1

    def test_get_nonexistent_file_returns_404(self, client: TestClient):
        """Requesting a non-existent file ID should return 404."""
        response = client.get("/api/files/nonexistent-id-abc123/")
        assert response.status_code == 404
        assert response.json()["detail"] == "File not found."

    def test_get_file_info_schema(self, client: TestClient, valid_kml_bytes: bytes):
        """Response schema should contain all required fields."""
        file_id = self._upload_kml(client, valid_kml_bytes)
        response = client.get(f"/api/files/{file_id}/")
        assert response.status_code == 200
        data = response.json()
        for field in ("id", "filename", "feature_count", "crs", "status"):
            assert field in data, f"Missing field: {field}"

    def test_file_id_is_unique(self, client: TestClient, valid_kml_bytes: bytes):
        """Each upload should generate a unique file ID."""
        id1 = self._upload_kml(client, valid_kml_bytes)
        id2 = self._upload_kml(client, valid_kml_bytes)
        assert id1 != id2

    def test_health_endpoint(self, client: TestClient):
        """Health endpoint should return {'status': 'ok'}."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
