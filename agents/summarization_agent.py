import time
import random
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from transformers import pipeline
from utils.formatter import clean_text
from config import get_gemini_api_key
from utils.logger import get_logger
from utils.rate_limit_guard import rate_limit_safe_call  # added for rate-limit handling

logger = get_logger(__name__)

# --------------------------------------------------
# Initialize Hugging Face fallback summarization model
# --------------------------------------------------
try:
    hf_summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
    logger.info("[Summarization] Hugging Face fallback model loaded successfully.")
except Exception as e:
    hf_summarizer = None
    logger.error(f"[Summarization] Failed to initialize fallback model: {e}")


# --------------------------------------------------
# Gemini Summarizer with Rate-Limit Guard
# --------------------------------------------------
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    """
    Generates a summary using Gemini with automatic rate-limit handling
    and API key rotation.
    """
    for attempt in range(1, retry_attempts + 1):
        api_key = get_gemini_api_key()
        logger.info(f"[Summarization] Attempt {attempt}/{retry_attempts} using Gemini key: {api_key[:6]}...")

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.5,
                google_api_key=api_key,
            )

            # Wrap call with rate-limit safety
            result = rate_limit_safe_call(model.invoke, prompt)
            summary_text = clean_text(result.content).strip()

            if not summary_text:
                raise ValueError("Empty summary from Gemini")

            return summary_text

        except Exception as e:
            error_message = str(e).lower()

            if "quota" in error_message or "429" in error_message:
                logger.warning(f"[Summarization] Gemini quota exceeded for key {api_key[:6]} — retrying after delay.")
                continue

            if "timeout" in error_message or "network" in error_message:
                logger.warning("[Summarization] Temporary network issue, retrying in 5s.")
                time.sleep(5)
                continue

            logger.error(f"[Summarization] Gemini API error: {e}")
            raise e

    raise RuntimeError("Gemini summarization failed after all retries.")


# --------------------------------------------------
# Public Entry Point
# --------------------------------------------------
def summarize_email(email: dict) -> str:
    """
    Summarizes an email using Gemini, with Hugging Face fallback.
    Produces a concise 2–3 sentence summary describing the customer's intent or issue.
    """
    content = email.get("body", "").strip()
    if not content:
        logger.warning("[Summarization] Empty email content detected.")
        return "No content to summarize."

    prompt_template = PromptTemplate(
        input_variables=["content"],
        template="Summarize this customer email briefly and clearly in 2 to 3 sentences:\n\n{content}",
    )

    prompt = prompt_template.format(content=content)

    # --------------------------------------------------
    # Try Gemini first (rate-limit safe)
    # --------------------------------------------------
    try:
        summary = _use_gemini(prompt)
        logger.debug(f"[Summarization] Raw Gemini output: {summary}")
        return summary

    except Exception as e:
        logger.warning(f"[Summarization] Gemini summarization failed: {e}")

    # --------------------------------------------------
    # Fallback to Hugging Face summarizer
    # --------------------------------------------------
    if hf_summarizer:
        try:
            result = hf_summarizer(content[:1000], max_length=80, min_length=25, do_sample=False)
            summary_text = result[0].get("summary_text", "").strip()
            if not summary_text:
                raise ValueError("Empty Hugging Face summary.")
            logger.info("[Summarization] Summary generated via Hugging Face fallback.")
            return summary_text
        except Exception as hf_err:
            logger.error(f"[Summarization] Fallback summarizer failed: {hf_err}")
            return "Unable to summarize the content due to model error."
    else:
        logger.warning("[Summarization] No fallback model available.")
        return "Unable to summarize the content."
