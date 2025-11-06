import csv
import os
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from utils.logger import get_logger

# Initialize logger for this module
logger = get_logger(__name__, log_to_file=True)

# Define the records directory and file path
RECORDS_DIR = Path(__file__).parent.parent / "records"
RECORDS_CSV_PATH = RECORDS_DIR / "records.csv"

# Define CSV headers (must match the log structure in main.py)
CSV_HEADERS = [
    "SR No", "Timestamp", "Sender Email", "Sender Name", "Recipient Email",
    "Original Subject", "Original Content", "Classification", "Summary",
    "Generated Response", "Requires Human Review", "Response Status",
    "Processing Error", "Record Save Time",
]


def initialize_csv(csv_path: Path = RECORDS_CSV_PATH) -> None:
    """
    Ensures the CSV file exists and contains headers.

    Args:
        csv_path (Path): Path to the CSV log file.
    """
    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not csv_path.exists():
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)
            logger.info(f"[Records] Initialized {csv_path.name} with headers.")
        else:
            logger.debug(f"[Records] {csv_path.name} already exists.")
    except Exception as e:
        logger.error(f"[Records] Failed to initialize CSV at {csv_path}: {e}", exc_info=True)


def log_email_record(record_data: Dict[str, Any], csv_path: Path = RECORDS_CSV_PATH) -> None:
    """
    Appends a single email processing record to the CSV file.

    Args:
        record_data (Dict[str, Any]): Dictionary of email details.
        csv_path (Path): Path to the CSV file where records are logged.
    """
    initialize_csv(csv_path)

    # Ensure required timestamps exist
    if "Record Save Time" not in record_data or not record_data["Record Save Time"]:
        record_data["Record Save Time"] = datetime.now().isoformat()
    if "Timestamp" not in record_data or not record_data["Timestamp"]:
        record_data["Timestamp"] = datetime.now().isoformat()

    # Ensure all headers exist in the row (fill missing with empty string)
    row_to_write = {header: record_data.get(header, "") for header in CSV_HEADERS}

    try:
        # Use append mode with flush for safety (atomic write pattern)
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow(row_to_write)
        logger.info(
            f"[Records] Logged email record: SR No {record_data.get('SR No', 'N/A')} "
            f"from {record_data.get('Sender Email', 'N/A')}"
        )
    except PermissionError:
        logger.error(f"[Records] Permission denied: Unable to write to {csv_path}")
    except Exception as e:
        logger.error(f"[Records] Failed to log email record: {e}", exc_info=True)
