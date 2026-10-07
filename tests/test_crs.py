"""
Tests for CRS detection, selection, and transformation.

Covers:
- EPSG:4326 (geographic) → UTM projection
- Already-projected CRS (EPSG:32643) used directly
- Missing CRS handling
- UTM zone selection accuracy
"""

from __future__ import annotations

import io

import geopandas as gpd
import pytest
from app.services.crs_service import (
    _utm_epsg_from_lonlat,
    crs_to_string,
    is_geographic_crs,
    select_measurement_crs,
    transform_to_measurement_crs,
)
from pyproj import CRS
from shapely.geometry import Polygon


class TestCrsDetection:
    """Unit tests for CRS detection helpers."""

    def test_epsg4326_is_geographic(self):
        """EPSG:4326 must be identified as geographic."""
        crs = CRS.from_epsg(4326)
        assert is_geographic_crs(crs) is True

    def test_epsg32643_is_not_geographic(self):
        """EPSG:32643 (UTM 43N) must be identified as projected."""
        crs = CRS.from_epsg(32643)
        assert is_geographic_crs(crs) is False

    def test_epsg27700_is_not_geographic(self):
        """EPSG:27700 (British National Grid) must be identified as projected."""
        crs = CRS.from_epsg(27700)
        assert is_geographic_crs(crs) is False

    def test_crs_to_string_epsg4326(self):
        """crs_to_string should return 'EPSG:4326' for geographic CRS."""
        crs = CRS.from_epsg(4326)
        assert crs_to_string(crs) == "EPSG:4326"

    def test_crs_to_string_none(self):
        """crs_to_string should return None for None input."""
        assert crs_to_string(None) is None

    def test_crs_to_string_projected(self):
        """crs_to_string should return 'EPSG:32643' for UTM 43N."""
        crs = CRS.from_epsg(32643)
        assert crs_to_string(crs) == "EPSG:32643"


class TestUtmZoneSelection:
    """Unit tests for UTM zone calculation."""

    @pytest.mark.parametrize(
        "lon,lat,expected_epsg",
        [
            (77.59, 12.97, 32643),  # Bengaluru, India → UTM 43N
            (-0.12, 51.50, 32630),  # London, UK → UTM 30N
            (-73.93, 40.73, 32618),  # New York, USA → UTM 18N
            (151.21, -33.87, 32756),  # Sydney, Australia → UTM 56S
            (37.62, -1.29, 32737),  # Nairobi, Kenya → UTM 37S (lat<0)
            (0.0, 0.0, 32631),  # Prime meridian equator → UTM 31N
            (180.0, 10.0, 32660),  # Dateline East (clamped to Zone 60N, not 61N)
            (180.0, -10.0, 32760),  # Dateline East (clamped to Zone 60S, not 61S)
            (-180.0, 10.0, 32601),  # Dateline West → UTM 1N
            (-180.0, -10.0, 32701),  # Dateline West → UTM 1S
            (-0.001, 10.0, 32630),  # Just west of Prime Meridian → UTM 30N
            (0.0, 10.0, 32631),  # Exactly at Prime Meridian → UTM 31N
            (5.999, 10.0, 32631),  # Inside zone 31 near eastern boundary → UTM 31N
            (6.0, 10.0, 32632),  # At zone 32 boundary → UTM 32N
        ],
    )
    def test_utm_zone_selection(self, lon: float, lat: float, expected_epsg: int):
        """UTM zone selection maps cities and boundary longitudes to correct EPSG codes."""
        assert _utm_epsg_from_lonlat(lon, lat) == expected_epsg

    def test_bengaluru_utm_zone(self):
        """Bengaluru (77.59°E, 12.97°N) → UTM 43N → EPSG:32643."""
        epsg = _utm_epsg_from_lonlat(77.59, 12.97)
        assert epsg == 32643

    def test_longitude_180_does_not_generate_zone_61(self):
        """180.0° longitude must be clamped to zone 60 (EPSG:32660), never invalid zone 61."""
        assert _utm_epsg_from_lonlat(180.0, 0.0) == 32660
        assert _utm_epsg_from_lonlat(180.0, -45.0) == 32760


class TestSelectMeasurementCrs:
    """Tests for select_measurement_crs() function."""

    def test_geographic_crs_returns_utm(self):
        """A geographic CRS GeoDataFrame should return a UTM CRS."""
        poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)])
        gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")
        result_crs = select_measurement_crs(gdf)
        assert not is_geographic_crs(result_crs)
        assert result_crs.to_epsg() == 32643

    def test_projected_crs_returned_directly(self):
        """A projected CRS GeoDataFrame should reuse the existing CRS."""
        poly = Polygon(
            [
                (770000, 1434000),
                (771000, 1434000),
                (771000, 1435000),
                (770000, 1435000),
            ]
        )
        gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:32643")
        result_crs = select_measurement_crs(gdf)
        assert result_crs.to_epsg() == 32643

    def test_missing_crs_raises_value_error(self):
        """Missing CRS must raise ValueError (not silently assume EPSG:4326)."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        gdf = gpd.GeoDataFrame(geometry=[poly], crs=None)
        with pytest.raises(ValueError, match="CRS information is missing"):
            select_measurement_crs(gdf)


class TestTransformToMeasurementCrs:
    """Tests for transform_to_measurement_crs() function."""

    def test_transformation_changes_crs(self):
        """Transformation of EPSG:4326 GDF should yield a projected GDF."""
        poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)])
        gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")
        projected = transform_to_measurement_crs(gdf)
        assert projected.crs is not None
        assert not is_geographic_crs(projected.crs)

    def test_transformation_preserves_row_count(self):
        """Transformation must not add or drop rows."""
        poly1 = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)])
        poly2 = Polygon([(77.70, 12.97), (77.71, 12.97), (77.71, 12.98), (77.70, 12.98)])
        gdf = gpd.GeoDataFrame(geometry=[poly1, poly2], crs="EPSG:4326")
        projected = transform_to_measurement_crs(gdf)
        assert len(projected) == len(gdf)

    def test_area_is_reasonable_after_projection(self):
        """Area computed after projection must be >> area in degrees."""
        # 0.01° × 0.01° square near Bengaluru
        poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)])
        gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")
        projected = transform_to_measurement_crs(gdf)
        projected_area = projected.geometry.iloc[0].area
        raw_area = gdf.geometry.iloc[0].area  # in degrees² – tiny
        # Projected area should be ~1.2M m²; raw area ~0.0001 deg²
        assert projected_area > 10_000, f"Area {projected_area} seems wrong"
        assert projected_area > raw_area * 1_000  # orders of magnitude larger


class TestCrsIntegration:
    """API-level CRS tests using the TestClient."""

    def test_epsg4326_upload_reports_crs(self, client, valid_kml_bytes):
        """EPSG:4326 KML should report EPSG:4326 in response."""
        response = client.post(
            "/api/files/",
            files={"file": ("sample.kml", io.BytesIO(valid_kml_bytes), "application/octet-stream")},
        )
        assert response.status_code == 201
        assert response.json()["crs"] == "EPSG:4326"

    def test_projected_crs_shapefile(self, client, projected_crs_zip_bytes):
        """Shapefile in projected CRS should report that CRS and compute valid area."""
        response = client.post(
            "/api/files/",
            files={"file": ("proj.zip", io.BytesIO(projected_crs_zip_bytes), "application/zip")},
        )
        assert response.status_code == 201
        data = response.json()
        # Should detect EPSG:32643
        assert data["crs"] == "EPSG:32643"

    def test_missing_crs_shapefile_still_processes(self, client, missing_crs_zip_bytes):
        """A shapefile with no CRS should process but report null crs and note in measurements."""
        response = client.post(
            "/api/files/",
            files={"file": ("nocrs.zip", io.BytesIO(missing_crs_zip_bytes), "application/zip")},
        )
        # Should succeed (201) but CRS will be null
        assert response.status_code == 201
        data = response.json()
        assert data["crs"] is None
        # Measurements should still be returned but with null measurement + note
        file_id = data["id"]
        meas_resp = client.get(f"/api/files/{file_id}/measurements/")
        assert meas_resp.status_code == 200
        features = meas_resp.json()["features"]
        assert features  # At least one feature
        # With no CRS, measurement should be null but a note should explain
        for feat in features:
            assert feat["measurement"] is None
