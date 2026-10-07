# Geospatial File Measurement API

[![CI](https://github.com/your-username/geospatial-file-measurement-api/actions/workflows/tests.yml/badge.svg)](https://github.com/your-username/geospatial-file-measurement-api/actions/workflows/tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)

## Overview

The Geospatial File Measurement API is a production-quality REST backend built with **FastAPI** that accepts geospatial files, processes their vector features, performs CRS-aware coordinate transformations, and returns accurate metric measurements (area in m², length in m).

The service accepts two industry-standard formats — **KML** (used by Google Earth and field survey tools) and **Shapefile ZIPs** (the ESRI format used by virtually every GIS platform). It handles the full spectrum of geometry types: Point, LineString, Polygon, and their Multi-variants, gracefully reporting unsupported types without crashing.

Every measurement is computed in a properly projected coordinate system. The API never calculates area or length directly from latitude/longitude degrees — doing so produces values that are geometrically meaningless. Instead, it automatically selects the optimal UTM zone for the dataset and reprojects before measuring, ensuring results are accurate regardless of where on Earth the data originates.

## Problem

Working engineers routinely need to answer basic spatial questions about uploaded survey files: _How large is this parcel? How long is this road? What CRS is this file in?_ Today, answering these questions requires a GIS desktop tool or custom scripting. This API exposes that capability as a clean HTTP interface that any application or workflow can consume.

Key pain points addressed:
- **Format fragmentation**: KML and Shapefile are both common but handled differently by every tool.
- **CRS confusion**: Files arrive in geographic (degrees) or projected (metres) coordinates, and silently computing on the wrong CRS produces silent errors.
- **Security gaps**: Naive Shapefile ZIP handling exposes applications to Zip Slip path traversal attacks.

## Features

- ✅ Upload KML files (Point, LineString, Polygon, Multi-variants)
- ✅ Upload Shapefile ZIPs (with Zip Slip / path traversal protection)
- ✅ Automatic CRS detection and UTM zone selection
- ✅ Accurate metric measurements (area m², length m) using projected CRS
- ✅ Full GeoJSON-compatible geometry responses
- ✅ Clean error responses (no stack traces exposed)
- ✅ Configurable via environment variables
- ✅ Production-ready Dockerfile (multi-stage, non-root user)
- ✅ OpenAPI / Swagger documentation at `/docs`
- ✅ Health check endpoint

## Tech Stack

| Technology | Version | Reason |
|---|---|---|
| **Python** | 3.12+ | Modern typing, pattern matching, performance |
| **FastAPI** | 0.115 | Async-native, automatic OpenAPI docs, Pydantic integration |
| **Uvicorn** | 0.32 | ASGI server; minimal overhead |
| **Pydantic v2** | 2.10 | Schema validation, settings management, JSON serialisation |
| **GeoPandas** | 1.0 | High-level geospatial DataFrame operations |
| **Shapely** | 2.0 | Geometry objects, area/length computation |
| **PyProj** | 3.7 | CRS definitions and coordinate transformations |
| **Pyogrio** | 0.13+ | High-performance vector file I/O with bundled GDAL (KML, Shapefile) |
| **Pytest** | 8.3 | Test framework with fixtures and parametrize |
| **Ruff** | 0.8 | Extremely fast linter (replaces flake8 + isort) |
| **Black** | 24.10 | Opinionated code formatter |
| **Docker** | — | Reproducible builds, easy deployment |

## Architecture

```
Client (HTTP)
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                     FastAPI App                         │
│  POST /api/files/   GET /api/files/{id}/                │
│  GET /api/files/{id}/measurements/   GET /health        │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────▼────────┐
        │   Validation    │  ← extension, size, content signature
        └────────┬────────┘    Zip Slip detection
                 │
        ┌────────▼────────┐
        │  File Storage   │  ← UUID-named files in UPLOAD_DIR
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │  File Service   │  ← orchestration layer
        │  (file_service) │
        └────────┬────────┘
           ┌─────┴──────┐
           │            │
    ┌──────▼───┐  ┌────────▼─────┐
    │   KML    │  │  Shapefile   │
    │  Loader  │  │  ZIP Loader  │
    │(Pyogrio) │  │  (Pyogrio)   │
    └──────┬───┘  └────────┬─────┘
           └─────┬───────┘
                 │
        ┌────────▼────────┐
        │   CRS Service   │  ← detect CRS → select UTM → reproject
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │  Geometry Svc   │  ← iterate rows, sanitise properties
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │ Measurement Svc │  ← area (m²) / length (m) on projected geom
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │  Metadata Store │  ← in-memory dict (UUID → metadata + features)
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │  JSON Response  │  ← Pydantic serialisation
        └─────────────────┘
```

## Project Structure

```
geospatial-file-measurement-api/
│
├── app/                        ← Application package
│   ├── main.py                 ← FastAPI app factory, startup, exception handlers
│   ├── config.py               ← Pydantic Settings (env vars / .env)
│   │
│   ├── api/routes/
│   │   └── files.py            ← POST /api/files/, GET /api/files/{id}/, measurements
│   │
│   ├── schemas/
│   │   └── file.py             ← Pydantic request/response models
│   │
│   ├── services/
│   │   ├── file_service.py     ← Upload pipeline + in-memory metadata store
│   │   ├── geometry_service.py ← Feature extraction, property sanitisation
│   │   ├── measurement_service.py ← area / length calculation
│   │   └── crs_service.py      ← CRS detection, UTM selection, reprojection
│   │
│   └── utils/
│       ├── validation.py       ← Extension, size, content, Zip Slip checks
│       └── logging.py          ← Structured logging setup
│
├── tests/                      ← pytest test suite
│   ├── conftest.py             ← Fixtures (programmatic test data, client)
│   ├── test_upload.py          ← Upload endpoint tests
│   ├── test_file_info.py       ← File info endpoint tests
│   ├── test_measurements.py    ← Measurement service unit tests
│   ├── test_api_measurements.py ← Measurements API integration tests
│   ├── test_crs.py             ← CRS service unit + integration tests
│   └── test_validation.py      ← Validation utility tests
│
├── sample_data/
│   ├── sample.kml              ← Point + LineString + Polygon (EPSG:4326)
│   └── README.md
│
├── uploads/                    ← Runtime upload directory
│   └── .gitkeep
│
├── .github/workflows/
│   └── tests.yml               ← GitHub Actions CI (lint + test)
│
├── .env.example                ← Environment variable template
├── .gitignore
├── .dockerignore
├── Dockerfile                  ← Multi-stage production image
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml              ← Ruff + Black + pytest configuration
└── README.md
```

## Installation

### Prerequisites

- Python 3.12+
- pip
- System geospatial libraries (Linux/macOS) or Docker (any OS)

### Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-username/geospatial-file-measurement-api.git
cd geospatial-file-measurement-api

# 2. Create a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

> **Linux / macOS only**: You may need system geospatial libraries:
> ```bash
> # Ubuntu / Debian
> sudo apt-get install gdal-bin libgdal-dev libproj-dev libgeos-dev
>
> # macOS (Homebrew)
> brew install gdal proj geos
> ```

### Environment Configuration

```bash
# Copy the example file
cp .env.example .env

# Edit as needed (defaults are suitable for local development)
# UPLOAD_DIR=uploads
# MAX_UPLOAD_SIZE_MB=50
# LOG_LEVEL=INFO
```

## Run

### Development server (with auto-reload)

```bash
uvicorn app.main:app --reload
```

The API will be available at: `http://localhost:8000`

### Production server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Docker

### Build and run

```bash
# Build
docker build -t geospatial-api .

# Run
docker run -p 8000:8000 geospatial-api

# Run with custom settings
docker run -p 8000:8000 \
  -e MAX_UPLOAD_SIZE_MB=100 \
  -e LOG_LEVEL=DEBUG \
  -v $(pwd)/uploads:/app/uploads \
  geospatial-api
```

### Docker Compose (recommended)

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop
docker-compose down
```

## API Documentation

Interactive documentation is auto-generated by FastAPI:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

### `GET /health`

Liveness probe.

```json
{"status": "ok"}
```

---

### `POST /api/files/`

Upload a geospatial file for processing.

**Request** — `multipart/form-data`:
```
file: <binary file content>
```

**Accepted formats**: `.kml`, `.zip` (containing a Shapefile)

**Response** `201 Created`:
```json
{
  "id": "a3f1b2c4-...",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

**Error responses**:
| Status | Reason |
|---|---|
| `400` | Invalid extension, corrupt file, ZIP without SHP, Zip Slip, file too large |
| `422` | Malformed multipart request |
| `500` | Unexpected processing error |

---

### `GET /api/files/{id}/`

Retrieve file metadata by ID.

**Response** `200 OK`:
```json
{
  "id": "a3f1b2c4-...",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

**Error**: `404 Not Found` if `id` doesn't exist.

---

### `GET /api/files/{id}/measurements/`

Retrieve feature-level measurements.

**Response** `200 OK`:
```json
{
  "file_id": "a3f1b2c4-...",
  "filename": "survey.kml",
  "crs": "EPSG:4326",
  "features": [
    {
      "feature_id": 0,
      "geometry_type": "Point",
      "geometry": {"type": "Point", "coordinates": [77.5946, 12.9716, 0.0]},
      "properties": {"name": "Tower"},
      "crs": "EPSG:4326",
      "measurement": null,
      "measurement_note": null
    },
    {
      "feature_id": 1,
      "geometry_type": "LineString",
      "geometry": {"type": "LineString", "coordinates": [[77.5946, 12.9716, 0.0], [77.5946, 12.9816, 0.0]]},
      "properties": {"name": "Road"},
      "crs": "EPSG:4326",
      "measurement": {"length": 1111.95, "unit": "m"},
      "measurement_note": null
    },
    {
      "feature_id": 2,
      "geometry_type": "Polygon",
      "geometry": {"type": "Polygon", "coordinates": [[[77.5946, 12.9716, 0.0], ...]]},
      "properties": {"name": "Site A"},
      "crs": "EPSG:4326",
      "measurement": {"area": 1234567.89, "unit": "m²"},
      "measurement_note": null
    }
  ]
}
```

## CRS Handling

**CRS** (Coordinate Reference System) defines how coordinates map to locations on Earth.

### Geographic vs. Projected

| Type | Example | Units | Suitable for measurement? |
|---|---|---|---|
| Geographic | EPSG:4326 (WGS 84) | Degrees | ❌ No |
| Projected | EPSG:32643 (UTM 43N) | Metres | ✅ Yes |

Computing `geometry.area` or `geometry.length` on EPSG:4326 coordinates returns values in **degrees²** or **degrees** — which are not meaningful physical measurements.

### UTM Zone Selection

The API uses the dataset centroid to automatically select the optimal UTM zone:

```
zone = int((longitude + 180) / 6) + 1

Northern hemisphere:  EPSG = 32600 + zone
Southern hemisphere:  EPSG = 32700 + zone
```

Examples:
| Location | Lon | Lat | UTM Zone | EPSG |
|---|---|---|---|---|
| Bengaluru, India | 77.59 | 12.97 | 43N | 32643 |
| London, UK | -0.12 | 51.50 | 30N | 32630 |
| New York, USA | -73.93 | 40.73 | 18N | 32618 |
| Sydney, Australia | 151.21 | -33.87 | 56S | 32756 |

### Missing CRS

If a file has no CRS information, the API:
1. Processes and returns the file (status `COMPLETED`)
2. Reports `"crs": null` in metadata
3. Returns `"measurement": null` for all features
4. Includes a `"measurement_note"` explaining why

We **never silently assume EPSG:4326** — geographic interpretation without a known datum is ambiguous and leads to silent measurement errors.

### Already-Projected CRS

If the input file is already in a projected CRS with metre units (e.g. EPSG:32643, EPSG:27700), we use it directly without reprojection. This avoids unnecessary transformation noise.

## Measurement Strategy

| Geometry Type | Measurement | Unit |
|---|---|---|
| Point | None (null) | — |
| MultiPoint | None (null) | — |
| LineString | length | m |
| MultiLineString | total length | m |
| Polygon | area | m² |
| MultiPolygon | total area | m² |
| GeometryCollection | None (null + note) | — |

Measurements are computed on the projected geometry and rounded to **2 decimal places** in the API response.

## Error Handling

| Status | Trigger | Response |
|---|---|---|
| `400` | Bad extension / corrupt file / no SHP in ZIP | `{"detail": "..."}` |
| `404` | Unknown file ID | `{"detail": "File not found."}` |
| `422` | Malformed request | FastAPI validation error |
| `500` | Unexpected error | `{"detail": "An unexpected internal server error occurred."}` |

Python stack traces are **never** returned to API callers. Full error details are logged server-side.

## Security

| Threat | Mitigation |
|---|---|
| Arbitrary file uploads | Extension whitelist (`.kml`, `.zip` only) |
| Content spoofing | Byte-level magic-number validation |
| Oversized uploads | Configurable `MAX_UPLOAD_SIZE_MB` limit |
| Zip Slip / path traversal | Every ZIP member is checked for `..` and absolute paths before extraction |
| Stack trace leakage | Global exception handler returns only generic messages |
| Privilege escalation | Docker container runs as non-root user (UID 1001) |

## Testing

```bash
# Run all tests
pytest

# Verbose output with short tracebacks
pytest -v --tb=short

# Run a specific test file
pytest tests/test_crs.py -v

# Run a specific test class
pytest tests/test_validation.py::TestZipContentValidation -v
```

Tests use **programmatically generated** geospatial fixtures (via GeoPandas + Shapely) — no binary test files are committed. Every test runs in an isolated temporary upload directory.

### Test Coverage

| Test File | What it covers |
|---|---|
| `test_upload.py` | Upload endpoint, extension/size/content validation, ZipSlip, schema |
| `test_file_info.py` | File info endpoint, 404, health check |
| `test_measurements.py` | Measurement service units (area, length, null, unsupported, JSON) |
| `test_api_measurements.py` | Measurements API integration (metric values, GeoJSON, CRS, missing CRS) |
| `test_crs.py` | UTM zone selection (parametrized cities), CRS detection, projection sanity |
| `test_validation.py` | All validation functions (extension, size, KML sig, ZIP, ZipSlip) |

## Storage

**Current implementation**: Local filesystem with UUID-named files.

Architecture decisions that make migration straightforward:

| Component | Current | Future |
|---|---|---|
| File storage | `uploads/<uuid>.<ext>` | S3 / GCS / Azure Blob |
| Metadata store | In-memory dict | PostgreSQL / PostGIS |
| Feature store | Same dict | PostGIS geometry tables |

The upload and retrieval logic is isolated in `file_service.py`. Swapping `_save_file()` for an S3 `put_object()` call and `_metadata_store` for SQLAlchemy ORM calls requires changes in exactly one file.

## Design Decisions

### Why FastAPI?
FastAPI gives us automatic OpenAPI documentation, async support, and Pydantic v2 integration out of the box. For an API-first geospatial service, the self-documenting nature is particularly valuable — consumers can explore the API at `/docs` without reading external documentation.

### Why GeoPandas + Pyogrio?
GeoPandas provides a high-level DataFrame interface over geospatial data, making it easy to iterate features, handle CRS, and batch-process geometry. Pyogrio serves as the underlying vector I/O engine:
- **High performance**: Built on GDAL C API and Apache Arrow, reading files up to 5-10x faster than legacy backends.
- **Self-contained binaries**: Bundles GDAL, PROJ, and GEOS in standard wheel distributions, avoiding manual C++ compilation or external system library installations across platforms (Windows, Linux, macOS).
- **Multi-format support**: Provides full driver support for KML, LIBKML, and ESRI Shapefiles out of the box.

### Why PyProj?
PyProj wraps the PROJ library and is the de facto standard for coordinate transformations in Python. It integrates directly with GeoPandas' `to_crs()` method, making reprojection a single line.

### Why UTM-based projection?
UTM (Universal Transverse Mercator) provides excellent metric accuracy within each 6° longitude zone. For single-site survey files — the primary use case here — UTM error is well under 0.1%. It's also deterministic: any point on Earth maps to exactly one UTM zone, making the selection algorithm simple and testable.

### Why local storage?
For an internship assignment, a database adds complexity without value. The in-memory + local-file approach is simple, fast, and the service layer is explicitly designed for future migration (see Storage section).

### Why not EPSG:3857 (Web Mercator)?
Web Mercator preserves shape but significantly distorts area at latitudes away from the equator. UTM is the correct choice for accurate area and length measurements.

## Learning

Building this project involved working through several layers of geospatial engineering that aren't obvious from a Python/web background:

**CRS and coordinate systems** were the biggest learning curve. Understanding the difference between a geographic CRS (a model of Earth's shape) and a projected CRS (a flat-map projection) — and why you cannot compute Euclidean distance on spherical coordinates — required reading through PROJ documentation and experimenting with concrete values. Seeing `geometry.area` return `0.0001` on EPSG:4326 data vs `1,234,000` on UTM data was a real "aha" moment.

**GeoPandas & Pyogrio layer model**: KML files can contain multiple layers (Placemarks, folders, etc.). Pyogrio exposes these via `pyogrio.list_layers()`, allowing the service to reliably discover and concatenate all layers into a single GeoDataFrame rather than silently reading only the first layer.

**FastAPI + Pydantic v2**: Pydantic v2's breaking changes from v1 (`.dict()` → `.model_dump()`, schema generation changes) required careful attention. Using discriminated unions for the `measurement` field (which is either an AreaMeasurement, LengthMeasurement, or None) was an interesting schema design challenge.

**Secure file handling**: Zip Slip is a real vulnerability where `../../` paths in ZIP entries can overwrite arbitrary files. Implementing the two-pass defence (member path check + resolved-path containment check) required understanding how `pathlib.Path.resolve()` works on Windows vs Linux.

## Future Scope

- **Background processing**: Move file processing to Celery/RQ workers with a job queue, returning a job ID immediately and polling for results. This unblocks long-running large file processing.
- **PostGIS storage**: Store extracted features in a PostGIS-enabled PostgreSQL database for spatial queries (intersections, buffer, nearest-neighbour).
- **Cloud object storage**: Replace local file storage with S3-compatible storage for horizontal scalability and durability.
- **Authentication**: API key or OAuth2 authentication for multi-tenant deployments.
- **Large file streaming**: Stream uploads in chunks rather than reading the entire file into memory.
- **Spatial indexing**: R-tree indexing via Shapely's STRtree for fast bounding-box queries over large datasets.
- **Cloud deployment**: Kubernetes/Cloud Run deployment with auto-scaling, readiness probes, and Prometheus metrics.
- **Monitoring**: Structured JSON logging with correlation IDs, Prometheus metrics, and OpenTelemetry tracing.
- **Additional formats**: GeoJSON, GeoPackage (.gpkg), CSV with lat/lon columns.
