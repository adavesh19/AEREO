"""
Structured logging configuration for the application.

Sets up a consistent logging format across all modules.
"""

import logging
import sys

from app.config import get_settings


def setup_logging() -> None:
    """
    Configure root logger with a structured format.

    Reads LOG_LEVEL from application settings so it can be adjusted
    via environment variable without code changes.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times.
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        root_logger.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (module-level convenience wrapper)."""
    return logging.getLogger(name)
