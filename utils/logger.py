import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import time


def get_logger(
    name: str,
    log_to_file: bool = False,
    log_dir: str = "logs",
    log_level: int = logging.DEBUG,
    max_file_size_mb: int = 5,
    backup_count: int = 3,
) -> logging.Logger:
    """
    Creates and returns a robust logger with console output and optional
    rotating log file support.

    Safe for production:
    - Prevents duplicate handlers
    - Rotates cleanly and keeps old logs
    - Creates log dir automatically
    - Stable timestamp formatting
    """

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.propagate = False  # Avoid double logging from root

    # If handlers already exist, return the same logger (prevents duplication)
    if getattr(logger, "_initialized", False):
        return logger

    # ------------------------------------------------------------
    # Console Handler
    # ------------------------------------------------------------
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # ------------------------------------------------------------
    # File Handler (Optional)
    # ------------------------------------------------------------
    if log_to_file:
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        # Use module name for log file; fallback to timestamp if unsafe
        safe_name = name.replace(".", "_").replace("/", "_")
        if not safe_name:
            safe_name = f"log_{int(time.time())}"

        log_file_path = Path(log_dir) / f"{safe_name}.log"

        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8",
        )

        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    logger.debug(f"Logger initialized for '{name}' (to_file={log_to_file}).")

    # Mark as initialized to prevent re-attaching handlers later
    logger._initialized = True

    return logger
