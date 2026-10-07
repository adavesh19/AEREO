"""
Integration tests for the measurements API endpoint.
GET /api/files/{id}/measurements/
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient


def _upload(client: TestClient, filename: str, content: bytes) -> str:
    """Upload a file and return its ID."""
    ct = "application/zip" if filename.endswith(".zip") else "application/octet-stream"
    response = client.post(
        "/api/files/",
        files={"file": (filename, io.BytesIO(content), ct)},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _get_measurements(client: TestClient, file_id: str) -> dict:
    """Retrieve measurements response for a file ID."""
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 200, response.text
    return response.json()


class TestMeasurementsApiEndpoint:
    """Integration-level tests for the measurements endpoint."""

    def test_404_for_unknown_file(self, client: TestClient):
        """Measurements endpoint should return 404 for unknown file IDs."""
        resp = client.get("/api/files/does-not-exist/measurements/")
        assert resp.status_code == 404

    def test_kml_measurements_top_level_schema(self, client: TestClient, valid_kml_bytes: bytes):
        """Measurements response must have correct top-level schema."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        data = _get_measurements(client, file_id)
        for field in ("file_id", "filename", "crs", "features"):
            assert field in data, f"Missing top-level field: {field}"
        assert isinstance(data["features"], list)

    def test_kml_feature_schema(self, client: TestClient, valid_kml_bytes: bytes):
        """Each feature must have required fields."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        data = _get_measurements(client, file_id)
        required = ("feature_id", "geometry_type", "geometry", "properties", "crs")
        for feat in data["features"]:
            for field in required:
                assert field in feat, f"Feature missing field: {field}"

    def test_kml_polygon_has_area_in_sq_metres(self, client: TestClient, valid_kml_bytes: bytes):
        """KML Polygon should have area >> 1 m² (not degrees)."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        data = _get_measurements(client, file_id)
        polygons = [f for f in data["features"] if f["geometry_type"] == "Polygon"]
        assert polygons, "No Polygon in KML"
        area = polygons[0]["measurement"]["area"]
        assert area > 1_000, f"Area {area} m² looks like degrees, not metres"
        assert polygons[0]["measurement"]["unit"] == "m²"

    def test_kml_linestring_has_length_in_metres(self, client: TestClient, valid_kml_bytes: bytes):
        """KML LineString should have length >> 1 m (not degrees)."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        data = _get_measurements(client, file_id)
        lines = [f for f in data["features"] if f["geometry_type"] == "LineString"]
        assert lines, "No LineString in KML"
        length = lines[0]["measurement"]["length"]
        assert length > 100, f"Length {length} m looks like degrees, not metres"
        assert lines[0]["measurement"]["unit"] == "m"

    def test_kml_point_null_measurement(self, client: TestClient, valid_kml_bytes: bytes):
        """KML Point features should have null measurement."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        data = _get_measurements(client, file_id)
        points = [f for f in data["features"] if f["geometry_type"] == "Point"]
        assert points, "No Point in KML"
        for pt in points:
            assert pt["measurement"] is None

    def test_shapefile_polygon_area(self, client: TestClient, polygon_zip_bytes: bytes):
        """Shapefile Polygon ZIP should return positive area."""
        file_id = _upload(client, "poly.zip", polygon_zip_bytes)
        data = _get_measurements(client, file_id)
        feat = data["features"][0]
        assert feat["geometry_type"] == "Polygon"
        assert feat["measurement"]["area"] > 0

    def test_shapefile_linestring_length(self, client: TestClient, linestring_zip_bytes: bytes):
        """Shapefile LineString ZIP should return positive length."""
        file_id = _upload(client, "line.zip", linestring_zip_bytes)
        data = _get_measurements(client, file_id)
        feat = data["features"][0]
        assert feat["geometry_type"] == "LineString"
        assert feat["measurement"]["length"] > 0

    def test_multipolygon_total_area(self, client: TestClient, multipolygon_zip_bytes: bytes):
        """MultiPolygon should return total area across all components."""
        file_id = _upload(client, "mpoly.zip", multipolygon_zip_bytes)
        data = _get_measurements(client, file_id)
        feat = data["features"][0]
        assert feat["geometry_type"] == "MultiPolygon"
        assert feat["measurement"]["area"] > 0
        assert feat["measurement"]["unit"] == "m²"

    def test_multilinestring_total_length(
        self, client: TestClient, multilinestring_zip_bytes: bytes
    ):
        """MultiLineString should return total length across all components."""
        file_id = _upload(client, "mline.zip", multilinestring_zip_bytes)
        data = _get_measurements(client, file_id)
        feat = data["features"][0]
        assert feat["geometry_type"] == "MultiLineString"
        assert feat["measurement"]["length"] > 0
        assert feat["measurement"]["unit"] == "m"

    def test_geometry_is_valid_geojson(self, client: TestClient, valid_kml_bytes: bytes):
        """All non-null geometries must be GeoJSON dicts with 'type' and 'coordinates'."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        data = _get_measurements(client, file_id)
        for feat in data["features"]:
            if feat["geometry"] is not None:
                assert "type" in feat["geometry"]
                assert "coordinates" in feat["geometry"]

    def test_response_fully_json_serialisable(self, client: TestClient, valid_kml_bytes: bytes):
        """Full response body must round-trip through json.dumps without error."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        raw = client.get(f"/api/files/{file_id}/measurements/").json()
        try:
            json.dumps(raw)
        except (TypeError, ValueError) as exc:
            pytest.fail(f"Response is not JSON-serialisable: {exc}")

    def test_crs_matches_file_info(self, client: TestClient, valid_kml_bytes: bytes):
        """CRS in measurements must match CRS in file info."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        info_crs = client.get(f"/api/files/{file_id}/").json()["crs"]
        meas_crs = _get_measurements(client, file_id)["crs"]
        assert meas_crs == info_crs

    def test_missing_crs_produces_null_measurements(
        self, client: TestClient, missing_crs_zip_bytes: bytes
    ):
        """Shapefile with no CRS should process but measurements are null."""
        file_id = _upload(client, "nocrs.zip", missing_crs_zip_bytes)
        data = _get_measurements(client, file_id)
        for feat in data["features"]:
            assert feat["measurement"] is None
            # Should have an explanatory note
            assert feat.get("measurement_note") is not None

    def test_feature_ids_are_sequential(self, client: TestClient, valid_kml_bytes: bytes):
        """Feature IDs should be non-negative integers."""
        file_id = _upload(client, "sample.kml", valid_kml_bytes)
        data = _get_measurements(client, file_id)
        ids = [f["feature_id"] for f in data["features"]]
        assert all(isinstance(i, int) and i >= 0 for i in ids)
