import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

# ============================================================
# PATH SETUP
# ============================================================
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# CONFIG IMPORTS
# ============================================================
from config import (
    EMAIL_USERNAME,
    YOUR_NAME,
    YOUR_GMAIL_ADDRESS_FOR_DRAFTS,
)

# ============================================================
# UTILITIES
# ============================================================
from utils.logger import get_logger
from utils.records_manager import (
    log_email_record,
    initialize_csv,
    RECORDS_CSV_PATH,
)
from utils.formatter import FALLBACK_RESPONSE, ask_yes_no, ask_positive_int
from core.email_sender import extract_name_from_email

# ============================================================
# CORE COMPONENTS
# ============================================================
from core.email_ingestion import fetch_email
from core.supervisor import supervisor_langgraph
from core.email_sender import send_email, send_draft_to_gmail
from core.state import EmailState

# ============================================================
# MONITORING (NEW)
# ============================================================
from monitoring.metrics import (
    EMAILS_PROCESSED,
    EMAIL_CLASSIFICATION_COUNTER,
    EMAIL_LATENCY,
    PIPELINE_ACTIVE,
)

# ============================================================
# LOGGER
# ============================================================
logger = get_logger(__name__, log_to_file=True)


# ============================================================
# HELPER: Extract Name & Email
# ============================================================
def _get_sender_email_and_name(email_record: dict):
    """Extract sender email & name consistently."""
    email_addr = (
        email_record.get("from")
        or email_record.get("sender_email")
        or email_record.get("sender")
        or ""
    )

    name = (
        email_record.get("sender_name")
        or email_record.get("from_name")
        or extract_name_from_email(email_addr)
        or "Customer"
    )

    return email_addr, name


# ============================================================
# HELPER: Send or Draft Email
# ============================================================
def handle_email_sending(final_state: EmailState, user_name: str, dry_run: bool) -> str:
    email_data = final_state.current_email
    response_body = final_state.generated_response_body or FALLBACK_RESPONSE
    recipient_email, _ = _get_sender_email_and_name(email_data)
    subject = email_data.get("subject", "No Subject")

    if not recipient_email:
        logger.error("[Main] Cannot send — No recipient email found.")
        return "Skipped (Missing Recipient)"

    if final_state.processing_error:
        logger.warning("[Main] Skipping send due to processing error.")
        return "Skipped (Processing Error)"

    payload = {
        "subject": subject,
        "response": response_body,
        "to": recipient_email,
        "from": EMAIL_USERNAME,
    }

    # draft
    if dry_run or final_state.requires_human_review:
        logger.info(f"[Main] Drafting email → {YOUR_GMAIL_ADDRESS_FOR_DRAFTS}")
        return "Drafted" if send_draft_to_gmail(payload, user_name, YOUR_GMAIL_ADDRESS_FOR_DRAFTS) else "Draft Failed"

    # send
    logger.info(f"[Main] Sending email to {recipient_email}")
    return "Sent Directly" if send_email(payload, user_name) else "Send Failed"


# ============================================================
# MAIN WORKFLOW
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("[Main] Starting ShipCube AI Email Pipeline")
    logger.info("=" * 60)

    initialize_csv(RECORDS_CSV_PATH)

    # ------------------------------------------------------------
    # FIXED INPUT VALIDATION (DO NOT BREAK PIPELINE FLOW)
    # ------------------------------------------------------------
    simulate = ask_yes_no("Use sample_emails.json instead of IMAP? (y/n): ")
    limit = ask_positive_int("How many emails? (1,5,10...): ")
    dry_run = ask_yes_no("Send ONLY drafts? (y/n): ")

    mark_seen = ask_yes_no("Mark IMAP emails as seen? (y/n): ") if not simulate else False

    # Fetch emails
    logger.info("[Main] Fetching emails…")
    emails = fetch_email(simulate=simulate, limit=limit, mark_as_seen=mark_seen)

    if not emails:
        logger.info("[Main] No emails fetched. Exiting.")
        return

    logger.info(f"[Main] Processing {len(emails)} email(s)")

    cooldown = 40 if os.getenv("GEMINI_FREE_TIER", "true").lower() == "true" else 10

    # ============================================================
    # PROCESS EACH EMAIL
    # ============================================================
    for index, email_raw in enumerate(emails, start=1):

        email_id = email_raw.get("id", f"simulated_{index}")
        sender_email, sender_name = _get_sender_email_and_name(email_raw)
        subject = email_raw.get("subject", "No Subject")

        logger.info("-" * 60)
        logger.info(f"[Main] Processing {index}/{len(emails)}")
        logger.info(f"       ID: {email_id}")
        logger.info(f"       From: {sender_name} <{sender_email}>")
        logger.info(f"       Subject: {subject}")

        PIPELINE_ACTIVE.inc()  # NEW METRIC

        try:
            # Track processing time
            with EMAIL_LATENCY.time():

                final_state: EmailState = supervisor_langgraph(
                    selected_email=email_raw,
                    your_name=YOUR_NAME,
                    recipient_name=extract_name_from_email(sender_email),
                )

            # classification metric
            EMAIL_CLASSIFICATION_COUNTER.labels(
                classification=final_state.classification or "unknown"
            ).inc()

            if final_state.processing_error:
                response_status = "Error During Processing"
                EMAILS_PROCESSED.labels(status="failed").inc()
            elif final_state.classification in ["spam", "promotional"]:
                response_status = f"Skipped ({final_state.classification})"
                EMAILS_PROCESSED.labels(status="success").inc()
            else:
                response_status = handle_email_sending(final_state, YOUR_NAME, dry_run)
                EMAILS_PROCESSED.labels(status="success").inc()

        except Exception as e:
            logger.critical(f"[Main] CRITICAL FAILURE for {email_id}: {e}", exc_info=True)
            final_state = EmailState(
                current_email=email_raw,
                current_email_id=email_id,
                classification="error",
                summary="Critical failure.",
                generated_response_body="Error occurred.",
                processing_error=str(e),
            )
            response_status = "Critical Error"
            EMAILS_PROCESSED.labels(status="failed").inc()

        finally:
            PIPELINE_ACTIVE.dec()  # NEW METRIC

        # Save CSV Log
        log_email_record(
            {
                "SR No": index,
                "Timestamp": email_raw.get("timestamp") or datetime.now().isoformat(),
                "Sender Email": sender_email,
                "Sender Name": sender_name,
                "Recipient Email": EMAIL_USERNAME,
                "Original Subject": subject,
                "Original Content": email_raw.get("body", ""),
                "Classification": final_state.classification,
                "Summary": final_state.summary,
                "Generated Response": final_state.generated_response_body,
                "Requires Human Review": final_state.requires_human_review,
                "Response Status": response_status,
                "Processing Error": final_state.processing_error,
                "Record Save Time": datetime.now().isoformat(),
            },
            RECORDS_CSV_PATH,
        )

        # cooldown before next email
        if index < len(emails):
            logger.info(f"[Main] Cooling down {cooldown}s (Gemini API limit)…")
            time.sleep(cooldown)

    logger.info("[Main] All emails processed.")
    logger.info("=" * 60)


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("[Main] Interrupted by user.")
    except Exception as e:
        logger.critical(f"[Main] Unhandled exception: {e}", exc_info=True)
