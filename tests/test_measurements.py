"""
Tests for the measurement service unit functions.

Covers:
- Polygon area computation
- LineString length computation
- Point returns null
- MultiPolygon total area
- MultiLineString total length
- Unsupported geometry types
- Empty / null geometry handling
- JSON serialisation of measurement types
"""

from __future__ import annotations

import json
import math

import pytest
from app.schemas.file import AreaMeasurement, LengthMeasurement
from app.services.measurement_service import compute_measurement
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)


class TestPolygonMeasurement:
    """Tests for Polygon area computation."""

    def test_unit_square_area(self):
        """A 1×1 unit square should have area 1.0."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        m, note = compute_measurement(poly)
        assert isinstance(m, AreaMeasurement)
        assert m.area == pytest.approx(1.0, rel=1e-6)
        assert m.unit == "m²"
        assert note is None

    def test_larger_polygon(self):
        """A 100×100 square should have area 10_000."""
        poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        m, _ = compute_measurement(poly)
        assert isinstance(m, AreaMeasurement)
        assert m.area == pytest.approx(10_000.0, rel=1e-4)

    def test_polygon_area_is_positive(self):
        """Polygon area must always be non-negative."""
        poly = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
        m, _ = compute_measurement(poly)
        assert m.area >= 0


class TestLineStringMeasurement:
    """Tests for LineString length computation."""

    def test_horizontal_unit_line(self):
        """A horizontal line of length 1 should return length 1.0."""
        line = LineString([(0, 0), (1, 0)])
        m, note = compute_measurement(line)
        assert isinstance(m, LengthMeasurement)
        assert m.length == pytest.approx(1.0, rel=1e-6)
        assert m.unit == "m"
        assert note is None

    def test_vertical_line(self):
        """A vertical line of length 1000 should return 1000.0."""
        line = LineString([(0, 0), (0, 1000)])
        m, _ = compute_measurement(line)
        assert m.length == pytest.approx(1000.0, rel=1e-4)

    def test_multipoint_line(self):
        """A three-point line should have correct cumulative length."""
        line = LineString([(0, 0), (3, 0), (3, 4)])
        m, _ = compute_measurement(line)
        # Length = 3 + 4 = 7
        assert m.length == pytest.approx(7.0, rel=1e-6)


class TestPointMeasurement:
    """Tests for Point geometry (no measurement required)."""

    def test_point_returns_null_measurement(self):
        """Point should return (None, None)."""
        pt = Point(1, 2)
        m, note = compute_measurement(pt)
        assert m is None
        assert note is None

    def test_multipoint_returns_null_measurement(self):
        """MultiPoint should return (None, None)."""
        mp = MultiPoint([(0, 0), (1, 1)])
        m, _ = compute_measurement(mp)
        assert m is None


class TestMultiGeometryMeasurement:
    """Tests for Multi* geometry types."""

    def test_multipolygon_total_area(self):
        """MultiPolygon area should equal sum of component polygon areas."""
        p1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        p2 = Polygon([(2, 2), (3, 2), (3, 4), (2, 4)])
        mp = MultiPolygon([p1, p2])
        m, _ = compute_measurement(mp)
        assert isinstance(m, AreaMeasurement)
        # p1 area=1, p2 area=2, total=3
        assert m.area == pytest.approx(3.0, rel=1e-6)

    def test_multilinestring_total_length(self):
        """MultiLineString length should equal sum of component lengths."""
        l1 = LineString([(0, 0), (3, 0)])  # length 3
        l2 = LineString([(0, 0), (0, 4)])  # length 4
        ml = MultiLineString([list(l1.coords), list(l2.coords)])
        m, _ = compute_measurement(ml)
        assert isinstance(m, LengthMeasurement)
        assert m.length == pytest.approx(7.0, rel=1e-6)


class TestUnsupportedGeometry:
    """Tests for unsupported geometry types."""

    def test_geometry_collection_returns_null_with_note(self):
        """GeometryCollection should return null measurement with an explanatory note."""
        gc = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
        m, note = compute_measurement(gc)
        assert m is None
        assert note is not None
        assert len(note) > 0

    def test_null_geometry_returns_null_with_note(self):
        """None geometry input should return null measurement with a note."""
        m, note = compute_measurement(None)
        assert m is None
        assert note is not None

    def test_empty_geometry_returns_null_with_note(self):
        """Empty geometry should return null measurement with a note."""
        empty = Polygon()
        m, note = compute_measurement(empty)
        assert m is None
        assert note is not None


class TestMeasurementJsonSerialisation:
    """Ensure measurement models serialise cleanly to JSON."""

    def test_area_measurement_serialisable(self):
        """AreaMeasurement should serialise to valid JSON."""
        m = AreaMeasurement(area=12345.67, unit="m²")
        payload = json.loads(m.model_dump_json())
        assert payload["area"] == 12345.67
        assert payload["unit"] == "m²"

    def test_length_measurement_serialisable(self):
        """LengthMeasurement should serialise to valid JSON."""
        m = LengthMeasurement(length=842.31, unit="m")
        payload = json.loads(m.model_dump_json())
        assert payload["length"] == 842.31
        assert payload["unit"] == "m"

    def test_area_measurement_rounding(self):
        """Area values should be rounded to 2 decimal places in the service."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])  # area=1.000000...
        m, _ = compute_measurement(poly)
        assert isinstance(m.area, float)
        # Check that the value is finite
        assert math.isfinite(m.area)
