# syntax=docker/dockerfile:1.5

# ---------------------------------------------------------------------------
# Stage 1 – Builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install system-level geospatial dependencies required by Pyogrio / GDAL / PROJ
RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        libproj-dev \
        libgeos-dev \
        libspatialindex-dev \
        gcc \
        g++ \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment to isolate Python packages
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 – Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL maintainer="Adavesh" \
      description="Geospatial File Measurement API" \
      version="1.0.0"

# Runtime geospatial libraries (no compiler needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgdal32 \
        libproj25 \
        libgeos-c1v5 \
        libspatialindex7 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN groupadd --gid 1001 appgroup \
 && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy application source
COPY app/ ./app/
COPY sample_data/ ./sample_data/

# Create uploads directory and set ownership
RUN mkdir -p /app/uploads && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Environment configuration (can be overridden at runtime)
ENV APP_NAME="Geospatial File Measurement API" \
    UPLOAD_DIR="/app/uploads" \
    MAX_UPLOAD_SIZE_MB=50 \
    LOG_LEVEL=INFO

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
