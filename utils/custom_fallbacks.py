# utils/custom_fallbacks.py
import re
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)

# Minimal set of intent patterns → expand as you like
INTENT_PATTERNS = {
    "appreciation": [r"\bthank(s| you)\b", r"\bappreciat", r"\bexcellent\b", r"\bdelight(ed)?\b"],
    "missing_items": [r"\bmissing\b", r"\bshortage\b", r"\bnot received\b", r"\bmissing items\b"],
    "wrong_address": [r"\bwrong address\b", r"\bdelivered to another\b", r"\bwrongly delivered\b"],
    "delayed": [r"\bdelay", r"\bdelayed\b", r"\bout for delivery\b", r"\bover a week\b", r"\bnot arrived\b"],
    "damaged": [r"\bdamag", r"\bdamaged\b", r"\bbroken\b", r"\bcrush(ed)?\b"],
    "billing": [r"\binvoice\b", r"\bbilling\b", r"\bcharge\b", r"\bduplicate invoice\b"],
    "customs": [r"\bcustoms\b", r"\bdocumentation\b", r"\bcommercial invoice\b"],
    "security": [r"\bclick the link\b", r"\bprovide your card\b", r"\blogin\b", r"\bphish\b", r"\bcard details\b"],
}

# Templates keyed by intent. Keep these safe — no operational promises.
TEMPLATES = {
    "appreciation": (
        "Thank you for your kind message. We're delighted your order arrived ahead of schedule — "
        "your feedback has been shared with our team. We appreciate your business and look forward to serving you again."
    ),
    "missing_items": (
        "Thanks for letting us know. We’re sorry to hear items are missing. "
        "We’ve forwarded your message to our operations team for verification. "
        "They will review the dispatch records and get back to you with the next steps."
    ),
    "wrong_address": (
        "We’re sorry for the inconvenience. The operations team has been notified and will investigate the delivery details. "
        "We will update you as soon as we have more information."
    ),
    "delayed": (
        "Thank you for reaching out. We understand the urgency — our operations team is checking the shipment status and will provide an update shortly."
    ),
    "damaged": (
        "We apologize for the damaged items. Please share photos and the shipment details if available. "
        "Our returns & claims team will review and advise on the replacement or claims process."
    ),
    "billing": (
        "Thanks for raising this billing concern. We have forwarded the invoice details to our Finance team; they will verify and provide a corrected invoice if needed."
    ),
    "customs": (
        "Thanks for the heads up. Our export team will re-check the documentation and share the required commercial invoice or declaration with you shortly."
    ),
    "security": (
        "This message looks suspicious. For your safety, do not share login or card details via email. "
        "Please confirm the sender's email and we will investigate further."
    ),
    # generic fallback if nothing matches
    "default": (
        "Thank you for reaching out. We’ve received your message and our team will get back to you shortly."
    ),
}

def _match_intent(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        for p in patterns:
            if re.search(p, text):
                return intent
    return None

def get_custom_fallback(summary: str, original_body: str) -> str:
    """
    Return a safe fallback template chosen by matching the summary or original email body.
    - summary: the sanitized summary string (may include intent clues)
    - original_body: the raw email body (used when summary is generic)
    """
    try:
        combined = " ".join([s for s in (summary or "", original_body or "") if s]).lower()

        intent = _match_intent(combined)
        if intent and intent in TEMPLATES:
            logger.info(f"[CustomFallbacks] Matched intent '{intent}' → returning template.")
            return TEMPLATES[intent]

        # second pass: less strict heuristics (keywords)
        keywords = {
            "appreciation": ["thank", "appreciate", "excellent", "delighted"],
            "delayed": ["delay", "delayed", "late"],
            "missing_items": ["missing", "short", "not received"],
            "damaged": ["damag", "broken", "crush"],
            "billing": ["invoice", "billing", "duplicate"]
        }
        for k, kws in keywords.items():
            if any(kw in combined for kw in kws):
                logger.info(f"[CustomFallbacks] Keyword match '{k}' → returning template.")
                return TEMPLATES.get(k, TEMPLATES["default"])

        logger.info("[CustomFallbacks] No strong match found → returning default fallback.")
        return TEMPLATES["default"]

    except Exception as e:
        logger.error(f"[CustomFallbacks] Error selecting fallback: {e}", exc_info=True)
        return TEMPLATES["default"]
