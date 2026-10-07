"""
Application configuration using Pydantic Settings.

All settings are configurable via environment variables or a .env file.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Geospatial File Measurement API"
    app_version: str = "1.0.0"
    app_description: str = (
        "A backend service that accepts geospatial files (KML, Shapefile ZIP), "
        "processes their features, handles CRS transformations, and returns "
        "accurate measurement information (area, length) in metric units."
    )
    debug: bool = False

    # Upload
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 50

    # Logging
    log_level: str = "INFO"

    @property
    def max_upload_size_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def upload_path(self) -> Path:
        """Resolved upload directory as a Path object."""
        return Path(self.upload_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings (singleton)."""
    return Settings()
