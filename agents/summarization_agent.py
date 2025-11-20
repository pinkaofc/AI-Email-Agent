import time
import random
import warnings
import re
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from transformers import pipeline
from utils.formatter import clean_text
from config import get_gemini_api_key
from utils.logger import get_logger
from utils.rate_limit_guard import rate_limit_safe_call  # Added for rate-limit handling

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

# ============================================================
#                  FALLBACK HF MODEL (PINNED)
# ============================================================
try:
    hf_summarizer = pipeline(
        "summarization",
        model="facebook/bart-large-cnn",
        revision="7b5b4db",   # pinned for reproducibility
    )
    logger.info("[Summarization] HuggingFace fallback model loaded successfully (pinned).")
except Exception as e:
    hf_summarizer = None
    logger.error(f"[Summarization] Failed to initialize fallback summarizer: {e}")


# ============================================================
#           SUSPICIOUS PATTERNS TO BLOCK IN SUMMARIES
# ============================================================
SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",       # actual order IDs
    r"\btracking number\b",       # avoid hallucinating a number
    r"\bAWB\b",                   # airway bill numbers
    r"\bETA\b",                   # exact ETA
    r"\border id\b",              # specific identifiers
    r"\bclient address\b",        # PII
    r"\bphone\b",                 # PII
]



def _sanitize_summary(summary: str) -> str:
    """
    Removes any hallucinated operational details from LLM summaries.
    Ensures only **intent-level** summary remains.
    """
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, summary, re.IGNORECASE):
            logger.warning("[Summarization] Suspicious details detected in Gemini summary — sanitizing.")
            return "The customer has raised a query and is seeking help. They need support or clarification regarding their issue."

    return summary


# ============================================================
#                 GEMINI SUMMARIZER (SAFE)
# ============================================================
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    """Gemini summarizer with:
    - Rate limit guard
    - Key rotation
    - Retry logic
    """
    for attempt in range(1, retry_attempts + 1):
        api_key = get_gemini_api_key()
        logger.info(f"[Summarization] Attempt {attempt}/{retry_attempts} using Gemini key: {api_key[:6]}...")

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.2,  # low temp → safer, fewer hallucinations
                google_api_key=api_key,
            )

            # Auto-paused safe call
            result = rate_limit_safe_call(model.invoke, prompt)
            summary = clean_text(result.content).strip()

            if not summary:
                raise ValueError("Empty summary from Gemini")

            return summary

        except Exception as e:
            error = str(e).lower()

            if "quota" in error or "429" in error:
                logger.warning(f"[Summarization] Quota exceeded for key {api_key[:6]} — rotating key.")
                continue

            if "timeout" in error or "network" in error:
                logger.warning("[Summarization] Temporary network issue — retrying in 5 seconds.")
                time.sleep(5)
                continue

            logger.error(f"[Summarization] Gemini API error: {e}")
            raise e

    raise RuntimeError("Gemini summarization failed after all retries.")


# ============================================================
#             PUBLIC SUMMARIZATION ENTRY POINT
# ============================================================
def summarize_email(email: dict) -> str:
    """
    Generates a **safe, intent-only** summary of the user's message.
    Strict rules:
      - No tracking numbers
      - No delivery dates
      - No investigation results
      - No operational claims
      - No commitments or invented details
    """

    content = (email.get("body") or "").strip()

    if not content:
        logger.warning("[Summarization] Empty email content detected.")
        return "No content to summarize."

    # ============================================================
    # SAFE PROMPT (PREVENTS HALLUCINATION)
    # ============================================================
    prompt_template = PromptTemplate(
        input_variables=["content"],
        template=(
            "Summarize the following customer email in 2–3 sentences.\n"
            "The summary must ONLY describe the customer's intent or concern.\n\n"

            "STRICT RULES:\n"
            "- Do NOT invent any details.\n"
            "- Do NOT generate tracking numbers.\n"
            "- Do NOT guess delivery dates, refunds, or resolutions.\n"
            "- Do NOT describe internal processes (investigations, warehouse checks).\n"
            "- Only restate what the customer is asking, reporting, or requesting.\n\n"

            "Email:\n{content}\n\n"
            "Provide ONLY the intent-level summary:\n"
        ),
    )

    prompt = prompt_template.format(content=content)

    # ============================================================
    # Try Gemini First
    # ============================================================
    try:
        summary = _use_gemini(prompt)
        summary = _sanitize_summary(summary)  # remove hallucinated details
        logger.debug(f"[Summarization] Safe Gemini summary: {summary!r}")
        return summary

    except Exception as e:
        logger.warning(f"[Summarization] Gemini summarization failed: {e}")

    # ============================================================
    # Fallback to HuggingFace
    # ============================================================
    if hf_summarizer:
        try:
            result = hf_summarizer(
                content[:1000],
                max_length=80,
                min_length=25,
                do_sample=False
            )
            summary = result[0].get("summary_text", "").strip()

            if not summary:
                raise ValueError("Empty HF summary")

            summary = _sanitize_summary(summary)
            logger.info("[Summarization] Summary generated via HuggingFace fallback.")
            return summary

        except Exception as e:
            logger.error(f"[Summarization] HuggingFace fallback failed: {e}")
            return "The customer has shared a message and is requesting assistance."

    # Last fallback
    logger.warning("[Summarization] No summarizer available — returning minimal default summary.")
    return "The customer has shared a message and needs assistance."
