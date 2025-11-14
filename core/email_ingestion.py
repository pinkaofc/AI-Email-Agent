import json
import socket
import time
from pathlib import Path
from config import EMAIL_USERNAME, EMAIL_APP_PASSWORD, IMAP_SERVER, IMAP_PORT
from utils.logger import get_logger

logger = get_logger(__name__, log_to_file=True)
logger.info("[Email Ingestion] Logger initialized successfully.")

try:
    from core.email_imap import fetch_imap_emails
except (ImportError, ModuleNotFoundError) as e:
    logger.error(f"[Email Ingestion] IMAP fetcher unavailable: {e}")
    fetch_imap_emails = None


def is_port_available(port: int = 8000) -> bool:
    """Check if a local port is free (used for detecting environment conflicts)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind(("localhost", port))
            return True
    except OSError:
        return False


def fetch_email(simulate: bool = True, limit: int = 10, mark_as_seen: bool = False):
    """
    Fetches emails either from local simulation or IMAP.

    Args:
        simulate (bool): Use local JSON instead of IMAP.
        limit (int): Number of emails to fetch.
        mark_as_seen (bool): Mark fetched emails as read.
    """
    if simulate:
        email_file = Path(__file__).parent.parent / "sample_emails.json"
        logger.info("[Email Ingestion] Simulation mode enabled — using local email dataset.")
        try:
            with open(email_file, "r", encoding="utf-8") as f:
                emails = json.load(f)
            logger.info(f"[Email Ingestion] Loaded {len(emails)} emails from {email_file.name}")
            time.sleep(2)
            return emails
        except Exception as e:
            logger.error(f"[Email Ingestion] Failed to load simulation emails: {e}")
            return []

    # --- Live IMAP Fetching ---
    if not fetch_imap_emails:
        logger.error("[Email Ingestion] IMAP fetcher not initialized.")
        return []

    if not EMAIL_USERNAME or not EMAIL_APP_PASSWORD:
        raise ValueError("[Email Ingestion] Missing email credentials in .env/config.")

    logger.info(f"[Email Ingestion] Connecting to IMAP server {IMAP_SERVER}:{IMAP_PORT} as {EMAIL_USERNAME}")

    for attempt in range(3):
        try:
            emails = fetch_imap_emails(
                email_address=EMAIL_USERNAME,
                app_password=EMAIL_APP_PASSWORD,
                imap_server=IMAP_SERVER,
                imap_port=IMAP_PORT,
                max_emails=limit,
                mark_as_seen=mark_as_seen,
            )

            if not emails:
                logger.warning("[Email Ingestion] No unread emails found.")
                return []

            logger.info(f"[Email Ingestion] Successfully fetched {len(emails)} emails via IMAP.")
            time.sleep(3)  # cooldown between batches
            return emails

        except Exception as e:
            logger.warning(f"[Email Ingestion] Attempt {attempt + 1} failed: {e}")
            time.sleep(5)

    logger.error("[Email Ingestion] Failed to fetch emails after multiple attempts.")
    return []
