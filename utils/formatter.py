import re
import warnings
from jinja2 import Template
from utils.logger import get_logger

# Prometheus safety metric
from monitoring.metrics import SANITIZATION_TRIGGERED

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
    """Detect fabricated or operational hallucinations."""
    if not text:
        return False
    for p in SUSPICIOUS_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


# ------------------------------------------------------------
# Basic cleaner
# ------------------------------------------------------------
def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


# ------------------------------------------------------------
# Friendly name builder
# ------------------------------------------------------------
def _derive_friendly_name(recipient_name: str) -> str:
    if not recipient_name:
        return "Customer"

    name = recipient_name.strip()

    # Email address → extract readable name
    if "@" in name:
        local = name.split("@")[0]
        parts = re.split(r"[._-]+", local)
        friendly = " ".join(p.capitalize() for p in parts if p)
        return friendly or "Customer"

    # Normal name
    parts = name.split()
    return parts[0].capitalize() if parts else "Customer"


# ------------------------------------------------------------
# FINAL EMAIL FORMATTER
# ------------------------------------------------------------
def format_email(subject: str, recipient_name: str, body: str, user_name: str) -> str:
    """
    Build the final email with greeting + signature.
    Cleans hallucinated details + accidental LLM formatting problems.
    """
    cleaned_subject = clean_text(subject)
    cleaned_user = clean_text(user_name)
    cleaned_body = (body or "").strip()

    friendly_name = _derive_friendly_name(recipient_name)

    # ------------------------------------------------------------
    # 1. FIREWALL: Sanitize hallucinated operational content
    # ------------------------------------------------------------
    if _contains_sensitive(cleaned_body):
        logger.warning("[Formatter] Sensitive/hallucinated details detected → sanitizing.")
        try:
            SANITIZATION_TRIGGERED.labels(stage="formatter").inc()
        except Exception:
            pass

        cleaned_body = (
            "Thank you for your message. We have forwarded the details to our operations team. "
            "They will review the request and update you shortly."
        )

    # ------------------------------------------------------------
    # 2. Remove accidental greetings added by Gemini
    # ------------------------------------------------------------
    greeting_starters = [
        "hi",
        "hello",
        "dear",
        "good morning",
        "good afternoon",
        "good evening",
    ]

    lines = cleaned_body.splitlines()
    if lines:
        first = lines[0].strip().lower()
        if any(first.startswith(g) for g in greeting_starters):
            lines = lines[1:]
            # Remove blank lines after greeting
            while lines and not lines[0].strip():
                lines.pop(0)
            cleaned_body = "\n".join(lines).strip()

    # ------------------------------------------------------------
    # 3. Remove AI-generated signatures
    # ------------------------------------------------------------
    signature_patterns = [
        r"^best regards[:,]?$",
        r"^regards[:,]?$",
        r"^sincerely[:,]?$",
        r"^thank you[:,]?$",
        r"^thanks[:,]?$",
    ]

    filtered = []
    for line in cleaned_body.splitlines():
        stripped = line.strip().lower()
        if any(re.match(p, stripped) for p in signature_patterns):
            continue
        if cleaned_user.lower() in stripped:
            continue
        filtered.append(line)

    cleaned_body = "\n".join(filtered).strip()

    # ------------------------------------------------------------
    # 4. Normalize extra spacing
    # ------------------------------------------------------------
    cleaned_body = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned_body)

    # ------------------------------------------------------------
    # 5. Guarantee non-empty output
    # ------------------------------------------------------------
    if not cleaned_body.strip():
        logger.warning("[Formatter] Cleaned body empty — inserting fallback.")
        cleaned_body = FALLBACK_RESPONSE

    # ------------------------------------------------------------
    # 6. Final Jinja2 Template
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
        f"[Formatter] Final email ready for '{friendly_name}' with subject '{cleaned_subject}'."
    )
    logger.debug(f"[Formatter] Preview:\n{formatted_email}")

    return formatted_email.strip()
