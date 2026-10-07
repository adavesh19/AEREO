"""
FastAPI application entry point.

Wires together:
- Application settings.
- Logging configuration.
- API routes.
- Health check endpoint.
- Global exception handling.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import files as files_router
from app.config import get_settings
from app.utils.logging import setup_logging

# Initialise logging before anything else
setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler: initialise directories and verify drivers."""
    logger.info(
        "Starting %s v%s | upload_dir=%s | max_upload=%dMB | log_level=%s",
        settings.app_name,
        settings.app_version,
        settings.upload_dir,
        settings.max_upload_size_mb,
        settings.log_level,
    )
    # Ensure the upload directory exists at startup
    settings.upload_path.mkdir(parents=True, exist_ok=True)

    # Verify Pyogrio / GDAL drivers (e.g. KML, ESRI Shapefile)
    from app.services import file_service

    file_service.verify_driver_support()

    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS (permissive for development; restrict in production)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(files_router.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Returns a simple OK response to confirm the service is running.",
)
async def health_check() -> dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Global exception handler (catch-all to prevent stack trace leakage)
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions.

    Logs full details internally but returns only a generic message to the caller
    so that internal stack traces are never exposed via the API.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal server error occurred."},
    )
