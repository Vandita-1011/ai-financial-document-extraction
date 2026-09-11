"""
Centralised logging configuration.

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
"""

import logging
import sys


_CONFIGURED = False


def _configure_logging(log_level: str = "INFO") -> None:
    """Configure the root logger once for the entire application."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers if called multiple times in tests
    if not root_logger.handlers:
        root_logger.addHandler(handler)

    # Quiet down noisy third-party libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for *name*, bootstrapping the root config if needed.

    Importing settings here (rather than at module level) avoids a circular
    import between config → logging → config.
    """
    if not _CONFIGURED:
        try:
            from app.core.config import settings  # noqa: PLC0415
            _configure_logging(settings.LOG_LEVEL)
        except Exception:
            # Fallback during early startup (e.g., before settings are loaded)
            _configure_logging("INFO")

    return logging.getLogger(name)
