"""Shared logging setup.

Provides a single ``setup_logging`` helper so every service logs in the same
structured, timestamped format. Per the safety controls, we log every
analysis request and every generated signal and never silently swallow
errors.
"""
from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(service_name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure root logging once and return a named logger for the service."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
        root.addHandler(handler)
        root.setLevel(level)
    return logging.getLogger(service_name)
