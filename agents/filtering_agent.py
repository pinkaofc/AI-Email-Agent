# agents/filtering_agent.py

import time
import re
from transformers import pipeline
from utils.logger import get_logger
from utils.formatter import clean_text

# Monitoring metrics
from monitoring.metrics import (
    FILTERING_COUNT,
    FILTERING_FAILURES,
    FILTERING_LATENCY,
    FILTERING_MODEL_USED,
    safe_increment_counter,
    safe_observe,
)

logger = get_logger(__name__)

"""
Filtering agent — HuggingFace ONLY
----------------------------------
✓ HF sentiment model only
✓ Proper Prometheus metrics added
✓ Tracks attempts, model used, failures, latency
✓ No Gemini usage
"""

# --------------------------------------------------
# Spam / Promotional keyword lists
# --------------------------------------------------
SPAM_KEYWORDS = [
    "lottery", "win cash", "claim prize", "free money", "work from home",
    "viagra", "buy now", "act now", "limited time", "click here", "buy direct"
]

PROMOTIONAL_KEYWORDS = [
    "sale", "discount", "promo", "subscribe", "newsletter",
    "offer", "deal", "new arrival"
]

# --------------------------------------------------
# Hugging Face Sentiment Model (Primary)
# --------------------------------------------------
try:
    hf_classifier = pipeline(
        "sentiment-analysis",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        revision="af0f99b",
    )
    logger.info("[Filter] HF sentiment model loaded.")
except Exception as e:
    hf_classifier = None
    logger.error(f"[Filter] HF classifier failed to initialize: {e}")


# --------------------------------------------------
# Keyword helper
# --------------------------------------------------
def _contains_keyword_list(text: str, keywords: list) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


# --------------------------------------------------
# Main Entry — HuggingFace ONLY + Metrics
# --------------------------------------------------
def filter_email(email: dict) -> str:
    """
    Classify email as:
    'positive', 'neutral', 'negative', 'spam', 'promotional'
    """

    start_time = time.time()
    safe_increment_counter(FILTERING_COUNT)

    subject = email.get("subject", "") or ""
    content = email.get("body", "") or ""
    combined = f"{subject}\n\n{content}"

    result_label = "neutral"

    try:
        # -------------------------
        # 1. Fast path — Spam
        # -------------------------
        if _contains_keyword_list(combined, SPAM_KEYWORDS):
            result_label = "spam"
            safe_increment_counter(FILTERING_MODEL_USED, model="keyword")
            return result_label

        # -------------------------
        # 2. Fast path — Promotional
        # -------------------------
        if _contains_keyword_list(combined, PROMOTIONAL_KEYWORDS):
            result_label = "promotional"
            safe_increment_counter(FILTERING_MODEL_USED, model="keyword")
            return result_label

        # -------------------------
        # 3. Empty Email → Neutral
        # -------------------------
        if not content.strip():
            result_label = "neutral"
            safe_increment_counter(FILTERING_MODEL_USED, model="keyword")
            return result_label

        # -------------------------
        # 4. HuggingFace Sentiment (Primary)
        # -------------------------
        if hf_classifier:
            hf_res = hf_classifier(content[:500])[0]
            label = hf_res.get("label", "").lower()

            result_label = (
                "negative" if "neg" in label
                else "positive" if "pos" in label
                else "neutral"
            )

            safe_increment_counter(FILTERING_MODEL_USED, model="huggingface")
            return result_label

        # -------------------------
        # 5. No HF model available → fallback to neutral
        # -------------------------
        safe_increment_counter(FILTERING_MODEL_USED, model="fallback")
        result_label = "neutral"
        return result_label

    except Exception as e:
        logger.error(f"[Filter] Unexpected error: {e}")
        safe_increment_counter(FILTERING_FAILURES)
        safe_increment_counter(FILTERING_MODEL_USED, model="fallback")
        result_label = "neutral"
        return result_label

    finally:
        duration = time.time() - start_time
        safe_observe(FILTERING_LATENCY, duration)
        logger.debug(f"[Filter] Completed in {duration:.4f}s → {result_label}")
