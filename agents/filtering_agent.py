import time
import random
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from transformers import pipeline
from config import get_gemini_api_key
from utils.logger import get_logger
from utils.formatter import clean_text
from utils.rate_limit_guard import rate_limit_safe_call  # new import
import re

logger = get_logger(__name__)

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
# Initialize Hugging Face fallback sentiment model
# (Pinned to avoid warnings & ensure deterministic output)
# --------------------------------------------------
try:
    hf_classifier = pipeline(
        "sentiment-analysis",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        revision="af0f99b",
    )
    logger.info("[Filter] Hugging Face sentiment model loaded successfully (pinned).")
except Exception as e:
    hf_classifier = None
    logger.error(f"[Filter] Failed to initialize Hugging Face fallback model: {e}")


# --------------------------------------------------
# Gemini Sentiment Helper (with Rate-Limit Guard)
# --------------------------------------------------
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    """
    Handles Gemini sentiment classification with retry logic,
    automatic key rotation, and rate-limit safety.
    Returns one of: 'positive', 'neutral', 'negative'.
    """

    for attempt in range(1, retry_attempts + 1):
        api_key = get_gemini_api_key()
        logger.info(
            f"[Filter] Using Gemini API key attempt {attempt}/{retry_attempts} -> {api_key[:6]}..."
        )

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.0,
                google_api_key=api_key,
            )

            result_obj = rate_limit_safe_call(model.invoke, prompt)
            sentiment_text = clean_text(result_obj.content).strip().lower()

            logger.debug(f"[Filter] Raw Gemini output: {sentiment_text!r}")

            # Strict normalization
            if sentiment_text in ["positive", "neg", "negative", "neutral"]:
                if sentiment_text.startswith("neg"):
                    return "negative"
                return sentiment_text

            logger.warning(f"[Filter] Unexpected Gemini output '{sentiment_text}' — defaulting to 'neutral'.")
            return "neutral"

        except Exception as e:
            error_message = str(e).lower()

            # Quota or 429 → rotate API key and retry
            if "quota" in error_message or "429" in error_message:
                logger.warning(
                    f"[Filter] Gemini quota exceeded for key {api_key[:6]} — rotating and retrying."
                )
                continue

            logger.error(f"[Filter] Gemini API error: {e}")
            raise e

    raise RuntimeError("Gemini sentiment classification failed after all retries.")


# --------------------------------------------------
# Helper: quick keyword detector
# --------------------------------------------------
def _contains_keyword_list(text: str, keywords: list) -> bool:
    t = (text or "").lower()
    for k in keywords:
        if k in t:
            return True
    return False


# --------------------------------------------------
# Main Entry Point (Sentiment Classification)
# --------------------------------------------------
def filter_email(email: dict) -> str:
    """
    Classifies email sentiment or category as:
        'positive', 'neutral', 'negative', 'spam', or 'promotional'

    Uses:
      - quick keyword spam/promotional detection (fast path)
      - Gemini first (with rate-limits, retries, key-rotation)
      - Falls back to HuggingFace pinned model on failure
    """

    subject = email.get("subject", "") or ""
    content = email.get("body", "") or ""
    combined = f"{subject}\n\n{content}"

    # Quick checks first (fast path)
    # Spam detection (explicit)
    if _contains_keyword_list(combined, SPAM_KEYWORDS):
        logger.info("[Filter] Spam keyword matched — marking as 'spam'.")
        return "spam"

    # Promotional detection
    if _contains_keyword_list(combined, PROMOTIONAL_KEYWORDS):
        logger.info("[Filter] Promotional keyword matched — marking as 'promotional'.")
        return "promotional"

    # Empty content
    if not content.strip():
        logger.warning("[Filter] Empty email body detected — returning 'neutral'.")
        return "neutral"

    # Gemini prompt
    prompt_template = PromptTemplate(
        input_variables=["subject", "content"],
        template=(
            "Analyze the following email and classify its overall sentiment as "
            "'positive', 'neutral', or 'negative'. Respond with ONLY the label.\n\n"
            "Subject: {subject}\n"
            "Content: {content}\n"
            "Sentiment:"
        ),
    )

    prompt = prompt_template.format(subject=subject, content=content)

    # --------------------------------------------------
    # Try Gemini first
    # --------------------------------------------------
    try:
        sentiment = _use_gemini(prompt)
        logger.info(f"[Filter] Sentiment classified via Gemini: {sentiment}")
        return sentiment

    except Exception as e:
        logger.warning(f"[Filter] Gemini failed ({e}) — falling back to Hugging Face local model.")

    # --------------------------------------------------
    # Hugging Face Fallback
    # --------------------------------------------------
    if hf_classifier:
        try:
            result = hf_classifier(content[:500])[0]
            label = result.get("label", "").lower()

            sentiment = (
                "negative" if "neg" in label
                else "positive" if "pos" in label
                else "neutral"
            )

            logger.info(f"[Filter] Sentiment classified via HuggingFace fallback: {sentiment}")
            return sentiment

        except Exception as hf_error:
            logger.error(f"[Filter] HuggingFace fallback failed: {hf_error}")
            return "neutral"

    # No fallback model available
    logger.warning("[Filter] No fallback sentiment model available — returning 'neutral'.")
    return "neutral"
