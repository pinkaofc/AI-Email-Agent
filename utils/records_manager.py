import os
import sys
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from utils.logger import get_logger

logger = get_logger(__name__, log_to_file=True)

# ------------------------------------------------------------
# File Paths & Constants
# ------------------------------------------------------------
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


# ------------------------------------------------------------
# CSV Initialization
# ------------------------------------------------------------
def initialize_csv(csv_path: Path = RECORDS_CSV_PATH) -> None:
    """
    Ensures the records CSV file exists with proper headers.
    Auto-creates 'records/' folder if missing.
    """
    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        # Create fresh CSV with headers
        if not csv_path.exists():
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)
            logger.info(f"[Records] Created new CSV file: {csv_path}")
        else:
            logger.debug(f"[Records] {csv_path.name} already exists.")

    except Exception as e:
        logger.error(f"[Records] Failed to initialize CSV: {e}", exc_info=True)


# ------------------------------------------------------------
# SR No Generator
# ------------------------------------------------------------
def get_next_sr_no(csv_path: Path = RECORDS_CSV_PATH) -> int:
    """
    Reads last row of CSV and returns next sequential SR No.
    If CSV is empty, returns 1.
    """
    if not csv_path.exists():
        return 1

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        # Only headers present
        if len(rows) <= 1:
            return 1

        last_row = rows[-1]
        last_sr = last_row[0].strip()

        return int(last_sr) + 1 if last_sr.isdigit() else 1

    except Exception as e:
        logger.warning(f"[Records] Failed to read last SR No: {e}")
        return 1


# ------------------------------------------------------------
# Record Writer
# ------------------------------------------------------------
def log_email_record(record_data: Dict[str, Any], csv_path: Path = RECORDS_CSV_PATH) -> None:
    """
    Appends one email record row to the CSV.
    Ensures:
      - Auto SR No
      - ISO timestamps
      - Columns always match required order
    """
    initialize_csv(csv_path)

    # Auto SR No
    record_data["SR No"] = record_data.get("SR No", get_next_sr_no(csv_path))

    # Ensure timestamps
    record_data.setdefault("Timestamp", datetime.now().isoformat())
    record_data.setdefault("Record Save Time", datetime.now().isoformat())

    # Create ordered row
    row_to_write = {header: record_data.get(header, "") for header in CSV_HEADERS}

    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow(row_to_write)

        logger.info(
            f"[Records] Logged record #{record_data['SR No']} | "
            f"Sender={record_data.get('Sender Email', 'N/A')} | "
            f"Status={record_data.get('Response Status', 'Unknown')}"
        )

    except PermissionError:
        logger.error(f"[Records] Permission denied: {csv_path}")
    except Exception as e:
        logger.error(f"[Records] Failed to write record: {e}", exc_info=True)


# ------------------------------------------------------------
# Manual Test
# ------------------------------------------------------------
if __name__ == "__main__":
    test_record = {
        "Timestamp": datetime.now().isoformat(),
        "Sender Email": "riya.sharma@example.com",
        "Sender Name": "Riya Sharma",
        "Recipient Email": "support@shipcube.com",
        "Original Subject": "Order delay inquiry",
        "Original Content": "My shipment SCX12400 is delayed.",
        "Classification": "negative",
        "Summary": "Customer asking for update on shipment SCX12400.",
        "Generated Response": "Hi Riya, your order is being checked.",
        "Requires Human Review": False,
        "Response Status": "Sent Directly",
        "Processing Error": "",
        "Record Save Time": datetime.now().isoformat(),
    }

    log_email_record(test_record)
    print(f"Record logged successfully at {RECORDS_CSV_PATH}")
