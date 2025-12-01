# utils/custom_fallbacks.py
import re
from typing import Optional, List
from utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# INTENT PATTERNS (kept same as provided)
# ============================================================
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


# ============================================================
# INTENT PRIORITY (strongest → weakest)
# ============================================================
INTENT_PRIORITY = [
    "damaged",
    "missing_items",
    "wrong_address",
    "delayed",
    "billing",
    "customs",
    "security",
    "appreciation",
]


# ============================================================
# RESPONSE TEMPLATES
# ============================================================
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
    "default": (
        "Thank you for reaching out. We’ve received your message and our team will get back to you shortly."
    ),
}


# ============================================================
# HELPER — collect *all* matched intents
# ============================================================
def _collect_intents(text: str) -> List[str]:
    matches = []
    if not text:
        return matches

    text = text.lower()

    for intent, patterns in INTENT_PATTERNS.items():
        for p in patterns:
            if re.search(p, text):
                matches.append(intent)
                break

    return matches


# ============================================================
# MAIN FALLBACK SELECTOR (Weighted)
# ============================================================
def get_custom_fallback(summary: str, original_body: str) -> str:
    """
    Returns the strongest intent fallback using weighted priority.
    Example:
      damaged + delayed → damaged
      missing_items + delayed → missing_items
    """

    try:
        combined = " ".join([s for s in (summary or "", original_body or "") if s]).lower()

        # gather all matching intents
        matched_intents = _collect_intents(combined)

        if matched_intents:
            # pick the strongest based on INTENT_PRIORITY
            for strong_intent in INTENT_PRIORITY:
                if strong_intent in matched_intents:
                    logger.info(
                        f"[CustomFallbacks] Weighted intent '{strong_intent}' selected from matches: {matched_intents}"
                    )
                    return TEMPLATES.get(strong_intent, TEMPLATES["default"])

        # keyword fallback (secondary)
        keywords = {
            "damaged": ["damag", "broken", "crush"],
            "missing_items": ["missing", "short", "not received"],
            "wrong_address": ["wrong address", "another address"],
            "delayed": ["delay", "late", "waiting"],
            "billing": ["invoice", "billing", "duplicate"],
        }

        for intent, kws in keywords.items():
            if any(k in combined for k in kws):
                logger.info(f"[CustomFallbacks] Keyword match → '{intent}'")
                return TEMPLATES.get(intent, TEMPLATES["default"])

        # no match
        logger.info("[CustomFallbacks] No intent matched → returning default fallback.")
        return TEMPLATES["default"]

    except Exception as e:
        logger.error(f"[CustomFallbacks] Error selecting fallback: {e}", exc_info=True)
        return TEMPLATES["default"]
