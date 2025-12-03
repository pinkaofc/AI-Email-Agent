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
# Minimal Firewall
# Only block CLEARLY fabricated operational details:
# - Fake AWB numbers
# - Fake ETAs
# - Fake long phone numbers
# ------------------------------------------------------------

STRICT_PATTERNS = [
    r"\bAWB\s*\d{5,}\b",     # Fake AWB numbers
    r"\bETA\s*\d",          # Unverified ETAs
    r"\bETA[:\- ]+\d",
    r"\b\d{10,}\b",         # Fabricated 10+ digit numbers
]


def _contains_fabrication(text: str) -> bool:
    """Return True only if text contains clearly fabricated operational info."""
    if not text:
        return False

    for pat in STRICT_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True

    return False


# ------------------------------------------------------------
# Clean text helper
# ------------------------------------------------------------
def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


# ------------------------------------------------------------
# Friendly name extraction
# ------------------------------------------------------------
def _derive_friendly_name(recipient_name: str) -> str:
    if not recipient_name:
        return "Customer"

    name = recipient_name.strip()

    # Handle email address → extract readable name
    if "@" in name:
        local = name.split("@")[0]
        parts = re.split(r"[._-]+", local)
        friendly = " ".join(part.capitalize() for part in parts if part)
        return friendly or "Customer"

    # Normal name
    parts = name.split()
    return parts[0].capitalize() if parts else "Customer"


# ------------------------------------------------------------
# FINAL EMAIL FORMATTER (Option-C)
# ------------------------------------------------------------
def format_email(subject: str, recipient_name: str, body: str, user_name: str) -> str:
    cleaned_subject = clean_text(subject)
    cleaned_user = clean_text(user_name)
    cleaned_body = (body or "").strip()

    friendly_name = _derive_friendly_name(recipient_name)

    # ------------------------------------------------------------
    # 1. Minimal hallucination firewall — Option-C
    # Only sanitizes when fabricated numbers/ETAs/AWB found.
    # ------------------------------------------------------------
    if _contains_fabrication(cleaned_body):
        logger.warning("[Formatter] Fabricated operational details detected → sanitizing.")
        try:
            SANITIZATION_TRIGGERED.labels(stage="formatter").inc()
        except Exception:
            pass

        cleaned_body = (
            "Thank you for your message. We have forwarded the details to our operations team. "
            "They will review the request and update you shortly."
        )

    # ------------------------------------------------------------
    # 2. Remove accidental AI-generated greetings
    # ------------------------------------------------------------
    greeting_starters = ["hi", "hello", "dear", "good morning", "good afternoon", "good evening"]

    lines = cleaned_body.splitlines()
    if lines:
        first = lines[0].strip().lower()
        if any(first.startswith(g) for g in greeting_starters):
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)
            cleaned_body = "\n".join(lines).strip()

    # ------------------------------------------------------------
    # 3. Remove AI-generated signatures from Gemini
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
        if cleaned_user.lower() in stripped:  # avoid duplicates
            continue
        filtered.append(line)

    cleaned_body = "\n".join(filtered).strip()

    # Guarantee non-empty
    if not cleaned_body:
        cleaned_body = FALLBACK_RESPONSE

    # ------------------------------------------------------------
    # 4. Final Jinja template
    # ------------------------------------------------------------
    template = Template(
        """Hi {{ recipient_name }},


{{ body }}


Best regards,
{{ user_name }}"""
    )

    formatted = template.render(
        recipient_name=friendly_name,
        body=cleaned_body,
        user_name=cleaned_user,
    )

    logger.info(f"[Formatter] Final email ready for '{friendly_name}' with subject '{cleaned_subject}'.")
    logger.debug(f"[Formatter] Preview:\n{formatted}")

    return formatted.strip()


# ============================================================
# NEW INPUT VALIDATION HELPERS (SAFE & PIPELINE-INDEPENDENT)
# ============================================================

def ask_yes_no(prompt: str) -> bool:
    """
    Safe yes/no input.
    Accepts: y, n, yes, no (any case).
    Repeats until valid.
    """
    valid_yes = {"y", "yes"}
    valid_no = {"n", "no"}

    while True:
        user_input = input(prompt).strip().lower()
        if user_input in valid_yes:
            return True
        if user_input in valid_no:
            return False
        print("Invalid input. Please type y/n or yes/no.")


def ask_positive_int(prompt: str) -> int:
    """
    Only accepts integers >= 1.
    Rejects negative, zero, float, text.
    """
    while True:
        user_input = input(prompt).strip()
        if user_input.isdigit():
            value = int(user_input)
            if value > 0:
                return value
        print("Invalid number. Please enter a positive integer (1, 5, 10...).")
