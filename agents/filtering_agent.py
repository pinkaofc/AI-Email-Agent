# agents/filtering_agent.py

import time
import random
import re
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from transformers import pipeline

from config import get_gemini_api_key
from utils.logger import get_logger
from utils.formatter import clean_text
from utils.rate_limit_guard import rate_limit_safe_call

# NEW: Monitoring metrics (correct imports)
from monitoring.metrics import (
    GEMINI_CALLS,
    GEMINI_FAILURES,
    GEMINI_FALLBACK_USED,
    EMAIL_CLASSIFICATION_COUNTER,
)

logger = get_logger(__name__)

"""
Filtering agent:
- Fast path keyword checks (spam/promotional)
- Primary sentiment classification via Gemini (with monitoring)
- HF fallback
- Safe final fallback
"""

# --------------------------------------------------
# Spam / Promotional keyword lists
# --------------------------------------------------
SPAM_KEYWORDS = [
    "lottery", "win cash", "claim prize", "free money", "work from home",
    "viagra", "buy now", "act now", "limited time", "click here", "buy direct"
]
PROMOTIONAL_KEYWORDS = [
    "sale", "discount", "promo", "subscribe", "newsletter", "offer", "deal", "new arrival"
]

# --------------------------------------------------
# Hugging Face fallback sentiment model (pinned)
# --------------------------------------------------
try:
    hf_classifier = pipeline(
        "sentiment-analysis",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        revision="af0f99b",
    )
    logger.info("[Filter] HF fallback sentiment model loaded.")
except Exception as e:
    hf_classifier = None
    logger.error(f"[Filter] HF fallback model failed to initialize: {e}")


# --------------------------------------------------
# Gemini sentiment classifier (with monitoring)
# --------------------------------------------------
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    """
    Attempt to get a single-word sentiment label from Gemini.
    Emits monitoring metrics for calls/failures/fallback usage.
    """
    for attempt in range(1, retry_attempts + 1):

        api_key = get_gemini_api_key()
        # Count attempt (we call this before invoking)
        try:
            GEMINI_CALLS.labels(module="filtering").inc()
        except Exception:
            pass

        logger.info(
            f"[Filter] Gemini attempt {attempt}/{retry_attempts} using key {api_key[:6]}..."
        )

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.0,
                google_api_key=api_key,
            )

            # IMPORTANT: do not pass monitoring kwargs into model.invoke
            result_obj = rate_limit_safe_call(
                model.invoke,
                prompt
            )

            # result_obj may be an object — access .content if present
            raw = getattr(result_obj, "content", result_obj)
            sentiment_text = clean_text(raw).strip().lower()
            logger.debug(f"[Filter] Raw Gemini output: {sentiment_text!r}")

            if sentiment_text.startswith("neg"):
                return "negative"
            if sentiment_text in ("positive", "neutral", "negative"):
                return sentiment_text

            logger.warning("[Filter] Unexpected Gemini output → defaulting to 'neutral'.")
            return "neutral"

        except Exception as e:
            err = str(e).lower()
            reason = (err[:80]) if err else "unknown"

            # record failure and fallback usage
            try:
                GEMINI_FAILURES.labels(module="filtering", reason=reason).inc()
                GEMINI_FALLBACK_USED.labels(module="filtering").inc()
            except Exception:
                pass

            # rotate on quota/429
            if "429" in err or "quota" in err:
                logger.warning("[Filter] Gemini quota/429 detected — rotating key and retrying.")
                continue

            logger.error(f"[Filter] Gemini unrecoverable error: {e}")
            # escalate unrecoverable error upward to allow HF fallback to run
            raise e

    raise RuntimeError("Gemini sentiment classification failed after retries.")


# --------------------------------------------------
# Helper
# --------------------------------------------------
def _contains_keyword_list(text: str, keywords: list) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


# --------------------------------------------------
# Main Entry Point
# --------------------------------------------------
def filter_email(email: dict) -> str:
    """
    Classify the incoming email into one of:
      - 'positive', 'neutral', 'negative', 'spam', 'promotional'
    This function ensures metrics are incremented for important outcomes.
    """
    subject = email.get("subject", "") or ""
    content = email.get("body", "") or ""
    combined = f"{subject}\n\n{content}"

    # ---------------------------------------
    # Fast path → Spam
    # ---------------------------------------
    if _contains_keyword_list(combined, SPAM_KEYWORDS):
        try:
            EMAIL_CLASSIFICATION_COUNTER.labels(classification="spam").inc()
        except Exception:
            pass
        return "spam"

    # ---------------------------------------
    # Fast path → Promotional
    # ---------------------------------------
    if _contains_keyword_list(combined, PROMOTIONAL_KEYWORDS):
        try:
            EMAIL_CLASSIFICATION_COUNTER.labels(classification="promotional").inc()
        except Exception:
            pass
        return "promotional"

    # ---------------------------------------
    # Empty email
    # ---------------------------------------
    if not content.strip():
        try:
            EMAIL_CLASSIFICATION_COUNTER.labels(classification="neutral").inc()
        except Exception:
            pass
        return "neutral"

    # ---------------------------------------
    # Build Gemini prompt
    # ---------------------------------------
    prompt = PromptTemplate(
        input_variables=["subject", "content"],
        template=(
            "Analyze this email and classify its overall sentiment as "
            "'positive', 'neutral', or 'negative'. Reply ONLY with the label.\n\n"
            "Subject: {subject}\n"
            "Content: {content}\n"
            "Sentiment:"
        ),
    ).format(subject=subject, content=content)

    # ---------------------------------------
    # Try Gemini First
    # ---------------------------------------
    try:
        sentiment = _use_gemini(prompt)
        try:
            EMAIL_CLASSIFICATION_COUNTER.labels(classification=sentiment).inc()
        except Exception:
            pass
        return sentiment

    except Exception as e:
        logger.warning(f"[Filter] Gemini failed — will try HuggingFace fallback: {e}")

    # ---------------------------------------
    # HuggingFace fallback
    # ---------------------------------------
    if hf_classifier:
        try:
            result = hf_classifier(content[:500])[0]
            label = result.get("label", "").lower()

            sentiment = (
                "negative" if "neg" in label
                else "positive" if "pos" in label
                else "neutral"
            )

            try:
                GEMINI_FALLBACK_USED.labels(module="filtering").inc()
                EMAIL_CLASSIFICATION_COUNTER.labels(classification=sentiment).inc()
            except Exception:
                pass

            return sentiment

        except Exception as e:
            logger.error(f"[Filter] HF fallback failed: {e}")

    # ---------------------------------------
    # Final fallback
    # ---------------------------------------
    try:
        GEMINI_FALLBACK_USED.labels(module="filtering").inc()
        EMAIL_CLASSIFICATION_COUNTER.labels(classification="neutral").inc()
    except Exception:
        pass

    return "neutral"
