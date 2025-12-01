# utils/human_review.py

import re
from utils.logger import get_logger

logger = get_logger(__name__)

"""
Human Review Logic 
-----------------------------
Only flag for review when:

  • Dangerous hallucinations exist
  • Promises of delivery dates, numbers, ETA, or commitments
  • Fake IDs not present in original email
  • Security-risk content appears

NOT flagged:
  • tone issues
  • generic operational statements
  • normal replies
"""

# ------------------------------------------------------
# Truly dangerous patterns (strict + minimal)
# ------------------------------------------------------
DANGEROUS_PATTERNS = [
    r"\bAWB\s*\d+",                   # fabricated airway bill
    r"\bETA\s*\d",                    # fake ETA
    r"\bETA[:\- ]+\d",                # ETA: 22
    r"\b\d{10,}\b",                   # suspicious phone number
]

# ------------------------------------------------------
# Promises that AI must not invent
# ------------------------------------------------------
PROMISE_PATTERNS = [
    r"\bwill\s+arrive\b",
    r"\bwill\s+deliver\b",
    r"\bby\s+\d{1,2}\s+\w+",          # by 12 March
    r"\bexpected\s+on\b",
    r"\bdelivery\s+on\b",
]

# ------------------------------------------------------
# Security red flags
# ------------------------------------------------------
SECURITY_PATTERNS = [
    r"click\s+here",
    r"login\s+here",
    r"verify\s+your\s+account",
    r"enter\s+your\s+card",
]

# Combined for scanning
ALL_REVIEW_PATTERNS = (
    DANGEROUS_PATTERNS +
    PROMISE_PATTERNS +
    SECURITY_PATTERNS
)


def requires_human_review(response: str, original_email: str) -> bool:
    """
    Returns TRUE only when human review is *strictly needed*.
    """

    if not response or len(response.strip()) < 20:
        return True  # Too short → unsafe

    # ---- Step 1: dangerous hallucinations ----
    for p in DANGEROUS_PATTERNS:
        if re.search(p, response, re.IGNORECASE):
            logger.warning(f"[HumanReview] Dangerous hallucination detected: {p}")
            return True

    # ---- Step 2: hallucinated IDs ----
    # Extract actual IDs from customer email
    real_ids = {
        oid.upper().replace(" ", "")
        for oid in re.findall(r"\b(?:SC|PO|ORDER|INVOICE)[-\s]?[A-Z0-9]{4,10}\b",
                              original_email,
                              flags=re.IGNORECASE)
    }

    # Extract IDs mentioned in response
    model_ids = {
        oid.upper().replace(" ", "")
        for oid in re.findall(r"\b(?:SC|PO|ORDER|INVOICE)[-\s]?[A-Z0-9]{4,10}\b",
                              response,
                              flags=re.IGNORECASE)
    }

    for mid in model_ids:
        if mid not in real_ids:
            logger.warning(f"[HumanReview] Hallucinated order ID in response: {mid}")
            return True

    # ---- Step 3: fabricated promises ----
    for p in PROMISE_PATTERNS:
        if re.search(p, response, re.IGNORECASE):
            logger.warning(f"[HumanReview] AI invented a promise: {p}")
            return True

    # ---- Step 4: security triggers ----
    for p in SECURITY_PATTERNS:
        if re.search(p, response, re.IGNORECASE):
            logger.warning(f"[HumanReview] Suspicious/phishy phrase detected: {p}")
            return True

    # If none of the above → safe
    return False


# ------------------------------------------------------
# Extract helpful review snippets
# ------------------------------------------------------
def get_review_snippets(response: str):
    snippets = []

    for p in ALL_REVIEW_PATTERNS:
        for match in re.finditer(p, response, re.IGNORECASE):
            start = max(0, match.start() - 25)
            end = min(len(response), match.end() + 25)
            snippets.append(response[start:end])

    return list(dict.fromkeys(snippets))
