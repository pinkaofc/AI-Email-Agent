import os
import sys
import time
from datetime import datetime
from pathlib import Path

# --- Fix for local package imports ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- Config ---
from config import (
    EMAIL_USERNAME,
    YOUR_NAME,
    YOUR_GMAIL_ADDRESS_FOR_DRAFTS,
)

# --- Utils ---
from utils.logger import get_logger
from utils.records_manager import (
    log_email_record,
    initialize_csv,
    RECORDS_CSV_PATH,
)
from core.email_sender import extract_name_from_email

# --- Core Components ---
from core.email_ingestion import fetch_email
from core.supervisor import supervisor_langgraph
from core.email_sender import send_email, send_draft_to_gmail
from core.state import EmailState

# --- Logger Initialization ---
logger = get_logger(__name__, log_to_file=True)


def _get_sender_email_and_name(email_record: dict):
    """
    Normalize email record fields so we accept multiple JSON / IMAP formats.
    Prefer these keys in order:
      - 'from' (sample_emails.json)
      - 'sender_email' (IMAP loader)
      - 'sender' (any other variant)
    Returns (email_address, friendly_name)
    """
    # Possible keys that might hold the sender's email address
    candidate_email = (
        email_record.get("from")
        or email_record.get("sender_email")
        or email_record.get("sender")
        or ""
    )

    # If the sample includes sender_name explicitly prefer it
    candidate_name = (
        email_record.get("sender_name")
        or email_record.get("from_name")
        or None
    )

    # If candidate_name is missing, derive it from email
    if not candidate_name:
        candidate_name = extract_name_from_email(candidate_email)

    # Ensure we never return an empty email; fallback is empty string (handled later)
    return candidate_email or "", candidate_name or "Customer"


def handle_email_sending(final_state: EmailState, user_name: str, dry_run: bool) -> str:
    """Handles sending or drafting an email based on workflow state."""
    email_data = final_state.current_email
    generated_response = final_state.generated_response_body

    # --- Normalize sender address and name from email record ---
    original_sender_email, original_sender_name = _get_sender_email_and_name(email_data)

    original_subject = email_data.get("subject", "No Subject")

    if not generated_response or final_state.processing_error:
        logger.warning(
            f"[Main] Skipping send/draft for email ID {final_state.current_email_id} "
            f"due to missing response or previous error."
        )
        return "Skipped (No Response/Error)"

    # Build the payload expected by send_email / send_draft_to_gmail.
    # Important: 'to' is the recipient (customer), 'from' is your account (EMAIL_USERNAME).
    email_for_sending = {
        "subject": original_subject,
        "response": generated_response,
        "to": original_sender_email,   # send to actual customer
        "from": EMAIL_USERNAME         # your sending address (used in headers)
    }

    # If draft mode or flagged for human review -> send draft to your review Gmail
    if dry_run or final_state.requires_human_review:
        logger.info(
            f"[Main] Email ID {final_state.current_email_id} flagged for human review "
            f"or in dry-run mode. Sending draft to '{YOUR_GMAIL_ADDRESS_FOR_DRAFTS}'."
        )
        # send_draft_to_gmail expects the original sender's name to create greeting in draft.
        # It will call extract_name_from_email() internally if needed.
        if send_draft_to_gmail(email_for_sending, user_name, YOUR_GMAIL_ADDRESS_FOR_DRAFTS):
            return "Drafted"
        else:
            logger.error(f"[Main] Failed to send draft for email ID {final_state.current_email_id}.")
            return "Draft Failed"
    else:
        # Send directly to customer
        logger.info(
            f"[Main] Email ID {final_state.current_email_id} ready for direct reply to "
            f"'{original_sender_email}'."
        )
        if send_email(email_for_sending, user_name):
            return "Sent Directly"
        else:
            logger.error(f"[Main] Failed to send email for email ID {final_state.current_email_id}.")
            return "Send Failed"


def main():
    """Main orchestration loop for the AI email agent."""
    logger.info("[Main] Starting AI email automation pipeline...")

    # Initialize CSV records
    initialize_csv(RECORDS_CSV_PATH)

    # --- Configuration Mode ---
    simulate_fetch = input("Use simulated emails from sample_emails.json? (y/n): ").strip().lower() == "y"
    email_limit = int(input("How many emails to process (max)? (e.g., 1): ") or "1")
    dry_run_send = input("Send all responses as DRAFTS to your Gmail address (dry run)? (y/n): ").strip().lower() == "y"
    mark_as_seen = (
        input("Mark fetched emails as 'seen' on IMAP server (only for real fetch)? (y/n): ").strip().lower() == "y"
        if not simulate_fetch
        else False
    )

    logger.info(f"[Main] Using simulation mode: {simulate_fetch}")
    logger.info(f"[Main] Email limit set to {email_limit}")
    logger.info(f"[Main] Dry-run mode: {dry_run_send}")

    # --- Fetch Emails ---
    logger.info("[Main] Fetching emails...")
    emails_to_process = fetch_email(
        simulate=simulate_fetch,
        limit=email_limit,
        mark_as_seen=mark_as_seen,
    )

    if not emails_to_process:
        logger.info("[Main] No emails found to process. Exiting.")
        return

    logger.info(f"[Main] Fetched {len(emails_to_process)} email(s). Beginning processing.")

    # --- Process Each Email ---
    for i, email_data_raw in enumerate(emails_to_process, start=1):
        email_id = email_data_raw.get("id", f"simulated_{i}")

        # Normalize sender fields (supports both sample JSON and IMAP results)
        sender_email, sender_name_calc = _get_sender_email_and_name(email_data_raw)

        # If sample JSON provides 'from' but not sender_name, we compute friendly name.
        # Also allow an explicit 'sender_name' field to override.
        sender_name = email_data_raw.get("sender_name") or sender_name_calc

        subject = email_data_raw.get("subject", "No Subject")

        logger.info(f"[Main] Processing Email {i} (ID: {email_id})")
        logger.info(f"[Main] Subject: {subject}")
        logger.info(f"[Main] From: {sender_name} <{sender_email}>")

        try:
            recipient_name_for_llm = extract_name_from_email(sender_email)

            final_state: EmailState = supervisor_langgraph(
                selected_email=email_data_raw,
                your_name=YOUR_NAME,
                recipient_name=recipient_name_for_llm,
            )

            logger.debug(
                f"[Main] Email ID {email_id} results: "
                f"Classification='{final_state.classification}', "
                f"Summary length={len(final_state.summary or '')}, "
                f"Response length={len(final_state.generated_response_body or '')}, "
                f"Requires Review={final_state.requires_human_review}, "
                f"Error='{final_state.processing_error}'"
            )

            if final_state.processing_error:
                response_status_action = "Error During Processing"
                logger.error(f"[Main] Skipping email ID {email_id}: {final_state.processing_error}")
            elif final_state.classification in ["spam", "promotional"]:
                response_status_action = f"Skipped ({final_state.classification.capitalize()})"
                logger.info(f"[Main] Skipping spam/promotional email ID {email_id}.")
            else:
                response_status_action = handle_email_sending(final_state, YOUR_NAME, dry_run_send)

        except Exception as e:
            logger.critical(f"[Main] Critical error processing email ID {email_id}: {e}", exc_info=True)
            final_state = EmailState(
                current_email=email_data_raw,
                current_email_id=email_id,
                classification="error",
                summary="Processing failed due to critical error.",
                generated_response_body="Error occurred during processing.",
                processing_error=f"Critical error: {str(e)}",
            )
            response_status_action = "Critical Error"

        # --- Log Record ---
        record_data_to_log = {
            "SR No": i,
            "Timestamp": email_data_raw.get("timestamp") or datetime.now().isoformat(),
            "Sender Email": sender_email,
            "Sender Name": sender_name,
            "Recipient Email": EMAIL_USERNAME,
            "Original Subject": subject,
            "Original Content": email_data_raw.get("body", ""),
            "Classification": final_state.classification,
            "Summary": final_state.summary,
            "Generated Response": final_state.generated_response_body,
            "Requires Human Review": final_state.requires_human_review,
            "Response Status": response_status_action,
            "Processing Error": final_state.processing_error,
            "Record Save Time": datetime.now().isoformat(),
        }

        log_email_record(record_data_to_log, RECORDS_CSV_PATH)

        # --- Delay between emails ---
        if i < len(emails_to_process):
            time.sleep(10)

    logger.info("[Main] All selected emails processed. Workflow finished successfully.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("[Main] Process interrupted manually by user.")
    except Exception as e:
        logger.critical(f"[Main] Unhandled exception: {e}", exc_info=True)
