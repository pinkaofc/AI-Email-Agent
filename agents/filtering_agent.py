import time
import random
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from transformers import pipeline
from config import get_gemini_api_key
from utils.logger import get_logger
from utils.formatter import clean_text
from utils.rate_limit_guard import rate_limit_safe_call  #  new import

logger = get_logger(__name__)

# --------------------------------------------------
# Initialize Hugging Face fallback sentiment model
# --------------------------------------------------
try:
    hf_classifier = pipeline("sentiment-analysis")
    logger.info("[Filter] Hugging Face sentiment model loaded successfully.")
except Exception as e:
    hf_classifier = None
    logger.error(f"[Filter] Failed to initialize Hugging Face model: {e}")


# --------------------------------------------------
# Gemini Sentiment Helper (with Rate-Limit Guard)
# --------------------------------------------------
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    """
    Handles Gemini sentiment classification with automatic
    rate-limit handling and key rotation.
    """
    for attempt in range(1, retry_attempts + 1):
        api_key = get_gemini_api_key()
        logger.info(f"[Filter] Using Gemini API key #{attempt}/{retry_attempts} -> {api_key[:6]}...")

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.0,
                google_api_key=api_key,
            )

            #  Run Gemini safely under rate-limit control
            sentiment_result = rate_limit_safe_call(model.invoke, prompt)
            sentiment_text = clean_text(sentiment_result.content).strip().lower()
            logger.debug("[Filter] Raw Gemini output: %s", sentiment_text)

            if sentiment_text not in ["positive", "neutral", "negative"]:
                logger.warning("[Filter] Unexpected Gemini output '%s'. Defaulting to 'neutral'.", sentiment_text)
                sentiment_text = "neutral"

            return sentiment_text

        except Exception as e:
            error_message = str(e).lower()
            if "quota" in error_message or "429" in error_message:
                logger.warning(f"[Filter] Gemini quota exceeded for key {api_key[:6]} — rotating key and retrying.")
                continue
            logger.error(f"[Filter] Gemini API error (non-quota): {e}")
            raise e

    raise RuntimeError("Gemini sentiment classification failed after all retries.")


# --------------------------------------------------
# Main Entry Point
# --------------------------------------------------
def filter_email(email: dict) -> str:
    """
    Analyzes email sentiment using Gemini API with Hugging Face fallback.
    Categories: 'positive', 'neutral', 'negative'.
    """
    subject = email.get("subject", "")
    content = email.get("body", "")

    if not content.strip():
        logger.warning("[Filter] Empty email body detected — returning 'neutral'.")
        return "neutral"

    # Create prompt for Gemini
    prompt_template = PromptTemplate(
        input_variables=["subject", "content"],
        template=(
            "Analyze the following email and classify its overall sentiment as "
            "'positive', 'neutral', or 'negative'. Respond with only the label.\n\n"
            "Subject: {subject}\n"
            "Content: {content}\n"
            "Sentiment:"
        ),
    )
    prompt = prompt_template.format(subject=subject, content=content)

    # --------------------------------------------------
    # Try Gemini first (with rate-limit safety)
    # --------------------------------------------------
    try:
        sentiment = _use_gemini(prompt)
        logger.info(f"[Filter] Sentiment classified via Gemini: {sentiment}")
        return sentiment
    except Exception as e:
        logger.warning(f"[Filter] Gemini failed: {e}. Falling back to Hugging Face.")

    # --------------------------------------------------
    # Fallback to Hugging Face local model
    # --------------------------------------------------
    if hf_classifier:
        try:
            hf_result = hf_classifier(content[:500])[0]
            label = hf_result["label"].lower()
            sentiment = (
                "negative" if "neg" in label else
                "positive" if "pos" in label else
                "neutral"
            )
            logger.info(f"[Filter] Sentiment classified via Hugging Face fallback: {sentiment}")
            return sentiment
        except Exception as hf_error:
            logger.error(f"[Filter] Hugging Face sentiment analysis failed: {hf_error}")
            return "neutral"
    else:
        logger.warning("[Filter] No fallback model available. Returning 'neutral'.")
        return "neutral"
