import re
import warnings
from jinja2 import Template
from utils.logger import get_logger

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

FALLBACK_RESPONSE = (
    "Thank you for reaching out. We’ve received your message and our team will get back to you shortly."
)

# ------------------------------------------------------------
# Sensitive / Operational Leak Patterns (LLM hallucination firewall)
# ------------------------------------------------------------
SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",
    r"\btracking\b",
    r"\btracking number\b",
    r"\brefund\b",
    r"\bdispatch(?:ed)?\b",
    r"\binvestigation\b",
    r"\bwarehouse\b",
    r"\bfulfillment\b",
    r"\border id\b",
    r"\bawb\b",
    r"\bdelivery date\b",
    r"\bexpected delivery\b",
]

def _contains_sensitive(text: str) -> bool:
    if not text:
        return False
    for p in SUSPICIOUS_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


# ------------------------------------------------------------
# Basic Text Cleaner
# ------------------------------------------------------------
def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


# ------------------------------------------------------------
# Friendly Name Constructor
# ------------------------------------------------------------
def _derive_friendly_name(recipient_name: str) -> str:
    if not recipient_name:
        return "Customer"

    recipient_name = recipient_name.strip()

    if "@" in recipient_name:
        local = recipient_name.split("@")[0]
        parts = re.split(r"[._-]+", local)
        friendly = " ".join(p.capitalize() for p in parts if p)
        return friendly or "Customer"

    parts = recipient_name.split()
    return parts[0].capitalize() if parts else "Customer"


# ------------------------------------------------------------
# Email Formatter (Final Output Builder)
# ------------------------------------------------------------
def format_email(subject: str, recipient_name: str, body: str, user_name: str) -> str:
    cleaned_subject = clean_text(subject)
    cleaned_user = clean_text(user_name)
    cleaned_body = (body or "").strip()

    friendly_name = _derive_friendly_name(recipient_name)

    # ------------------------------------------------------------
    # Sanitize dangerous LLM hallucinations
    # ------------------------------------------------------------
    if _contains_sensitive(cleaned_body):
        logger.warning("[Formatter] Sanitizing suspicious operational details from body.")
        cleaned_body = (
            "Thank you for your message. We have forwarded the details to our operations team. "
            "They will review the request and update you shortly."
        )

    # ------------------------------------------------------------
    # Remove greeting lines accidentally included in body
    # ------------------------------------------------------------
    greeting_starters = [
        "hi", "hello", "dear", "good morning", "good afternoon", "good evening",
    ]

    lines = cleaned_body.splitlines()
    if lines:
        first = lines[0].strip().lower()
        if any(first.startswith(g) for g in greeting_starters):
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)
            cleaned_body = "\n".join(lines).strip()

    # ------------------------------------------------------------
    # Remove signatures inserted by Gemini anywhere (not only at end)
    # ------------------------------------------------------------
    signature_patterns = [
        r"^best regards[:,]?$",
        r"^regards[:,]?$",
        r"^sincerely[:,]?$",
        r"^thank you[:,]?$",
        r"^thanks[:,]?$",
    ]

    filtered_lines = []
    for line in cleaned_body.splitlines():
        stripped = line.strip().lower()
        if any(re.match(p, stripped) for p in signature_patterns):
            continue
        if cleaned_user.lower() in stripped:
            continue
        filtered_lines.append(line)

    cleaned_body = "\n".join(filtered_lines).strip()

    # ------------------------------------------------------------
    # Normalize blank spacing
    # ------------------------------------------------------------
    cleaned_body = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned_body)

    # ------------------------------------------------------------
    # Guarantee a non-empty body
    # ------------------------------------------------------------
    if not cleaned_body.strip():
        logger.warning("[Formatter] Cleaned body empty — inserting fallback.")
        cleaned_body = FALLBACK_RESPONSE

    # ------------------------------------------------------------
    # Final Email Template
    # ------------------------------------------------------------
    template = Template(
        """Hi {{ recipient_name }},

{{ body }}

Best regards,
{{ user_name }}"""
    )

    formatted_email = template.render(
        recipient_name=friendly_name,
        body=cleaned_body,
        user_name=cleaned_user,
    )

    logger.info(
        f"[Formatter] Created formatted email for '{friendly_name}' with subject '{cleaned_subject}'."
    )
    logger.debug(f"[Formatter] Final formatted email preview:\n{formatted_email}")

    return formatted_email.strip()
