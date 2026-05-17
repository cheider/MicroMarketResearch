"""
Configures rotating file logging for the application.
Call configure_logging() once at startup (from run.py) before create_app().
"""

import logging
import logging.handlers
import os

_LOG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "logs")
)
LOG_FILE = os.path.join(_LOG_DIR, "sync.log")

_FMT = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)


def configure_logging():
    """
    Attaches a 5 MB rotating file handler (5 backups) to the root logger.
    Safe to call more than once — skips setup if the handler is already present.
    """
    os.makedirs(_LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    # Avoid adding duplicate handlers if called again in tests
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(_FMT)
    file_handler.setLevel(logging.DEBUG)

    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
