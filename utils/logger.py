import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

def get_logger(
    name: str,
    log_to_file: bool = False,
    log_dir: str = "logs",
    log_level: int = logging.DEBUG,
    max_file_size_mb: int = 5,
    backup_count: int = 3,
) -> logging.Logger:
    """
    Creates and returns a logger with console and optional rotating file output.

    Args:
        name (str): Name of the logger (usually __name__).
        log_to_file (bool): Whether to also write logs to a file.
        log_dir (str): Directory for log files if file logging is enabled.
        log_level (int): Logging level (e.g., logging.INFO, logging.DEBUG).
        max_file_size_mb (int): Maximum size per log file before rotation.
        backup_count (int): Number of old log files to retain.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.propagate = False  # Prevent duplicate log entries in root logger

    # If logger already has handlers, return it directly to avoid duplication
    if logger.handlers:
        return logger

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # --- Optional rotating file handler ---
    if log_to_file:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log_file_path = Path(log_dir) / f"{name}.log"
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
    return logger
