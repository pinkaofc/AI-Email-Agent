# agents/response_agent.py

import time
import warnings
import re
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.logger import get_logger
from utils.formatter import clean_text
from config import get_gemini_api_key
from utils.custom_fallbacks import get_custom_fallback

from monitoring.metrics import (
    GEMINI_CALLS,
    GEMINI_FAILURES,
    GEMINI_FALLBACK_USED,
    SANITIZATION_TRIGGERED,
    response_attempts_total,
    response_failures_total,
    response_fallback_used_total,
    response_model_used_total,
    response_latency_seconds,
    safe_increment_counter,
    safe_observe,
)

warnings.filterwarnings("ignore")
logger = get_logger(__name__)


# =======================================================================
# GEMINI 2.5 FLASH — STRICT 2-RETRY WRAPPER (NO LangChain retry!)
# =======================================================================
def _use_gemini(prompt: str, retry_attempts: int = 2) -> str:
    """
    Only 2 attempts.
    No exponential wait.
    max_retries=0 → disables LangChain retry system completely.
    """

    last_exception = None

    for attempt in range(1, retry_attempts + 1):
        api_key = get_gemini_api_key()

        safe_increment_counter(GEMINI_CALLS, module="response")

        logger.info(
            f"[ResponseAgent] Gemini attempt {attempt}/{retry_attempts} using key {api_key[:6]}..."
        )

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0.25,
                max_output_tokens=250,
                google_api_key=api_key,
                max_retries=0
            )

            result = model.invoke(prompt)
            text = clean_text(getattr(result, "content", result)).strip()

            if text:
                return text
            else:
                raise ValueError("Gemini returned empty")

        except Exception as e:
            last_exception = e
            err = str(e).lower()

            safe_increment_counter(GEMINI_FAILURES, module="response", reason=err[:40])

            if "429" in err or "quota" in err or "rate" in err:
                logger.warning("[ResponseAgent] 429 → rotating key…")
                time.sleep(1)
                continue

            if "timeout" in err or "timed out" in err:
                logger.warning("[ResponseAgent] Timeout → retrying…")
                time.sleep(1)
                continue

            logger.error(f"[ResponseAgent] Fatal error: {e}")
            break

    raise RuntimeError(f"Gemini failed after retries: {last_exception}")


# =======================================================================
# STRICT MINIMAL FIREWALL (Option-C)
# =======================================================================

TRUE_ID_PATTERN = r"\b(?:SC|PO|ORDER|INVOICE)-?[A-Z0-9]{3,12}\b"

STRICT_BLOCK_PATTERNS = [
    r"\bAWB\s*\d{5,}\b",
    r"\bETA\s*\d",
    r"\bETA[:\- ]+\d",
    r"\b\d{10,}\b",
]


def _contains_hallucination(response: str, subject: str, body: str) -> bool:

    if not response:
        return False

    real_ids = {
        oid.upper().replace(" ", "")
        for oid in re.findall(TRUE_ID_PATTERN, subject + " " + body, re.IGNORECASE)
    }

    model_ids = {
        oid.upper().replace(" ", "")
        for oid in re.findall(TRUE_ID_PATTERN, response, re.IGNORECASE)
    }

    fabricated = [oid for oid in model_ids if oid not in real_ids]
    if fabricated:
        logger.warning(f"[ResponseAgent] Fabricated ID detected → {fabricated}")
        return True

    for p in STRICT_BLOCK_PATTERNS:
        if re.search(p, response, re.IGNORECASE):
            logger.warning(f"[ResponseAgent] Blocked fabricated detail → {p}")
            return True

    return False


# =======================================================================
# MAIN RESPONSE GENERATOR (Fully Instrumented)
# =======================================================================
def generate_response(email: dict, summary: str, recipient_name: str, your_name: str) -> str:

    start_time = time.time()
    safe_increment_counter(response_attempts_total)

    subject = email.get("subject", "").strip()
    content = (email.get("body") or "").strip()

    prompt_template = PromptTemplate(
        input_variables=["recipient_name", "subject", "content", "summary"],
        template=(
            "You are an AI email support assistant at ShipCube Logistics.\n"
            "Write a clear, short, helpful response.\n\n"

            "STRICT RULES:\n"
            "- DO NOT invent tracking numbers, AWBs, ETAs, refunds, or replacements.\n"
            "- DO NOT generate order IDs unless given.\n"
            "- Only ask for missing info if needed.\n"
            "- Address the customer’s issue directly.\n"
            "- Keep it polite and simple.\n\n"

            "Customer Name: {recipient_name}\n"
            "Subject: {subject}\n"
            "Customer Email:\n{content}\n\n"
            "Intent Summary:\n{summary}\n\n"

            "Write ONLY the response body (NO greeting, NO signature):"
        ),
    )

    prompt = prompt_template.format(
        recipient_name=recipient_name,
        subject=subject,
        content=content,
        summary=summary,
    )

    # ------------------- Gemini Generation -------------------
    try:
        llm_text = _use_gemini(prompt)
        safe_increment_counter(response_model_used_total, model="gemini")

    except Exception as e:
        logger.error(f"[ResponseAgent] Gemini failure → fallback: {e}")
        safe_increment_counter(response_failures_total)
        safe_increment_counter(response_fallback_used_total)
        safe_increment_counter(response_model_used_total, model="fallback")
        safe_observe(response_latency_seconds, time.time() - start_time)
        return get_custom_fallback(summary, content)

    llm_text = llm_text.strip()

    if not llm_text:
        safe_increment_counter(response_fallback_used_total)
        safe_increment_counter(response_model_used_total, model="fallback")
        safe_observe(response_latency_seconds, time.time() - start_time)
        return get_custom_fallback(summary, content)

    # ------------------- Hallucination Check -------------------
    if _contains_hallucination(llm_text, subject, content):
        safe_increment_counter(SANITIZATION_TRIGGERED, stage="response")
        safe_increment_counter(response_fallback_used_total)
        safe_increment_counter(response_model_used_total, model="sanitized")
        safe_observe(response_latency_seconds, time.time() - start_time)
        return get_custom_fallback(summary, content)

    # ------------------- Clean & Return -------------------
    safe_observe(response_latency_seconds, time.time() - start_time)
    return clean_text(llm_text)
