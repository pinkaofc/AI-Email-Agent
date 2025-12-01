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

# Suppress unwanted warnings
warnings.filterwarnings("ignore")

logger = get_logger(__name__)


# ============================================================
#  Utility: Clean Sender Name
# ============================================================
def extract_name_from_email(email_address: str) -> str:
    """
    Extract a clean human-friendly name from an email address.
    """
    if not email_address or "@" not in email_address:
        return "Customer"
    local_part = email_address.split("@")[0]
    name_parts = re.split(r"[._-]+", local_part)
    formatted_name = " ".join(part.capitalize() for part in name_parts if part)
    return formatted_name or "Customer"


# ============================================================
#  SAFETY FIREWALL — Outbound Hallucination Blocker
# ============================================================

SUSPICIOUS_PATTERNS = [
    r"\bETA\b",                   # exact ETA
    r"\bclient address\b",        # PII
    r"\bphone\b",                 # PII
]


SAFE_FALLBACK_MESSAGE = (
    "Thank you for your message. Our team is reviewing your request and will provide "
    "an accurate update shortly."
)


def sanitize_outbound_response(email_body: str) -> (str, bool):
    """
    Returns (safe_body, was_sanitized)

    If AI hallucinated operational or sensitive company info,
    we replace response with a safe fallback and flag it.
    """
    if not email_body:
        return SAFE_FALLBACK_MESSAGE, True

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, email_body, re.IGNORECASE):
            logger.warning(f"[Safety] Outbound response contained suspicious pattern: {pattern}")
            return SAFE_FALLBACK_MESSAGE, True

    return email_body, False


# ============================================================
#  IMAP — Append to Sent
# ============================================================
def append_to_sent_mail(msg: EmailMessage):
    """
    Appends outgoing mail to Gmail "Sent Mail".
    """
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(EMAIL_USERNAME, EMAIL_APP_PASSWORD)
        imap.append(
            '"[Gmail]/Sent Mail"', '\\Seen',
            imaplib.Time2Internaldate(time.time()),
            msg.as_bytes()
        )
        imap.logout()
        logger.info(f"[Email] Appended email to Sent Mail for {msg['To']}")
    except Exception as e:
        logger.warning(f"[Email] Failed to append email to Sent Mail: {e}")


# ============================================================
#  Guarantee Non-Empty Response
# ============================================================
def ensure_non_empty_response(raw_response: str) -> str:
    if not raw_response or not raw_response.strip():
        logger.warning("[Email] Empty AI response — injecting global fallback.")
        return SAFE_FALLBACK_MESSAGE
    return raw_response.strip()


# ============================================================
#  SEND: Draft Email
# ============================================================
def send_draft_to_gmail(
    email_data: dict, user_name: str,
    gmail_address: str, retry: int = 3, cooldown: int = 4
) -> bool:

    subject = clean_text(email_data.get("subject", ""))
    raw_response = ensure_non_empty_response(email_data.get("response", ""))
    customer_email = email_data.get("to", "")
    customer_name = extract_name_from_email(customer_email)

    # Safety layer before building the draft
    safe_body, sanitized = sanitize_outbound_response(raw_response)
    if sanitized:
        logger.warning("[Safety] Draft response sanitized before sending.")

    formatted_response = format_email(subject, customer_name, safe_body, user_name)

    msg = EmailMessage()
    msg["Subject"] = f"Draft: Re: {subject}"
    msg["From"] = EMAIL_USERNAME
    msg["To"] = gmail_address
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.set_content(formatted_response, subtype="plain", charset="utf-8")

    # SMTP sending with retries
    for attempt in range(1, retry + 1):
        try:
            logger.debug(f"[Draft] Connecting SMTP {EMAIL_SERVER}:{EMAIL_PORT} (Attempt {attempt})")
            with smtplib.SMTP(EMAIL_SERVER, int(EMAIL_PORT), timeout=20) as server:
                server.starttls()
                server.login(EMAIL_USERNAME, EMAIL_APP_PASSWORD)
                server.send_message(msg)

            logger.info(f"[Draft] Sent draft of '{subject}' to review inbox: {gmail_address}")
            return True

        except Exception as e:
            logger.warning(f"[Draft] Attempt {attempt} failed: {e}")
            time.sleep(cooldown)

    logger.error(f"[Draft] Failed to send draft after {retry} attempts.")
    return False


# ============================================================
#  SEND: Final Email to Customer
# ============================================================
def send_email(email_data: dict, user_name: str, retry: int = 3, cooldown: int = 5) -> bool:
    subject = clean_text(email_data.get("subject", ""))
    raw_body = ensure_non_empty_response(email_data.get("response", ""))
    recipient_email = email_data.get("to", "")

    if not recipient_email:
        logger.error(f"[Email] Missing recipient email for subject '{subject}'")
        return False

    # NAME HOLDING
    recipient_name = extract_name_from_email(recipient_email)

    # Final outbound safety
    safe_body, sanitized = sanitize_outbound_response(raw_body)
    if sanitized:
        logger.warning("[Safety] Outbound response sanitized before sending.")

    formatted_response = format_email(subject, recipient_name, safe_body, user_name)

    # Build SMTP message
    msg = EmailMessage()
    msg["Subject"] = f"Re: {subject}"
    msg["From"] = EMAIL_USERNAME
    msg["To"] = recipient_email
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.set_content(formatted_response, subtype="plain", charset="utf-8")

    # Retry sending
    for attempt in range(1, retry + 1):
        try:
            logger.debug(f"[Email] Connecting SMTP {EMAIL_SERVER}:{EMAIL_PORT} (Attempt {attempt})")
            with smtplib.SMTP(EMAIL_SERVER, int(EMAIL_PORT), timeout=25) as server:
                server.starttls()
                server.login(EMAIL_USERNAME, EMAIL_APP_PASSWORD)
                server.send_message(msg)

            logger.info(f"[Email] Successfully sent reply to {recipient_email}")

            # Append to Sent Mail for record keeping
            append_to_sent_mail(msg)
            return True

        except Exception as e:
            logger.warning(f"[Email] Attempt {attempt} failed for {recipient_email}: {e}")
            time.sleep(cooldown)

    logger.error(f"[Email] Failed to send after {retry} attempts.")
    return False