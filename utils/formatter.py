import re
import warnings
from jinja2 import Template
from utils.logger import get_logger

# Suppress non-critical warnings globally
warnings.filterwarnings("ignore")

logger = get_logger(__name__)

FALLBACK_RESPONSE = (
    "Thank you for reaching out. We’ve received your message and our team will get back to you shortly."
)


def clean_text(text: str) -> str:
    """
    Cleans whitespace and redundant characters from text.
    Ensures AI or raw email content is normalized and tidy.
    """
    if not text:
        return ""
    return " ".join(text.split()).strip()


def _derive_friendly_name(recipient_name: str) -> str:
    """
    Derives a readable name from an email or provided string.
    Examples:
      'raj.malhotra@domain.com' -> 'Raj Malhotra'
      'alex_johnson' -> 'Alex Johnson'
      'Evelyn Harper' -> 'Evelyn'
    """
    if not recipient_name:
        return "Customer"

    recipient_name = recipient_name.strip()
    if "@" in recipient_name:
        local_part = recipient_name.split("@")[0]
        name_parts = re.split(r"[._-]+", local_part)
        friendly = " ".join(part.capitalize() for part in name_parts if part)
        return friendly or "Customer"
    else:
        parts = recipient_name.split()
        return parts[0].capitalize() if parts else "Customer"


def format_email(subject: str, recipient_name: str, body: str, user_name: str) -> str:
    """
    Formats the AI-generated email reply into a clean and consistent structure.

    Args:
        subject (str): The subject of the original email.
        recipient_name (str): The recipient's name or email.
        body (str): The generated email body (raw AI response).
        user_name (str): The AI or support agent's name for the signature.

    Returns:
        str: Fully formatted email text ready for sending.
    """
    cleaned_subject = clean_text(subject)
    cleaned_user = clean_text(user_name)
    cleaned_body = (body or "").strip()

    friendly_recipient_name = _derive_friendly_name(recipient_name)

    # --- Remove duplicated greetings like "Hi John," or "Hello Raj" ---
    greeting_starters = ["hi", "hello", "dear", "good morning", "good afternoon", "good evening"]
    lines = cleaned_body.splitlines()

    if lines:
        first_line = lines[0].strip().lower()
        if any(first_line.startswith(greet) for greet in greeting_starters) and (
            first_line.endswith(",") or " " in first_line
        ):
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)
            cleaned_body = "\n".join(lines).strip()

    # --- Remove redundant closing signatures ---
    signature_phrases = ["best regards", "regards,", "thank you", "sincerely"]
    body_lines = cleaned_body.splitlines()
    while body_lines:
        last_line = body_lines[-1].strip().lower()
        if any(last_line.startswith(phrase) for phrase in signature_phrases) or cleaned_user.lower() in last_line:
            body_lines.pop()
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
        else:
            break
    cleaned_body = "\n".join(body_lines).strip()

    # --- Prevent blank responses ---
    if not cleaned_body:
        logger.warning("[Formatter] Empty body detected — inserting fallback text.")
        cleaned_body = FALLBACK_RESPONSE

    # --- Build final structured email ---
    template = Template(
        """Hi {{ recipient_name }},

{{ body }}

Best regards,
{{ user_name }}"""
    )

    formatted_email = template.render(
        recipient_name=friendly_recipient_name,
        body=cleaned_body,
        user_name=cleaned_user,
    )

    logger.info(
        f"[Formatter] Created formatted email for '{friendly_recipient_name}' with subject '{cleaned_subject}'."
    )
    logger.debug(f"[Formatter] Final formatted email preview:\n{formatted_email}")
    return formatted_email.strip()
