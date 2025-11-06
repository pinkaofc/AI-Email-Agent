import json
import socket
from pathlib import Path
from config import (
    EMAIL_USERNAME,
    EMAIL_PASSWORD,
    IMAP_SERVER,
    IMAP_PORT,
)
from utils.logger import get_logger

logger = get_logger(__name__, log_to_file=True)
logger.info("[Email Ingestion] Logger initialized successfully.")

# --- Import IMAP Fetcher Safely ---
try:
    from core.email_imap import fetch_imap_emails
except (ImportError, ModuleNotFoundError) as e:
    logger.error(
        f"[Email Ingestion] Could not import fetch_imap_emails from core.email_imap: {e}. "
        "IMAP fetching will be unavailable. Ensure 'core/email_imap.py' exists and dependencies (like beautifulsoup4) are installed."
    )
    fetch_imap_emails = None


# -------------------------------
# Helper: Check local port status
# -------------------------------
def is_running_locally(port: int = 8000) -> bool:
    """
    Checks if a local port is free (used to detect dev environment or conflicts).
    Returns True if available, False otherwise.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind(("localhost", port))
            return True
    except OSError:
        return False
    except Exception as e:
        logger.warning(f"[Email Ingestion] Error checking local port {port}: {e}")
        return False


# -------------------------------
# Core Email Fetch Function
# -------------------------------
def fetch_email(simulate: bool = True, limit: int = 10, mark_as_seen: bool = False):
    """
    Fetches emails for processing.

    If simulate=True, loads emails from local JSON (sample_emails.json).
    If simulate=False, connects to IMAP using Gmail credentials.

    Args:
        simulate (bool): Whether to use simulation mode.
        limit (int): Max number of emails to fetch (when using IMAP).
        mark_as_seen (bool): Whether to mark fetched emails as 'seen' on Gmail.

    Returns:
        list[dict]: List of email dictionaries.
    """
    # --- Simulation Mode (local) ---
    if simulate:
        email_file = Path(__file__).parent.parent / "sample_emails.json"
        logger.info("[Email Ingestion] Running in simulation mode (local JSON).")
        try:
            with open(email_file, "r", encoding="utf-8") as f:
                emails = json.load(f)
            logger.info(f"[Email Ingestion] Loaded {len(emails)} simulated emails from {email_file.name}")
            return emails
        except FileNotFoundError:
            logger.error(f"[Email Ingestion] Simulation file not found: {email_file}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"[Email Ingestion] Failed to parse {email_file}: {e}")
            return []

    # --- Real Email Mode (IMAP) ---
    else:
        if not fetch_imap_emails:
            raise ImportError(
                "[Email Ingestion] IMAP fetching unavailable — missing 'core/email_imap.py' or required modules."
            )

        # Sanity checks for credentials
        if not EMAIL_USERNAME or not EMAIL_APP_PASSWORD:
            raise ValueError(
                "[Email Ingestion] Missing EMAIL_USERNAME or EMAIL_APP_PASSWORD in config or .env file."
            )

        logger.info(
            f"[Email Ingestion] Attempting to fetch {limit} unread emails via IMAP for {EMAIL_USERNAME} from {IMAP_SERVER}:{IMAP_PORT}"
        )

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
                logger.warning("[Email Ingestion] No unread emails retrieved.")
                return []

            logger.info(f"[Email Ingestion] Successfully fetched {len(emails)} emails via IMAP.")
            return emails

        except Exception as e:
            logger.error(f"[Email Ingestion] IMAP fetching failed: {e}", exc_info=True)
            return []
