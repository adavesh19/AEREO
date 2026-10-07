# AEREO - Geospatial File Measurement API

## Overview

This project was built as part of the Aereo Software Development Engineer internship assignment. 

The goal was to solve a practical backend problem: take geospatial survey files uploaded by users, parse their features, handle Coordinate Reference Systems (CRS) properly, and return verified area and length measurements through a clean REST API. 

The service accepts KML files and ZIP archives containing Shapefiles, inspects their vector geometries, transforms geographic coordinates into appropriate metric projections, and returns structured JSON and GeoJSON-compatible responses using FastAPI.

## What I Built

Here is what is implemented in the service:

- **FastAPI backend**: Clean, typed REST endpoints with automatic OpenAPI documentation and structured error handling.
- **KML & Shapefile ZIP uploads**: Handlers for single `.kml` files and `.zip` archives containing the required Shapefile components.
- **Pyogrio-based vector file processing**: Vector I/O powered by Pyogrio and GDAL drivers for reliable layer reading.
- **GeoPandas & Shapely integration**: High-level geospatial DataFrame operations and geometry manipulations.
- **PyProj coordinate transformations**: Accurate transformations between geographic and projected coordinate reference systems.
- **CRS-aware measurement engine**: Automatic detection of input CRS, centroid-based UTM zone calculation, and metric planar measurements.
- **Polygon area**: Calculated in square metres ($m^2$) for Polygon and MultiPolygon geometries.
- **LineString length**: Calculated in metres ($m$) for LineString and MultiLineString geometries.
- **Point handling**: Correctly handled without measurements ($null$) since points have no length or area.
- **GeoJSON-compatible responses**: Feature geometries returned as standard GeoJSON objects alongside attributes and measurements.
- **Multi-layer validation**: File extension allowlists, byte-level signature checks, and upload size enforcement.
- **Secure ZIP extraction**: Defensive path validation protecting against Zip Slip and Windows-style path traversal attacks.
- **Automated test suite**: 123 automated unit and integration tests covering API endpoints, CRS selection, measurements, and security.
- **Docker containerization**: Multi-stage Dockerfile and Docker Compose configuration running as an unprivileged non-root user.

## Why FastAPI

I chose FastAPI for this service for several practical engineering reasons:

- **Clean API design**: Modern Python type annotations keep route definitions concise and readable.
- **Type-safe request/response models**: Pydantic v2 schemas ensure strict validation on both incoming uploads and outgoing responses.
- **Automatic Swagger documentation**: Interactive API exploration is available out of the box at `/docs`, which makes testing endpoints straightforward.
- **Easy testing**: FastAPI's `TestClient` integrates cleanly with `pytest`, allowing fast in-memory execution of the full request/response lifecycle.
- **Good fit for a backend assignment**: It provides production-ready structure without the heavy boilerplate of Django or the manual wiring required in Flask.

## Architecture

```
Client
  |
  v
FastAPI
  |
  +--> Validation
  |
  +--> File Processing
  |
  +--> GeoPandas / Pyogrio
  |
  +--> CRS Transformation
  |
  +--> Measurement Engine
  |
  +--> JSON / GeoJSON Response
```

### Request Flow

1. **Client Request**: The client uploads a `.kml` or `.zip` file via `POST /api/files/`.
2. **Validation**: The upload is verified for file extension, configured size limit, and file signature. ZIP files are inspected to ensure valid Shapefile components and to prevent path traversal attacks.
3. **Storage & Ingestion**: The file is stored locally using a unique UUID and loaded into a GeoPandas `GeoDataFrame` using Pyogrio.
4. **CRS Transformation**: The service inspects the dataset's CRS. If geographic (such as WGS 84 / EPSG:4326), it calculates the dataset centroid and reprojects the geometries into the corresponding metric UTM zone.
5. **Measurement Engine**: The service computes planar measurements on the projected geometries (area in $m^2$, length in $m$).
6. **Response Generation**: The metadata and feature-level measurements are formatted according to Pydantic schemas and returned to the client as JSON.

## Project Structure

```
geospatial-file-measurement-api/
├── app/
│   ├── main.py                 # FastAPI application factory and error handlers
│   ├── config.py               # Pydantic Settings (environment configuration)
│   ├── api/routes/files.py     # API route handlers for uploads, status, and measurements
│   ├── schemas/file.py         # Request and response models (Pydantic v2)
│   ├── services/
│   │   ├── file_service.py     # Upload orchestration and metadata storage
│   │   ├── crs_service.py      # CRS detection, UTM zone determination, reprojection
│   │   ├── geometry_service.py # Feature iteration and GeoJSON formatting
│   │   └── measurement_service.py # Metric planar area and length calculation
│   └── utils/
│       ├── validation.py       # File extension, size, signature, and Zip Slip checks
│       └── logging.py          # Structured application logging
├── tests/                      # 123 automated pytest test cases
│   ├── conftest.py             # Reusable test fixtures and mock geospatial data
│   ├── test_upload.py          # Upload endpoint validation and error tests
│   ├── test_file_info.py       # File status and health check tests
│   ├── test_measurements.py    # Unit tests for geometry measurements
│   ├── test_api_measurements.py # Integration tests for measurement endpoints
│   ├── test_crs.py             # CRS selection and reprojection tests
│   └── test_validation.py      # File validation and security checks
├── sample_data/
│   └── sample.kml              # Sample KML with Point, LineString, and Polygon
├── Dockerfile                  # Multi-stage production container definition
├── docker-compose.yml          # Container configuration with volume persistence
├── pyproject.toml              # Tooling configuration for pytest, ruff, and black
└── requirements.txt            # Python dependencies
```

## Supported Files

The API supports vector datasets in the following formats:

1. **KML (`.kml`)**: Standard Keyhole Markup Language files containing Placemarks with Point, LineString, Polygon, MultiLineString, or MultiPolygon geometries.
2. **Shapefile ZIP (`.zip`)**: A ZIP archive containing an ESRI Shapefile dataset. The archive must include the required components:
   - `.shp`: Geometry data
   - `.shx`: Shape index format
   - `.dbf`: Attribute format
   - `.prj`: Coordinate system description (recommended for automatic CRS detection)

## API

### Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health and liveness probe |
| `POST` | `/api/files/` | Upload a KML file or Shapefile ZIP archive |
| `GET` | `/api/files/{id}/` | Retrieve file processing status and basic metadata |
| `GET` | `/api/files/{id}/measurements/` | Retrieve detailed feature geometries, attributes, and measurements |

---

### `GET /health`

**Response (`200 OK`)**:
```json
{
  "status": "ok"
}
```

---

### `POST /api/files/`

Uploads and processes a geospatial file (`multipart/form-data`).

**Example Request**:
```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -F "file=@sample_data/sample.kml"
```

**Example Response (`201 Created`)**:
```json
{
  "id": "656e9dab-c98a-499a-b199-2ebf9299ce74",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

---

### `GET /api/files/{id}/`

Retrieves metadata and processing state for a previously uploaded file.

**Example Response (`200 OK`)**:
```json
{
  "id": "656e9dab-c98a-499a-b199-2ebf9299ce74",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

---

### `GET /api/files/{id}/measurements/`

Returns the full list of features with their GeoJSON geometry, properties, original CRS, and calculated metric measurements.

**Example Response (`200 OK`)**:
```json
{
  "file_id": "656e9dab-c98a-499a-b199-2ebf9299ce74",
  "filename": "sample.kml",
  "crs": "EPSG:4326",
  "features": [
    {
      "feature_id": 0,
      "geometry_type": "Point",
      "geometry": {
        "type": "Point",
        "coordinates": [77.5946, 12.9716, 0.0]
      },
      "properties": {
        "Name": "Tower",
        "description": "A communication tower in Bengaluru"
      },
      "crs": "EPSG:4326",
      "measurement": null,
      "measurement_note": null
    },
    {
      "feature_id": 1,
      "geometry_type": "LineString",
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [77.5946, 12.9716, 0.0],
          [77.5946, 12.9816, 0.0]
        ]
      },
      "properties": {
        "Name": "Road",
        "description": "A short road segment in Bengaluru"
      },
      "crs": "EPSG:4326",
      "measurement": {
        "length": 1106.94,
        "unit": "m"
      },
      "measurement_note": null
    },
    {
      "feature_id": 2,
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [77.5946, 12.9716, 0.0],
            [77.6046, 12.9716, 0.0],
            [77.6046, 12.9816, 0.0],
            [77.5946, 12.9816, 0.0],
            [77.5946, 12.9716, 0.0]
          ]
        ]
      },
      "properties": {
        "Name": "Site A",
        "description": "A survey polygon near Bengaluru"
      },
      "crs": "EPSG:4326",
      "measurement": {
        "area": 1201684.72,
        "unit": "m²"
      },
      "measurement_note": null
    }
  ]
}
```

## CRS Handling

Correctly managing Coordinate Reference Systems is one of the most critical aspects of geospatial software development:

- **Angular vs. Planar Coordinates**: Latitude and longitude (such as EPSG:4326) are angular measurements expressed in decimal degrees on an ellipsoidal Earth. Calculating Euclidean distances or polygon areas directly on degree coordinates produces values that are geometrically meaningless (e.g. area in square degrees).
- **UTM Zone Selection**: When a dataset is provided in a geographic CRS, the application computes the centroid longitude and latitude of the dataset and determines the appropriate Universal Transverse Mercator (UTM) zone:
  $$\text{UTM Zone} = \left\lfloor \frac{\text{longitude} + 180}{6} \right\rfloor + 1$$
  The zone number is strictly clamped to the valid range $[1, 60]$.
- **Hemisphere Mapping**:
  - Northern hemisphere ($\text{latitude} \ge 0$): `EPSG:326xx` (e.g. `EPSG:32643` for Bengaluru, India)
  - Southern hemisphere ($\text{latitude} < 0$): `EPSG:327xx` (e.g. `EPSG:32756` for Sydney, Australia)
- **Preserving Projected CRS**: If the uploaded dataset is already defined in an appropriate projected metric CRS (such as State Plane or a local UTM projection), the service preserves that coordinate system rather than forcing a redundant reprojection.
- **Handling Missing CRS**: If a file has no CRS information, the API does not assume `EPSG:4326`. Guessing a coordinate system can lead to silent measurement errors. Instead, the service processes the file, records `"crs": null`, returns `"measurement": null` for all features, and attaches a descriptive `measurement_note` explaining that a valid CRS is required for measurement.
- **Measurement Methodology**: All computations are performed as a **projected planar measurement** in metres or square metres on reprojected Cartesian coordinates.

## Measurement Logic

Measurements are computed based on the geometry type after projecting geographic features into a metric coordinate system:

- **Point / MultiPoint**: No measurement required (`measurement: null`, `measurement_note: null`). Points represent discrete spatial coordinates and do not have length or area.
- **LineString**: Measured as planar length in metres ($m$).
- **MultiLineString**: Measured as the combined total length of all line components in metres ($m$).
- **Polygon**: Measured as planar area in square metres ($m^2$).
- **MultiPolygon**: Measured as the combined total area of all polygon parts in square metres ($m^2$).
- **GeometryCollection / Unsupported Types**: Returned with `measurement: null` and an explanatory `measurement_note`.

All calculated measurements are rounded to 2 decimal places for clean, consistent API output.

## Security

Handling user-uploaded archives and vector files requires defensive backend programming:

- **Upload Size Limit**: Configured through `MAX_UPLOAD_SIZE_MB` (defaults to 50 MB) to prevent denial-of-service from oversized uploads.
- **Extension Allowlist**: Strict check allowing only `.kml` and `.zip` extensions.
- **Content Validation**: Byte-level header validation to confirm that files match expected XML or PK-ZIP magic numbers, preventing renamed binary uploads.
- **ZIP File Verification**: Uploaded archives are inspected to confirm they contain valid Shapefile components (`.shp`, `.shx`, `.dbf`).
- **Zip Slip & Path Traversal Protection**: Every archive entry is inspected before extraction. The extractor rejects paths with `..`, absolute paths, Windows drive letters (`C:`), or paths that resolve outside the designated destination folder.
- **Safe Extraction**: Files are extracted into isolated, temporary directories created per request.
- **Sanitized API Errors**: Generic error messages are returned to callers on internal errors to prevent internal stack traces or server paths from leaking.
- **Non-Root Docker Execution**: The Docker container creates and runs under an unprivileged user (`appuser`, UID 1001).

## Why Pyogrio Instead of Fiona

During the implementation, I chose **Pyogrio** as the vector file I/O engine for GeoPandas:

- **Independent Vector Engine**: Pyogrio provides direct Python bindings to the GDAL C API and integrates natively with GeoPandas (`gpd.options.io_engine = "pyogrio"`).
- **Cleaner Deployment**: Fiona often requires separately compiled system GDAL libraries that can introduce complex C-dependency conflicts across development and container environments. Pyogrio wheels provide self-contained GDAL binaries for standard platforms.
- **Performance**: Pyogrio reads vector datasets via Apache Arrow memory structures, significantly reducing read latency for multi-feature datasets.
- This was an intentional architecture choice for this project to ensure consistent, stable builds across local Windows development and Linux Docker containers without sacrificing GDAL format support.

## Testing

The codebase includes an extensive test suite built with `pytest`:

```
======================= 123 passed, 3 warnings in 4.01s =======================
```

The test suite covers:
- **API Integration Tests**: Testing upload workflows, metadata retrieval, and measurement endpoints with `TestClient`.
- **CRS Tests**: Testing UTM zone selection logic, hemisphere boundary conditions, already-projected coordinate systems, and missing CRS handling.
- **Measurement Tests**: Unit tests verifying area and length formulas against known geometric shapes (unit squares, lines, multipart geometries).
- **Upload Validation Tests**: Testing file size boundaries, extension allowlists, and corrupt file signatures.
- **Security Tests**: Dedicated tests verifying that malicious ZIP archives (Zip Slip, directory traversal, drive letter absolute paths) are rejected before extraction.

## Docker

Docker support was verified locally with Docker Desktop 29.8.2.

### Build the Image

```bash
docker build -t aereo-geospatial-api .
```

### Run the Container

```bash
docker run --rm -d --name aereo-api -p 8000:8000 aereo-geospatial-api
```

### Health Check

```bash
curl http://127.0.0.1:8000/health
# Output: {"status":"ok"}
```

### API Verification Against Container

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" -F "file=@sample_data/sample.kml"
# Output: {"id":"656e9dab-c98a-499a-b199-2ebf9299ce74","filename":"sample.kml","feature_count":3,"crs":"EPSG:4326","status":"COMPLETED"}
```

### Stop the Container

```bash
docker stop aereo-api
```

### Docker Compose

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/health
docker compose down
```

## Design Decisions

- **FastAPI**: Chosen for its fast asynchronous handling, automatic OpenAPI schema generation, and straightforward Pydantic models.
- **Pyogrio**: Chosen to read both KML and Shapefile files reliably using bundled GDAL drivers without external system library headaches.
- **GeoPandas & Shapely**: Used as the primary data abstraction for vector features and geometric operations.
- **PyProj**: Used for coordinate transformations, ensuring mathematically accurate reprojections to metric systems.
- **UTM Selection**: Centroid-based UTM selection provides an accurate, automated way to project single-site survey datasets without requiring manual user input.
- **Local Storage & In-Memory Store**: Kept simple and stateless to focus on core geospatial processing without introducing unnecessary database dependencies for an internship assignment.

## What I Learned

Building this project gave me hands-on experience solving real-world geospatial backend engineering problems:

- **Geospatial Coordinate Systems**: I gained a much clearer understanding of why geographic coordinates (degrees) cannot be used directly for distance or area calculations, and how to programmatically select appropriate UTM projections.
- **Working with Pyogrio & GDAL**: I learned how vector drivers discover and read layers in KML files and ESRI Shapefiles, and how to structure layer iteration cleanly.
- **API Design with Pydantic v2**: I learned how to structure nested response schemas, discriminate between different measurement models (area vs. length vs. null), and handle serialization cleanly.
- **Defensive File Ingestion**: Working with ZIP archives taught me about real-world security vulnerabilities like Zip Slip and how to sanitize paths across both Windows and Unix environments.
- **Containerizing Geospatial Applications**: I learned how to construct a multi-stage Docker build that bundles the necessary C libraries for spatial data while keeping the final container lightweight and running under an unprivileged user.

## Limitations

- **In-Memory Metadata Store**: File records are stored in memory for the life of the process. Restarting the server clears the file index (though files remain on disk).
- **Synchronous File Processing**: Files are processed synchronously in the request thread, which is fine for small to medium survey files but would block the event loop for very large datasets.
- **Single UTM Zone for Wide Datasets**: The centroid UTM projection is optimal for localized survey sites. Datasets spanning multiple UTM zones or entire continents would experience projection distortion at the edges.

## Future Improvements

If extended into a larger production system, the following enhancements would be natural next steps:

- **PostgreSQL / PostGIS**: Persist file records, geometry, and spatial indexes in a database to enable spatial queries (intersections, buffers, bounding box lookups).
- **Background Task Processing**: Move heavy file parsing to a background worker queue (e.g. Celery or RQ) so that file uploads return immediately with a job ID.
- **Cloud Object Storage**: Store uploaded raw files and processed artifacts in AWS S3 or Google Cloud Storage instead of the local filesystem.
- **Authentication**: Add API key or JWT-based authentication for user access control.
- **Support for Large Geographic Extents**: Implement custom projection selection (such as Albers Equal Area or Lambert Conformal Conic) for regional datasets spanning multiple UTM zones.

## Running Locally

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then visit:
```
http://127.0.0.1:8000/docs
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Docker

### Direct Docker Run

```bash
docker build -t aereo-geospatial-api .
docker run --rm -p 8000:8000 aereo-geospatial-api
```

### Docker Compose

```bash
docker compose up --build
```

## Testing

Run the full quality and verification suite:

```bash
# Run automated tests
pytest -v

# Run code linter
ruff check .

# Check code formatting
black --check app/ tests/

# Verify dependencies
pip check
```

## GitHub

Repository:
[https://github.com/adavesh19/AEREO](https://github.com/adavesh19/AEREO)
