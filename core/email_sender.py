import smtplib
import re
import time
import email.utils
from email.message import EmailMessage
from config import EMAIL_SERVER, EMAIL_PASSWORD, EMAIL_USERNAME, EMAIL_PORT
from utils.logger import get_logger
from utils.formatter import clean_text, format_email

logger = get_logger(__name__)


# ----------------------------
# Utility: Name Extraction
# ----------------------------
def extract_name_from_email(email_address: str) -> str:
    """
    Extracts a clean, readable name from an email address.
    Examples:
        raj.malhotra@malhotragoods.in -> Raj Malhotra
        james_liu@fasttrackglobal.cn -> James Liu
    """
    if not email_address or "@" not in email_address:
        return "Customer"

    local_part = email_address.split("@")[0]
    name_parts = re.split(r"[._-]+", local_part)
    formatted_name = " ".join(part.capitalize() for part in name_parts if part)
    return formatted_name or "Customer"


# ----------------------------
# Send Draft to Gmail (for review)
# ----------------------------
def send_draft_to_gmail(email_data: dict, user_name: str, gmail_address: str, retry: int = 2) -> bool:
    """
    Sends a draft version of an email to your Gmail for manual review.
    The message is NOT sent to the customer — only to your configured Gmail.

    Args:
        email_data (dict): Contains "subject", "response", "to" (customer email).
        user_name (str): Your name for signature.
        gmail_address (str): Gmail address where the draft will be sent.
        retry (int): Retry attempts for SMTP errors.

    Returns:
        bool: True if sent successfully, False otherwise.
    """
    subject = clean_text(email_data.get("subject", ""))
    raw_response = email_data.get("response", "").strip()
    customer_email = email_data.get("to", "")
    customer_name = extract_name_from_email(customer_email)

    formatted_response = format_email(subject, customer_name, raw_response, user_name)

    msg = EmailMessage()
    msg["Subject"] = f"Draft: Re: {subject}"
    msg["From"] = EMAIL_USERNAME
    msg["To"] = gmail_address
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.set_content(formatted_response, subtype="plain", charset="utf-8")

    for attempt in range(retry):
        try:
            logger.debug(f"[Draft] Connecting to SMTP {EMAIL_SERVER}:{EMAIL_PORT} (attempt {attempt + 1})")
            with smtplib.SMTP(EMAIL_SERVER, int(EMAIL_PORT), timeout=15) as server:
                server.starttls()
                server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
                server.send_message(msg)
            logger.info(f"[Draft] Sent draft of '{subject}' to review inbox {gmail_address}")
            return True
        except Exception as e:
            logger.warning(f"[Draft] Attempt {attempt + 1} failed: {e}")
            time.sleep(3)

    logger.error(f"[Draft] Failed to send draft after {retry} attempts.")
    return False


# ----------------------------
# Send Final Email to Customer
# ----------------------------
def send_email(email_data: dict, user_name: str, retry: int = 2) -> bool:
    """
    Sends a finalized AI-generated reply to the actual customer via SMTP.

    Args:
        email_data (dict): Contains "subject", "response", "to" (customer email).
        user_name (str): Your name or signature.
        retry (int): Retry attempts in case of transient SMTP failures.

    Returns:
        bool: True if sent successfully, False otherwise.
    """
    subject = clean_text(email_data.get("subject", ""))
    raw_response = email_data.get("response", "").strip()
    recipient_email = email_data.get("to", "")
    recipient_name = extract_name_from_email(recipient_email)

    formatted_response = format_email(subject, recipient_name, raw_response, user_name)

    msg = EmailMessage()
    msg["Subject"] = f"Re: {subject}"
    msg["From"] = EMAIL_USERNAME
    msg["To"] = recipient_email
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.set_content(formatted_response, subtype="plain", charset="utf-8")

    for attempt in range(retry):
        try:
            logger.debug(f"[Email] Connecting to SMTP {EMAIL_SERVER}:{EMAIL_PORT} (attempt {attempt + 1})")
            with smtplib.SMTP(EMAIL_SERVER, int(EMAIL_PORT), timeout=20) as server:
                server.starttls()
                server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
                server.send_message(msg)
            logger.info(f"[Email] Successfully sent reply to {recipient_email}")
            return True
        except Exception as e:
            logger.warning(f"[Email] Attempt {attempt + 1} failed for {recipient_email}: {e}")
            time.sleep(3)

    logger.error(f"[Email] Failed to send email to {recipient_email} after {retry} attempts.")
    return False
