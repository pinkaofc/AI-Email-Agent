import smtplib
import imaplib
import time
import re
import email.utils
import warnings
from email.message import EmailMessage
from config import EMAIL_APP_PASSWORD, EMAIL_SERVER, EMAIL_USERNAME, EMAIL_PORT
from utils.logger import get_logger
from utils.formatter import clean_text, format_email

# Suppress startup and future/deprecation warnings
warnings.filterwarnings("ignore")

logger = get_logger(__name__)

# --------------------------------------------------
# Utility: Name Extraction
# --------------------------------------------------
def extract_name_from_email(email_address: str) -> str:
    """
    Extracts a clean name from an email address.
    Example:
        raj.malhotra@malhotragoods.in -> Raj Malhotra
    """
    if not email_address or "@" not in email_address:
        return "Customer"
    local_part = email_address.split("@")[0]
    name_parts = re.split(r"[._-]+", local_part)
    formatted_name = " ".join(part.capitalize() for part in name_parts if part)
    return formatted_name or "Customer"


# --------------------------------------------------
# Append Sent Mail via IMAP
# --------------------------------------------------
def append_to_sent_mail(msg: EmailMessage):
    """
    Appends a copy of the sent email to Gmail's 'Sent Mail' folder using IMAP.
    Requires IMAP to be enabled in Gmail settings.
    """
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(EMAIL_USERNAME, EMAIL_APP_PASSWORD)
        imap.append('"[Gmail]/Sent Mail"', '\\Seen', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        imap.logout()
        logger.info(f"[Email]  Appended email to Sent Mail for {msg['To']}")
    except Exception as e:
        logger.warning(f"[Email]  Failed to append email to Sent Mail: {e}")


# --------------------------------------------------
# Helper: Guarantee Non-empty Response
# --------------------------------------------------
def ensure_non_empty_response(raw_response: str) -> str:
    """
    Ensures the email body is never blank by providing a fallback message.
    """
    if not raw_response or not raw_response.strip():
        logger.warning("[Email] Empty or missing AI response — using fallback message.")
        return "Thank you for reaching out. We’ve received your message and our team will get back to you shortly."
    return raw_response.strip()


# --------------------------------------------------
# Send Draft Email (for review/testing)
# --------------------------------------------------
def send_draft_to_gmail(email_data: dict, user_name: str, gmail_address: str, retry: int = 3, cooldown: int = 4) -> bool:
    subject = clean_text(email_data.get("subject", ""))
    raw_response = ensure_non_empty_response(email_data.get("response", ""))
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

    for attempt in range(1, retry + 1):
        try:
            logger.debug(f"[Draft] Connecting to SMTP {EMAIL_SERVER}:{EMAIL_PORT} (Attempt {attempt})")
            with smtplib.SMTP(EMAIL_SERVER, int(EMAIL_PORT), timeout=20) as server:
                server.starttls()
                server.login(EMAIL_USERNAME, EMAIL_APP_PASSWORD)
                server.send_message(msg)
            logger.info(f"[Draft] Sent draft email '{subject}' to review inbox: {gmail_address}")
            time.sleep(2)
            return True
        except Exception as e:
            logger.warning(f"[Draft] Attempt {attempt} failed: {e}")
            time.sleep(cooldown)

    logger.error(f"[Draft] Failed to send draft email after {retry} attempts.")
    return False


# --------------------------------------------------
# Send Final Email (to Customer + Append to Sent)
# --------------------------------------------------
def send_email(email_data: dict, user_name: str, retry: int = 3, cooldown: int = 5) -> bool:
    """
    Sends an AI-generated reply directly to the customer and appends it to Gmail's Sent Mail.
    """
    subject = clean_text(email_data.get("subject", ""))
    raw_response = ensure_non_empty_response(email_data.get("response", ""))
    recipient_email = email_data.get("to", "")

    if not recipient_email:
        logger.error(f"[Email] Missing recipient email for subject: '{subject}'")
        return False

    recipient_name = extract_name_from_email(recipient_email)
    formatted_response = format_email(subject, recipient_name, raw_response, user_name)

    msg = EmailMessage()
    msg["Subject"] = f"Re: {subject}"
    msg["From"] = EMAIL_USERNAME
    msg["To"] = recipient_email
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.set_content(formatted_response, subtype="plain", charset="utf-8")

    for attempt in range(1, retry + 1):
        try:
            logger.debug(f"[Email] Connecting to SMTP {EMAIL_SERVER}:{EMAIL_PORT} (Attempt {attempt})")
            with smtplib.SMTP(EMAIL_SERVER, int(EMAIL_PORT), timeout=25) as server:
                server.starttls()
                server.login(EMAIL_USERNAME, EMAIL_APP_PASSWORD)
                server.send_message(msg)
            logger.info(f"[Email] Successfully sent reply to {recipient_email}")

            # Append to Sent Mail
            append_to_sent_mail(msg)

            time.sleep(3)
            return True
        except Exception as e:
            logger.warning(f"[Email] Attempt {attempt} failed for {recipient_email}: {e}")
            time.sleep(cooldown)

    logger.error(f"[Email] Failed to send email to {recipient_email} after {retry} attempts.")
    return False
