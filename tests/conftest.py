"""
Test configuration and shared fixtures.

All test fixtures that create temporary files generate them programmatically
using GeoPandas / Shapely so that no binary test files need to be committed
to version control.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import zipfile
from collections.abc import Generator
from pathlib import Path

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon

# Ensure GeoPandas uses Pyogrio in tests
gpd.options.io_engine = "pyogrio"

# ---------------------------------------------------------------------------
# Environment setup BEFORE importing app modules
# ---------------------------------------------------------------------------
# Point to a temporary upload directory so tests never pollute production.
_TMP_UPLOAD_DIR = tempfile.mkdtemp(prefix="geo_test_uploads_")
os.environ["UPLOAD_DIR"] = _TMP_UPLOAD_DIR
os.environ["LOG_LEVEL"] = "WARNING"  # Quieter test output

# Import app AFTER setting env vars so Settings picks them up.
from app.main import app  # noqa: E402
from app.services import file_service  # noqa: E402

# ---------------------------------------------------------------------------
# Session-wide teardown
# ---------------------------------------------------------------------------


def pytest_sessionfinish(session, exitstatus):
    """Clean up the temporary upload directory after the full test session."""
    shutil.rmtree(_TMP_UPLOAD_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """FastAPI TestClient for API-level tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clear_metadata_store():
    """Reset the in-memory metadata store before each test."""
    file_service._metadata_store.clear()
    yield
    file_service._metadata_store.clear()


# ---------------------------------------------------------------------------
# KML file helpers
# ---------------------------------------------------------------------------

_SAMPLE_KML = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Test Dataset</name>
    <Placemark>
      <name>Tower</name>
      <Point><coordinates>77.5946,12.9716,0</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Road</name>
      <LineString>
        <coordinates>77.5946,12.9716,0 77.5946,12.9816,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Site A</name>
      <Polygon>
        <outerBoundaryIs><LinearRing>
          <coordinates>
            77.5946,12.9716,0
            77.6046,12.9716,0
            77.6046,12.9816,0
            77.5946,12.9816,0
            77.5946,12.9716,0
          </coordinates>
        </LinearRing></outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""


@pytest.fixture
def valid_kml_bytes() -> bytes:
    """Raw bytes of a valid KML file containing Point, LineString, Polygon."""
    return _SAMPLE_KML.encode("utf-8")


@pytest.fixture
def valid_kml_file(valid_kml_bytes) -> tuple[str, bytes, str]:
    """Tuple of (filename, content, content_type) for upload tests."""
    return ("sample.kml", valid_kml_bytes, "application/vnd.google-earth.kml+xml")


# ---------------------------------------------------------------------------
# Shapefile ZIP helpers
# ---------------------------------------------------------------------------


def _build_shapefile_zip(
    geometries: list,
    crs: str | None = "EPSG:4326",
    properties: list[dict] | None = None,
) -> bytes:
    """
    Build an in-memory ZIP containing a Shapefile with the given geometries.

    Args:
        geometries: List of Shapely geometries.
        crs: CRS string (e.g. "EPSG:4326") or None to omit .prj.
        properties: Optional list of property dicts aligned with geometries.

    Returns:
        ZIP bytes.
    """
    if properties is None:
        properties = [{"name": f"feature_{i}"} for i in range(len(geometries))]

    gdf = gpd.GeoDataFrame(properties, geometry=geometries, crs=crs)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shp_path = tmp_path / "test.shp"
        gdf.to_file(str(shp_path), driver="ESRI Shapefile", engine="pyogrio")

        # Collect all Shapefile component files
        shp_files = list(tmp_path.glob("test.*"))

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in shp_files:
                zf.write(f, arcname=f.name)
        return buf.getvalue()


def _build_shapefile_zip_no_crs(geometries: list) -> bytes:
    """Build a Shapefile ZIP omitting the .prj (CRS) file."""
    properties = [{"name": f"feature_{i}"} for i in range(len(geometries))]
    gdf = gpd.GeoDataFrame(properties, geometry=geometries, crs=None)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shp_path = tmp_path / "test.shp"
        # Write without CRS info
        gdf.to_file(str(shp_path), driver="ESRI Shapefile", engine="pyogrio")

        # Remove the .prj file to simulate missing CRS
        prj = tmp_path / "test.prj"
        if prj.exists():
            prj.unlink()

        shp_files = list(tmp_path.glob("test.*"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for f in shp_files:
                zf.write(f, arcname=f.name)
        return buf.getvalue()


@pytest.fixture
def polygon_zip_bytes() -> bytes:
    """Shapefile ZIP containing a single Polygon."""
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    return _build_shapefile_zip([poly], crs="EPSG:4326")


@pytest.fixture
def linestring_zip_bytes() -> bytes:
    """Shapefile ZIP containing a single LineString."""
    line = LineString([(0, 0), (1, 0)])
    return _build_shapefile_zip([line], crs="EPSG:4326")


@pytest.fixture
def multi_feature_zip_bytes() -> bytes:
    """Shapefile ZIP with multiple polygon features adhering to Shapefile homogeneity."""
    poly1 = Polygon(
        [
            (77.5946, 12.9716),
            (77.6046, 12.9716),
            (77.6046, 12.9816),
            (77.5946, 12.9816),
            (77.5946, 12.9716),
        ]
    )
    poly2 = Polygon(
        [
            (77.6100, 12.9716),
            (77.6200, 12.9716),
            (77.6200, 12.9816),
            (77.6100, 12.9816),
            (77.6100, 12.9716),
        ]
    )
    poly3 = Polygon(
        [
            (77.6300, 12.9716),
            (77.6400, 12.9716),
            (77.6400, 12.9816),
            (77.6300, 12.9816),
            (77.6300, 12.9716),
        ]
    )
    return _build_shapefile_zip(
        [poly1, poly2, poly3],
        crs="EPSG:4326",
        properties=[{"name": "site_1"}, {"name": "site_2"}, {"name": "site_3"}],
    )


@pytest.fixture
def multipolygon_zip_bytes() -> bytes:
    """Shapefile ZIP containing a MultiPolygon."""
    mp = MultiPolygon(
        [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
            Polygon([(2, 2), (3, 2), (3, 3), (2, 3), (2, 2)]),
        ]
    )
    return _build_shapefile_zip([mp], crs="EPSG:4326")


@pytest.fixture
def multilinestring_zip_bytes() -> bytes:
    """Shapefile ZIP containing a MultiLineString."""
    ml = MultiLineString(
        [
            [(0, 0), (1, 0)],
            [(2, 2), (3, 3)],
        ]
    )
    return _build_shapefile_zip([ml], crs="EPSG:4326")


@pytest.fixture
def projected_crs_zip_bytes() -> bytes:
    """Shapefile ZIP in a projected CRS (EPSG:32643 UTM 43N)."""
    # Bengaluru in UTM 43N metres
    poly = Polygon(
        [
            (770000, 1434000),
            (771000, 1434000),
            (771000, 1435000),
            (770000, 1435000),
            (770000, 1434000),
        ]
    )
    return _build_shapefile_zip([poly], crs="EPSG:32643")


@pytest.fixture
def missing_crs_zip_bytes() -> bytes:
    """Shapefile ZIP with no CRS information."""
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    return _build_shapefile_zip_no_crs([poly])


# ---------------------------------------------------------------------------
# Invalid / malformed file fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def corrupt_zip_bytes() -> bytes:
    """Bytes that look like a ZIP header but are corrupt."""
    return b"PK\x03\x04" + b"\x00" * 50 + b"garbage_data_here"


@pytest.fixture
def zip_without_shp_bytes() -> bytes:
    """A valid ZIP that contains only a text file (no .shp)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "This ZIP has no shapefile.")
    return buf.getvalue()


@pytest.fixture
def zip_slip_bytes() -> bytes:
    """A ZIP with a path traversal entry (Zip Slip attack)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.sh", "rm -rf /")
    return buf.getvalue()
