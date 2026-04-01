"""
Centralised logging configuration for Music Source Separator.

Usage:
    from lib.logging import get_logger, configure_logging

    configure_logging()            # call once at app startup
    logger = get_logger(__name__)  # in every module
"""

import logging
import sys
from typing import Optional

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure the root logger with a consistent format.

    Call this once at application startup (in api.py or cli.py).
    All module-level loggers created with get_logger() will inherit
    this configuration automatically.

    Args:
        level: Logging level, e.g. logging.DEBUG or logging.INFO.
    """
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # override any prior basicConfig calls
    )
    # Quieten noisy third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Return a named logger.

    Args:
        name:  Typically __name__ of the calling module.
        level: Optional override for this specific logger's level.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger
