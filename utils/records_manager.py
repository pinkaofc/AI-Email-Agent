import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from utils.logger import get_logger

logger = get_logger(__name__, log_to_file=True)

# -------------------------------------------------------------------
# PATHS
# -------------------------------------------------------------------
RECORDS_DIR = Path(__file__).resolve().parent.parent / "records"
RECORDS_CSV_PATH = RECORDS_DIR / "records.csv"

CSV_HEADERS = [
    "SR No",
    "Timestamp",
    "Sender Email",
    "Sender Name",
    "Recipient Email",
    "Original Subject",
    "Original Content",
    "Classification",
    "Summary",
    "Generated Response",
    "Requires Human Review",
    "Response Status",
    "Processing Error",
    "Record Save Time",
]


# -------------------------------------------------------------------
# INITIALIZE CSV
# -------------------------------------------------------------------
def initialize_csv(csv_path: Path = RECORDS_CSV_PATH) -> None:
    """
    Creates records.csv with correct headers if missing.
    Ensures directory exists.
    """

    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        if not csv_path.exists():
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)

            logger.info(f"[Records] Created new CSV at: {csv_path}")
        else:
            # Ensure header row exists correctly
            with open(csv_path, "r", encoding="utf-8") as f:
                first_line = f.readline()

            if "SR No" not in first_line:
                # Rebuild file with header + append existing rows
                old_data = list(csv.reader(open(csv_path, "r", encoding="utf-8")))
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_HEADERS)
                    writer.writerows(old_data)

                logger.warning("[Records] Missing header fixed in records.csv")

    except Exception as e:
        logger.error(f"[Records] CSV initialization error: {e}", exc_info=True)


# -------------------------------------------------------------------
# SR NUMBER GENERATOR
# -------------------------------------------------------------------
def get_next_sr_no(csv_path: Path = RECORDS_CSV_PATH) -> int:
    """
    Reads last non-empty SR No and increments it.
    Handles empty files and malformed values safely.
    """
    try:
        if not csv_path.exists():
            return 1

        with open(csv_path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        # Only header present
        if len(rows) <= 1:
            return 1

        # Find last non-empty row with SR No
        for row in reversed(rows):
            if row and row[0].strip().isdigit():
                return int(row[0]) + 1

        return 1

    except Exception as e:
        logger.warning(f"[Records] SR-No read failure: {e}")
        return 1


# -------------------------------------------------------------------
# WRITE RECORD
# -------------------------------------------------------------------
def log_email_record(record_data: Dict[str, Any], csv_path: Path = RECORDS_CSV_PATH) -> None:
    """
    Safely appends a new email processing record into the CSV file.
    Ensures correct ordering of fields.
    """
    initialize_csv(csv_path)

    # Assign SR No
    record_data["SR No"] = record_data.get("SR No", get_next_sr_no(csv_path))

    # Ensure timestamps
    record_data.setdefault("Timestamp", datetime.now().isoformat())
    record_data.setdefault("Record Save Time", datetime.now().isoformat())

    # Build an ordered row
    ordered_row = {header: record_data.get(header, "") for header in CSV_HEADERS}

    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow(ordered_row)

        logger.info(
            f"[Records] Saved record #{record_data['SR No']} | "
            f"Sender={record_data.get('Sender Email')} | "
            f"Classification={record_data.get('Classification')} | "
            f"Status={record_data.get('Response Status')}"
        )

    except PermissionError:
        logger.error(f"[Records] Permission denied for {csv_path}")
    except Exception as e:
        logger.error(f"[Records] Failed to write CSV record: {e}", exc_info=True)


# -------------------------------------------------------------------
# Manual test
# -------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Testing logging into: {RECORDS_CSV_PATH}")
    test_record = {
        "Sender Email": "test@example.com",
        "Sender Name": "Test User",
        "Recipient Email": "support@shipcube.com",
        "Original Subject": "Test message",
        "Original Content": "This is a sample email content.",
        "Classification": "neutral",
        "Summary": "Test summary",
        "Generated Response": "Sample response",
        "Requires Human Review": False,
        "Response Status": "Test Run",
        "Processing Error": "",
    }
    log_email_record(test_record)
    print("✓ Test record logged.")
