import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from bs4 import BeautifulSoup
from utils.logger import get_logger

logger = get_logger(__name__, log_to_file=True)
logger.info("[IMAP] Logger initialized successfully.")


def fetch_imap_emails(email_address, app_password, imap_server, imap_port=993, max_emails=1, mark_as_seen=False):
    """
    Fetches recent unread emails from the IMAP inbox and returns structured, LLM-ready data.

    Args:
        email_address (str): Gmail address used for login.
        app_password (str): Gmail App Password (16-character).
        imap_server (str): IMAP server (usually 'imap.gmail.com').
        imap_port (int): Port (default 993 for SSL).
        max_emails (int): Number of recent emails to fetch.
        mark_as_seen (bool): Whether to mark emails as read.

    Returns:
        list[dict]: Normalized email objects ready for RAG processing.
    """
    mail = None
    emails = []

    try:
        logger.info(f"[IMAP] Connecting to {imap_server}:{imap_port} as {email_address}...")
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(email_address, app_password)
        mail.select("inbox")

        status, messages = mail.search(None, "UNSEEN")
        if status != "OK":
            logger.error(f"[IMAP] Failed to search for unread emails: {messages}")
            return []

        email_ids = messages[0].split()
        if not email_ids:
            logger.info("[IMAP] No unread emails found.")
            return []

        email_ids = email_ids[-max_emails:]
        logger.info(f"[IMAP] Found {len(email_ids)} unread email(s). Fetching...")

        for num in email_ids:
            try:
                status, msg_data = mail.fetch(num, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    logger.warning(f"[IMAP] Failed to fetch email ID {num.decode()}. Skipping.")
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                email_info = parse_email_message(num, msg)

                if not email_info.get("body"):
                    logger.warning(f"[IMAP] Empty body detected for email ID {num.decode()} — skipping.")
                    continue

                emails.append(email_info)

                if mark_as_seen:
                    mail.store(num, "+FLAGS", "\\Seen")
                    logger.debug(f"[IMAP] Marked email ID {num.decode()} as seen.")

            except Exception as e:
                logger.error(f"[IMAP] Error processing email ID {num.decode()}: {e}", exc_info=True)

    except imaplib.IMAP4.error as e:
        logger.error(f"[IMAP] Authentication or server error: {e}")
    except Exception as e:
        logger.error(f"[IMAP] Unexpected error during IMAP fetching: {e}", exc_info=True)
    finally:
        if mail:
            try:
                mail.logout()
                logger.debug("[IMAP] Logged out successfully.")
            except Exception as e:
                logger.warning(f"[IMAP] Error during logout: {e}")

    logger.info(f"[IMAP] Finished fetching {len(emails)} email(s).")
    return emails


# ------------------------------------
# Subfunctions: Parsing and Cleaning
# ------------------------------------
def parse_email_message(num, msg):
    """Extracts structured information from an email message object."""
    email_id = num.decode(errors="ignore")

    # Decode subject safely
    subject = decode_email_subject(msg.get("Subject", "(No Subject)"))

    # Parse sender name and email
    sender_name, sender_email = parseaddr(msg.get("From", "Unknown <unknown@example.com>"))
    sender_name = sender_name or sender_email.split("@")[0].title() if sender_email else "Unknown"
    sender_email = sender_email or "unknown@example.com"

    # Extract timestamp
    timestamp = None
    try:
        if msg.get("Date"):
            timestamp = parsedate_to_datetime(msg["Date"]).isoformat()
    except Exception as e:
        logger.warning(f"[IMAP] Failed to parse timestamp for email ID {email_id}: {e}")

    # Extract and clean body
    body = extract_email_body(msg)
    body_cleaned = clean_email_text(body)

    return {
        "id": email_id,
        "subject": subject,
        "body": body_cleaned,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "timestamp": timestamp,
    }


def decode_email_subject(subject_raw):
    """Handles complex encoded subject headers safely."""
    try:
        decoded_parts = decode_header(subject_raw)
        subject_text = []
        for s, encoding in decoded_parts:
            if isinstance(s, bytes):
                subject_text.append(s.decode(encoding or "utf-8", errors="replace"))
            else:
                subject_text.append(s)
        return "".join(subject_text).strip() or "(No Subject)"
    except Exception as e:
        logger.warning(f"[IMAP] Could not decode subject: {e}")
        return "(No Subject)"


def extract_email_body(msg):
    """
    Extracts the best possible plain-text version of the email body.
    Prioritizes text/plain; falls back to HTML-to-text if necessary.
    """
    plain_texts = []
    html_texts = []

    for part in msg.walk():
        content_type = part.get_content_type()
        disposition = str(part.get("Content-Disposition", "")).lower()

        if "attachment" in disposition:
            continue

        charset = part.get_content_charset() or "utf-8"
        try:
            payload = part.get_payload(decode=True)
            if not payload:
                continue

            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_texts.append(decoded)
            elif content_type == "text/html":
                html_texts.append(decoded)
        except Exception as e:
            logger.debug(f"[IMAP] Skipping undecodable part: {e}")

    if plain_texts:
        return "\n".join(plain_texts).strip()

    # Convert HTML to text if plain text is unavailable
    if html_texts:
        html_combined = "\n".join(html_texts)
        return html_to_text(html_combined)

    return ""


def html_to_text(html_content):
    """Converts HTML email content to plain text using BeautifulSoup."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        text = soup.get_text(separator="\n")
        lines = (line.strip() for line in text.splitlines())
        chunks = [phrase for phrase in lines if phrase]
        return "\n".join(chunks)
    except Exception as e:
        logger.warning(f"[IMAP] HTML parsing failed: {e}")
        return "HTML content detected but could not be converted."


def clean_email_text(text):
    """Removes excessive whitespace, system footers, and reply markers for LLM clarity."""
    if not text:
        return ""

    import re
    text = re.sub(r"(?m)^On .+ wrote:$", "", text)  # remove reply markers
    text = re.sub(r"\s+", " ", text)                # normalize spaces
    text = re.sub(r"(--+|Sent from my .+)$", "", text, flags=re.I)  # remove signatures
    return text.strip()
