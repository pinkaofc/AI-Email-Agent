# agents/response_agent.py

import time
import warnings
import re
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from utils.logger import get_logger
from utils.formatter import clean_text
from config import get_gemini_api_key
from utils.rate_limit_guard import rate_limit_safe_call
from utils.custom_fallbacks import get_custom_fallback

# NEW Monitoring
from monitoring.metrics import (
    GEMINI_CALLS,
    GEMINI_FAILURES,
    GEMINI_FALLBACK_USED,
    SANITIZATION_TRIGGERED,
)

warnings.filterwarnings("ignore")
logger = get_logger(__name__)


# ============================================================
#                 GEMINI SAFE RESPONSE WRAPPER
# ============================================================
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    """
    Calls Gemini safely with:
    - automatic retries
    - exponential backoff for network errors
    - rotation on quota / 429
    - Prometheus monitoring
    """
    last_exception = None

    for attempt in range(1, retry_attempts + 1):
        api_key = get_gemini_api_key()

        # Metrics: count call attempt
        try:
            GEMINI_CALLS.labels(module="response").inc()
        except Exception:
            pass

        logger.info(f"[ResponseAgent] Gemini attempt {attempt}/{retry_attempts} using key {api_key[:6]}...")

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.4,
                google_api_key=api_key,
            )

            # ⚠️ IMPORTANT: do NOT pass module_name into model.invoke
            response_obj = rate_limit_safe_call(model.invoke, prompt)

            response_text = clean_text(getattr(response_obj, "content", response_obj)).strip()
            if not response_text:
                raise ValueError("Gemini returned empty response.")

            return response_text

        except Exception as e:
            last_exception = e
            err = str(e).lower()
            reason = err[:60] if err else "unknown"

            # Metrics: failure count
            try:
                GEMINI_FAILURES.labels(module="response", reason=reason).inc()
            except Exception:
                pass

            logger.warning(f"[ResponseAgent] Attempt {attempt} failed: {e}")

            # Retry conditions
            if "429" in err or "quota" in err:
                logger.info("[ResponseAgent] Quota limit hit — rotating key...")
                time.sleep(3)
                continue

            if "timeout" in err or "network" in err:
                delay = 2 ** attempt
                logger.info(f"[ResponseAgent] Network issue → retrying in {delay}s.")
                time.sleep(delay)
                continue

            logger.error("[ResponseAgent] Fatal Gemini error — aborting further attempts.")
            break

    raise RuntimeError(f"Gemini failed after retries: {last_exception}")


# ============================================================
#        MAIN SAFE RESPONSE BODY GENERATOR
# ============================================================
def generate_response(email: dict, summary: str, recipient_name: str, your_name: str) -> str:
    """
    Generates ONLY the body text of the email — no greeting and no signature.
    Ensures:
    - No hallucinated operational data
    - Proper fallback when LLM fails
    - Full monitoring integration
    """

    subject = email.get("subject", "").strip()
    content = (email.get("body") or "").strip() or "(No content provided)"

    # ============================================================
    # SAFE PROMPT
    # ============================================================
    prompt_template = PromptTemplate(
        input_variables=["recipient_name", "subject", "content", "summary", "your_name"],
        template=(
            "You are an AI assistant for ShipCube Logistics.\n"
            "Write ONLY the main body text (no greeting, no closing).\n\n"

            "==== SAFETY RULES ====\n"
            "- Do NOT invent tracking numbers.\n"
            "- Do NOT guess delivery dates or ETAs.\n"
            "- Do NOT claim refunds, replacements, or investigations.\n"
            "- Do NOT mention warehouses unless explicitly stated.\n"
            "- If required information is missing, state that the operations team will verify.\n\n"

            "Customer Name: {recipient_name}\n"
            "Subject: {subject}\n"
            "Email Content:\n{content}\n\n"
            "Intent Summary:\n{summary}\n\n"
            "Produce ONLY the response body:\n"
        ),
    )

    prompt = prompt_template.format(
        recipient_name=recipient_name,
        subject=subject,
        content=content,
        summary=summary,
        your_name=your_name,
    )

    # ============================================================
    # Try Gemini
    # ============================================================
    try:
        llm_text = _use_gemini(prompt).strip()

        # If unusable → fallback
        if not llm_text or len(llm_text) < 6:
            logger.warning("[ResponseAgent] Gemini output too weak — using fallback")
            GEMINI_FALLBACK_USED.labels(module="response").inc()
            return get_custom_fallback(summary, content)

        # ============================================================
        # Hallucination Firewall
        # ============================================================
        suspicious_patterns = [
            r"\bSC-[A-Z0-9]{4,}\b",
            r"\btracking number\b",
            r"\border id\b",
            r"\brefund\b",
            r"\bETA\b",
            r"\bwarehouse\b",
            r"\binvestigation\b",
        ]

        for p in suspicious_patterns:
            if re.search(p, llm_text, re.IGNORECASE):
                logger.warning("[ResponseAgent] Suspicious content detected — sanitized fallback")
                SANITIZATION_TRIGGERED.labels(stage="response").inc()
                GEMINI_FALLBACK_USED.labels(module="response").inc()
                return get_custom_fallback(summary, content)

        return llm_text

    except Exception as e:
        logger.error(f"[ResponseAgent] Gemini failure — fallback used: {e}")
        GEMINI_FALLBACK_USED.labels(module="response").inc()
        return get_custom_fallback(summary, content)
