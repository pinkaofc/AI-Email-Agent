# agents/summarization_agent.py

import time
import re
import warnings
from transformers import pipeline
from utils.logger import get_logger
from utils.formatter import clean_text

# Monitoring metrics
from monitoring.metrics import (
    summarization_attempts_total,
    summarization_failures_total,
    summarization_fallback_used_total,
    summarization_model_used_total,
    summarization_latency_seconds,
    SANITIZATION_TRIGGERED,
    safe_increment_counter,
    safe_observe,
)

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

"""
Improved Summarization Agent — FINAL VERSION
-------------------------------------------
✓ Always produces a meaningful summary
✓ Short-email interpretation improved
✓ Dynamic summarization length
✓ Minimal Option-C firewall
✓ Fully instrumented with Prometheus metrics
"""


# ============================================================
# HuggingFace Summarizer
# ============================================================
try:
    hf_summarizer = pipeline(
        "summarization",
        model="facebook/bart-large-cnn"
    )
    logger.info("[Summarization] HF summarizer loaded.")
except Exception as e:
    hf_summarizer = None
    logger.error(f"[Summarization] HF summarizer failed: {e}")


# ============================================================
# Minimal Option-C Firewall
# ============================================================
STRICT_BLOCK_PATTERNS = [
    r"\bAWB\s*\d{5,}\b",
    r"\bETA\s*\d",
    r"\bETA[:\- ]+\d",
    r"\b\d{10,}\b",
]


def _sanitize_summary(text: str) -> str:
    """Minimal hallucination firewall."""

    if not text:
        return text

    for pattern in STRICT_BLOCK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning("[Summarization] Fabricated operational detail detected.")

            try:
                SANITIZATION_TRIGGERED.labels(stage="summarization").inc()
            except Exception:
                pass

            return "The customer has described an issue and is requesting clarification or assistance."

    return text


# ============================================================
# Main Summarization Function
# ============================================================
def summarize_email(email: dict) -> str:
    start_time = time.time()
    safe_increment_counter(summarization_attempts_total)

    content = (email.get("body") or "").strip()

    if not content:
        safe_increment_counter(summarization_model_used_total, model="fallback")
        safe_observe(summarization_latency_seconds, time.time() - start_time)
        return "The customer sent a message but no content was provided."

    words = content.split()
    wc = len(words)

    # -----------------------------------
    # 1) Extremely short emails
    # -----------------------------------
    if wc <= 6:
        safe_increment_counter(summarization_model_used_total, model="keyword")
        safe_observe(summarization_latency_seconds, time.time() - start_time)
        return f"The customer is making a brief request: {content}"

    # -----------------------------------
    # 2) Short/medium emails (interpret intent)
    # -----------------------------------
    if wc <= 18:
        safe_increment_counter(summarization_model_used_total, model="keyword")
        safe_observe(summarization_latency_seconds, time.time() - start_time)
        return (
            f"The customer states: '{content}'. "
            f"They appear to be requesting assistance or clarification."
        )

    # -----------------------------------
    # 3) Longer emails → HuggingFace summarizer
    # -----------------------------------
    if hf_summarizer:
        try:
            max_len = 70 if wc > 40 else max(20, wc + 5)
            min_len = max(12, wc // 3)

            result = hf_summarizer(
                content[:900],
                max_length=max_len,
                min_length=min_len,
                do_sample=False,
            )

            summary_text = clean_text(result[0].get("summary_text", "")).strip()

            safe_increment_counter(summarization_model_used_total, model="huggingface")
            safe_observe(summarization_latency_seconds, time.time() - start_time)

            return _sanitize_summary(summary_text)

        except Exception as e:
            logger.error(f"[Summarization] HF summarization failed: {e}")
            safe_increment_counter(summarization_failures_total)

    # -----------------------------------
    # 4) Final fallback
    # -----------------------------------
    safe_increment_counter(summarization_fallback_used_total)
    safe_increment_counter(summarization_model_used_total, model="fallback")
    safe_observe(summarization_latency_seconds, time.time() - start_time)

    return "The customer has shared details of their issue and requires assistance."
