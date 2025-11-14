import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

# Suppress non-critical startup warnings globally
warnings.filterwarnings("ignore")

# ============================================================
#                   PATH SETUP
# ============================================================
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
#                   CONFIG IMPORTS
# ============================================================
from config import (
    EMAIL_USERNAME,
    YOUR_NAME,
    YOUR_GMAIL_ADDRESS_FOR_DRAFTS,
)

# ============================================================
#                   UTILITIES
# ============================================================
from utils.logger import get_logger
from utils.records_manager import (
    log_email_record,
    initialize_csv,
    RECORDS_CSV_PATH,
)
from core.email_sender import extract_name_from_email

# ============================================================
#                   CORE COMPONENTS
# ============================================================
from core.email_ingestion import fetch_email
from core.supervisor import supervisor_langgraph
from core.email_sender import send_email, send_draft_to_gmail
from core.state import EmailState

# Import unified fallback message from formatter to keep text consistent
from utils.formatter import FALLBACK_RESPONSE

# ============================================================
#                   LOGGER INITIALIZATION
# ============================================================
logger = get_logger(__name__, log_to_file=True)


# ============================================================
#                   HELPER FUNCTIONS
# ============================================================
def _get_sender_email_and_name(email_record: dict):
    """Extract sender email and name, normalized for IMAP or JSON inputs."""
    candidate_email = (
        email_record.get("from")
        or email_record.get("sender_email")
        or email_record.get("sender")
        or ""
    )

    candidate_name = (
        email_record.get("sender_name")
        or email_record.get("from_name")
        or None
    )

    if not candidate_name:
        candidate_name = extract_name_from_email(candidate_email)

    return candidate_email or "", candidate_name or "Customer"


def handle_email_sending(final_state: EmailState, user_name: str, dry_run: bool) -> str:
    """Handles sending or drafting based on AI pipeline results."""
    email_data = final_state.current_email
    generated_response = final_state.generated_response_body or ""
    original_sender_email, original_sender_name = _get_sender_email_and_name(email_data)
    original_subject = email_data.get("subject", "No Subject")

    # Ensure non-empty response (global fallback)
    if not generated_response.strip():
        logger.warning(f"[Main] Empty generated response for ID {final_state.current_email_id} — inserting fallback.")
        generated_response = FALLBACK_RESPONSE
        final_state.generated_response_body = generated_response

    # Ensure recipient present
    if not original_sender_email:
        logger.error(f"[Main] Missing recipient address for ID {final_state.current_email_id}; skipping send.")
        return "Skipped (No Recipient)"

    # If previous processing error flagged, skip sending
    if final_state.processing_error:
        logger.warning(
            f"[Main] Skipping send/draft for ID {final_state.current_email_id} — prior processing error: "
            f"{final_state.processing_error}"
        )
        return "Skipped (Processing Error)"

    email_for_sending = {
        "subject": original_subject,
        "response": generated_response,
        "to": original_sender_email,
        "from": EMAIL_USERNAME,
    }

    # Draft mode for human review or dry run
    if dry_run or final_state.requires_human_review:
        logger.info(
            f"[Main] ID {final_state.current_email_id} flagged for review/dry-run. "
            f"Sending draft to {YOUR_GMAIL_ADDRESS_FOR_DRAFTS}."
        )
        if send_draft_to_gmail(email_for_sending, user_name, YOUR_GMAIL_ADDRESS_FOR_DRAFTS):
            return "Drafted"
        logger.error(f"[Main] Failed to send draft for ID {final_state.current_email_id}.")
        return "Draft Failed"

    # Direct send
    logger.info(f"[Main] ID {final_state.current_email_id} — sending reply to {original_sender_email}")
    if send_email(email_for_sending, user_name):
        return "Sent Directly"

    logger.error(f"[Main] Failed to send direct reply for ID {final_state.current_email_id}.")
    return "Send Failed"


# ============================================================
#                   MAIN WORKFLOW
# ============================================================
def main():
    """Main orchestration for the AI-powered email workflow."""
    logger.info("=" * 60)
    logger.info("[Main] Starting ShipCube AI Email Automation Pipeline...")
    logger.info("=" * 60)

    initialize_csv(RECORDS_CSV_PATH)

    # ---------------- CONFIG INPUTS ----------------
    simulate_fetch = input("Use sample_emails.json instead of IMAP? (y/n): ").strip().lower() == "y"
    email_limit = int(input("Number of emails to process (e.g. 1, 5, 10): ") or "1")
    dry_run_send = input("Send all responses as DRAFTS (dry-run)? (y/n): ").strip().lower() == "y"
    mark_as_seen = (
        input("Mark fetched emails as 'seen' on IMAP? (y/n): ").strip().lower() == "y"
        if not simulate_fetch
        else False
    )

    logger.info(f"[Main] Simulation Mode: {simulate_fetch}")
    logger.info(f"[Main] Processing Limit: {email_limit}")
    logger.info(f"[Main] Dry Run: {dry_run_send}")

    # ---------------- FETCH EMAILS ----------------
    logger.info("[Main] Fetching emails...")
    emails_to_process = fetch_email(
        simulate=simulate_fetch,
        limit=email_limit,
        mark_as_seen=mark_as_seen,
    )

    if not emails_to_process:
        logger.info("[Main] No emails found to process. Exiting.")
        return

    logger.info(f"[Main] {len(emails_to_process)} emails ready for processing.")

    # Detect if using Gemini free-tier
    using_free_tier = os.getenv("GEMINI_FREE_TIER", "true").lower() == "true"
    base_cooldown = 40 if using_free_tier else 10

    # ---------------- PROCESS LOOP ----------------
    for i, email_data_raw in enumerate(emails_to_process, start=1):
        email_id = email_data_raw.get("id", f"simulated_{i}")
        sender_email, sender_name_calc = _get_sender_email_and_name(email_data_raw)
        sender_name = email_data_raw.get("sender_name") or sender_name_calc
        subject = email_data_raw.get("subject", "No Subject")

        logger.info("-" * 60)
        logger.info(f"[Main] Processing Email {i}/{len(emails_to_process)} — ID: {email_id}")
        logger.info(f"[Main] From: {sender_name} <{sender_email}>")
        logger.info(f"[Main] Subject: {subject}")

        try:
            recipient_name_for_llm = extract_name_from_email(sender_email)

            # --- PROCESS THROUGH PIPELINE ---
            logger.info("[Main] Running email through AI pipeline (Filter → Summarize → Respond)...")
            start_time = time.time()

            final_state: EmailState = supervisor_langgraph(
                selected_email=email_data_raw,
                your_name=YOUR_NAME,
                recipient_name=recipient_name_for_llm,
            )

            elapsed_time = time.time() - start_time
            logger.info(f"[Main] Processing completed in {elapsed_time:.2f}s for Email ID {email_id}")

            # --- DEBUG SUMMARY ---
            logger.debug(
                f"[Main] Results for {email_id} — "
                f"Classification={final_state.classification}, "
                f"Summary length={len(final_state.summary or '')}, "
                f"Response length={len(final_state.generated_response_body or '')}, "
                f"Review={final_state.requires_human_review}, "
                f"Error={final_state.processing_error}"
            )

            # --- DETERMINE NEXT STEP ---
            if final_state.processing_error:
                response_status_action = "Error During Processing"
            elif final_state.classification in ["spam", "promotional"]:
                response_status_action = f"Skipped ({final_state.classification.capitalize()})"
            else:
                response_status_action = handle_email_sending(final_state, YOUR_NAME, dry_run_send)

        except Exception as e:
            logger.critical(f"[Main] Critical error while processing {email_id}: {e}", exc_info=True)
            final_state = EmailState(
                current_email=email_data_raw,
                current_email_id=email_id,
                classification="error",
                summary="Critical pipeline failure.",
                generated_response_body="Error occurred during processing.",
                processing_error=str(e),
            )
            response_status_action = "Critical Error"

        # ---------------- LOG RECORD ----------------
        record_data = {
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

        log_email_record(record_data, RECORDS_CSV_PATH)

        # --- DELAY BETWEEN EMAILS ---
        if i < len(emails_to_process):
            logger.info(f"[Main] Cooling down for {base_cooldown}s before next email to respect Gemini API limits...")
            time.sleep(base_cooldown)

    logger.info("[Main] All emails processed successfully.")
    logger.info("=" * 60)


# ============================================================
#                   ENTRY POINT
# ============================================================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("[Main] Process manually interrupted by user.")
    except Exception as e:
        logger.critical(f"[Main] Unhandled exception: {e}", exc_info=True)
