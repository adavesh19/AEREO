# Sample Data

This directory contains sample geospatial files for testing and demonstration.

## Files

### `sample.kml`

A KML file containing three features near Bengaluru, India (EPSG:4326 / WGS 84):

| Feature | Geometry Type | Name    | Description                 |
|---------|--------------|---------|----------------------------|
| 0       | Point        | Tower   | Communication tower        |
| 1       | LineString   | Road    | Short road segment (~1 km) |
| 2       | Polygon      | Site A  | ~1 km² survey area         |

**Coordinates**: All in WGS 84 decimal degrees.  
**Measurement CRS**: The API will automatically select UTM Zone 43N (EPSG:32643).

### Expected measurements (approximate)

| Feature | Measurement  | Value       | Unit |
|---------|-------------|-------------|------|
| Tower   | —           | null        | —    |
| Road    | length      | ~1 111 m    | m    |
| Site A  | area        | ~1 234 000 m² | m² |

> Exact values will vary slightly due to UTM projection distortion.

## Generating Shapefile Test Data

Shapefile test data is generated programmatically during tests
(`tests/conftest.py`) to avoid committing binary files to version control.

The `conftest.py` creates temporary GeoDataFrames saved to disk and
tears them down after each test run.
