"""
backend/logging_config.py
==========================
Centralised logging setup for the Student Finance Management backend.

Call ``setup_logging()`` once at application entry points (generate_data,
API server, CLI tools).  All backend modules use ``logging.getLogger(__name__)``
— they pick up configuration automatically.
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str | Path] = None,
    fmt: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
) -> None:
    """
    Configure root logger with console (and optionally file) handlers.

    Parameters
    ----------
    level : str
        Logging level for the root logger: DEBUG, INFO, WARNING, ERROR.
    log_file : str | Path | None
        Optional path for a rotating file handler.
    fmt : str
        Log message format string.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler (optional)
    if log_file is not None:
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
