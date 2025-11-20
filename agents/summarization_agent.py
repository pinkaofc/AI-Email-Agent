# agents/summarization_agent.py

import time
import re
import warnings
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from transformers import pipeline

from utils.formatter import clean_text
from config import get_gemini_api_key
from utils.logger import get_logger
from utils.rate_limit_guard import rate_limit_safe_call

# Proper monitoring imports
from monitoring.metrics import (
    GEMINI_CALLS,
    GEMINI_FAILURES,
    GEMINI_FALLBACK_USED,
    SANITIZATION_TRIGGERED,
)

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

# ============================================================
#        HuggingFace FALLBACK Summarizer
# ============================================================
try:
    hf_summarizer = pipeline(
        "summarization",
        model="facebook/bart-large-cnn"
    )
    logger.info("[Summarization] HF fallback model loaded.")
except Exception as e:
    hf_summarizer = None
    logger.error(f"[Summarization] HF summarizer failed: {e}")

# ============================================================
#      Block hallucinated operational info
# ============================================================
SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",
    r"\btracking number\b",
    r"\bETA\b",
    r"\border id\b",
    r"\bclient address\b",
    r"\bphone\b",
    r"\bAWB\b",
]


def _sanitize_summary(summary: str) -> str:
    """Remove any hallucinated operational details."""
    for pat in SUSPICIOUS_PATTERNS:
        if re.search(pat, summary, re.IGNORECASE):
            logger.warning("[Summarization] Suspicious text found → sanitizing")
            try:
                SANITIZATION_TRIGGERED.labels(stage="summarization").inc()
            except Exception:
                pass
            return (
                "The customer has raised a query and is seeking assistance. "
                "They need support or clarification regarding their issue."
            )
    return summary


# ============================================================
#        Gemini Summarizer (safe & monitored)
# ============================================================
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    last_exception = None

    for attempt in range(1, retry_attempts + 1):

        api_key = get_gemini_api_key()

        try:
            GEMINI_CALLS.labels(module="summarization").inc()
        except Exception:
            pass

        logger.info(
            f"[Summarization] Gemini attempt {attempt}/{retry_attempts} using key {api_key[:6]}..."
        )

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.2,
                google_api_key=api_key,
            )

            # IMPORTANT — do NOT pass module_name into model.invoke()
            result = rate_limit_safe_call(model.invoke, prompt)

            summary = clean_text(result.content).strip()
            if not summary:
                raise ValueError("Gemini produced empty summary")

            return summary

        except Exception as e:
            last_exception = e
            err = str(e).lower()
            reason = err[:50]

            try:
                GEMINI_FAILURES.labels(module="summarization", reason=reason).inc()
            except Exception:
                pass

            logger.warning(f"[Summarization] Attempt {attempt} failed: {e}")

            # Retry: quota / 429
            if "429" in err or "quota" in err:
                try:
                    GEMINI_FALLBACK_USED.labels(module="summarization").inc()
                except Exception:
                    pass
                time.sleep(3)
                continue

            # Retry: network / timeout
            if "timeout" in err or "network" in err:
                time.sleep(2)
                continue

            # Other fatal errors → break
            break

    raise RuntimeError(f"Gemini summarization failed: {last_exception}")


# ============================================================
#             MAIN PUBLIC SUMMARIZATION FUNCTION
# ============================================================
def summarize_email(email: dict) -> str:
    content = (email.get("body") or "").strip()
    if not content:
        return "No content to summarize."

    prompt_template = PromptTemplate(
        input_variables=["content"],
        template=(
            "Summarize the following customer email in 2–3 sentences.\n"
            "STRICT RULES:\n"
            "- Do NOT guess tracking numbers or ETAs.\n"
            "- Do NOT invent refunds, investigations, or internal processes.\n"
            "- ONLY explain the customer's intent.\n\n"
            "Email:\n{content}\n\n"
            "Provide ONLY the intent-level summary:\n"
        ),
    )

    prompt = prompt_template.format(content=content)

    # ============================================================
    # Try Gemini first
    # ============================================================
    try:
        summary = _use_gemini(prompt)
        return _sanitize_summary(summary)

    except Exception as e:
        logger.warning(f"[Summarization] Gemini failed → HF fallback used: {e}")
        try:
            GEMINI_FALLBACK_USED.labels(module="summarization").inc()
        except Exception:
            pass

    # ============================================================
    # HF fallback
    # ============================================================
    if hf_summarizer:
        try:
            result = hf_summarizer(
                content[:800],
                max_length=70,
                min_length=25,
                do_sample=False
            )
            summary = result[0].get("summary_text", "")
            return _sanitize_summary(summary)

        except Exception as e:
            logger.error(f"[Summarization] HF fallback failed: {e}")

    # ============================================================
    # Final fallback (guaranteed)
    # ============================================================
    try:
        GEMINI_FALLBACK_USED.labels(module="summarization").inc()
    except Exception:
        pass

    return "The customer has shared a message and needs assistance."
