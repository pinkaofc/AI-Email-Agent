# core/supervisor.py

import time
import warnings
import re
from functools import partial
from datetime import datetime

warnings.filterwarnings("ignore")

from langgraph.graph import END, StateGraph
from agents import filtering_agent, summarization_agent, response_agent
from core.state import EmailState
from utils.logger import get_logger
from utils.formatter import format_email, FALLBACK_RESPONSE
from knowledge_base.query import query_knowledge_base
from utils.custom_fallbacks import get_custom_fallback

# ===================== METRICS ============================
from monitoring.metrics import (
    EMAILS_PROCESSED,
    EMAIL_CLASSIFICATION_COUNTER,
    EMAIL_LATENCY,
    KB_QUERIES,
    KB_EMPTY_RESULTS,
    SANITIZATION_TRIGGERED,
    PIPELINE_ACTIVE,

    FILTERING_COUNT,
    FILTERING_MODEL_USED,
    FILTERING_LATENCY,

    summarization_attempts_total,
    summarization_model_used_total,
    summarization_latency_seconds,

    response_attempts_total,
    response_model_used_total,
    response_latency_seconds,
)

logger = get_logger(__name__)

# ===========================================================
# Hallucination Firewall (Option C)
# ===========================================================

ORDER_ID_PATTERN = r"\b(?:SC|PO|ORDER|INVOICE)[-\s]?[A-Z0-9]{4,12}\b"

STRICT_FORBIDDEN = [
    r"\bAWB\s*\d+",
    r"\bETA[:\- ]?\d",
    r"\bETA\s+\d",
    r"\b\d{10,}\b",
]

def _fabrication_detected(text: str, email_text: str) -> bool:
    if not text:
        return False

    real_ids = {
        oid.upper().replace(" ", "")
        for oid in re.findall(ORDER_ID_PATTERN, email_text or "", re.IGNORECASE)
    }

    model_ids = {
        oid.upper().replace(" ", "")
        for oid in re.findall(ORDER_ID_PATTERN, text, re.IGNORECASE)
    }

    fabricated = [i for i in model_ids if i not in real_ids]
    if fabricated:
        logger.warning(f"[Supervisor] Fabricated ID → {fabricated}")
        return True

    for p in STRICT_FORBIDDEN:
        if re.search(p, text, re.IGNORECASE):
            logger.warning(f"[Supervisor] Fabricated pattern → {p}")
            return True

    return False

# ===========================================================
# Light local fallbacks
# ===========================================================

def local_classify(text: str) -> str:
    if not text or not text.strip():
        return "neutral"
    low = text.lower()
    if any(w in low for w in ["not", "issue", "problem", "wrong"]):
        return "negative"
    return "neutral"

def local_summary(text: str) -> str:
    if not text or not text.strip():
        return "No content to summarize."
    if len(text.split()) < 8:
        return f"The customer is requesting: {text.strip()}"
    return "The customer needs assistance."

# ===========================================================
# FILTER NODE — with metrics
# ===========================================================

def filter_node(state: EmailState) -> EmailState:
    email = state.current_email
    email_id = state.current_email_id
    logger.info(f"[Filtering] Email ID: {email_id}")

    start = time.time()
    try:
        try:
            cls = filtering_agent.filter_email(email)
            state.used_fallback = False
            FILTERING_MODEL_USED.labels(model="huggingface").inc()
        except Exception as e:
            logger.warning(f"[Filtering] agent failed → fallback: {e}")
            cls = local_classify(email.get("body", ""))
            state.used_fallback = True
            FILTERING_MODEL_USED.labels(model="fallback").inc()

        FILTERING_COUNT.inc()
        FILTERING_LATENCY.observe(time.time() - start)

        state.classification = cls
        state.metadata.setdefault(email_id, {})["classification"] = cls

        EMAIL_CLASSIFICATION_COUNTER.labels(classification=cls).inc()
        state.record_history(stage="filter", note=f"class={cls}")

    except Exception as e:
        state.classification = "error"
        state.processing_error = f"Filtering error: {e}"
        state.record_history(stage="filter_error", note=str(e))

    return state

# ===========================================================
# SUMMARIZE NODE — with metrics
# ===========================================================

def summarize_node(state: EmailState) -> EmailState:
    email = state.current_email
    email_id = state.current_email_id
    logger.info(f"[Summarization] Email ID: {email_id}")

    if state.classification in ["spam", "promotional"]:
        state.summary = "Summary skipped."
        state.record_history(stage="summarize_skipped", note="spam/promotional")
        return state

    start = time.time()

    try:
        summarization_attempts_total.inc()

        try:
            summary = summarization_agent.summarize_email(email)
            state.used_fallback = False
            summarization_model_used_total.labels(model="huggingface").inc()
        except Exception as e:
            logger.warning(f"[Summarization] agent failed → fallback: {e}")
            summary = local_summary(email.get("body", ""))
            state.used_fallback = True
            summarization_model_used_total.labels(model="fallback").inc()

        if not summary.strip():
            summary = local_summary(email.get("body", ""))
            state.used_fallback = True

        summarization_latency_seconds.observe(time.time() - start)

        state.summary = summary
        state.metadata.setdefault(email_id, {})["summary"] = summary
        state.record_history(stage="summarize", note=f"fallback={state.used_fallback}")

    except Exception as e:
        state.summary = "The customer needs assistance."
        state.processing_error = f"Summarization error: {e}"
        state.record_history(stage="summarize_error", note=str(e))

    return state

# ===========================================================
# RESPONSE NODE — with metrics
# ===========================================================

def respond_node(state: EmailState, your_name: str, recipient_name: str) -> EmailState:
    email = state.current_email
    email_id = state.current_email_id
    body_text = email.get("body", "")

    logger.info(f"[Response] Email ID: {email_id}")

    start_time = time.time()
    PIPELINE_ACTIVE.inc()

    try:
        # -------- KB Retrieval --------
        try:
            KB_QUERIES.inc()
            kb_context = query_knowledge_base(state.summary) or ""
            if not kb_context:
                KB_EMPTY_RESULTS.inc()
        except:
            kb_context = ""
            KB_EMPTY_RESULTS.inc()

        composite_summary = (
            f"Intent Summary:\n{state.summary}\n\n"
            f"Knowledge Context:\n{kb_context}\n\n"
            f"OriginalEmail:\n{body_text}"
        )

        # -------- Response Attempt --------
        response_attempts_total.inc()

        try:
            resp = response_agent.generate_response(
                email=email,
                summary=composite_summary,
                recipient_name=recipient_name,
                your_name=your_name,
            )
            source = "gemini"
            response_model_used_total.labels(model="gemini").inc()

        except Exception as e:
            logger.warning(f"[Response] Gemini failed → fallback: {e}")
            resp = get_custom_fallback(state.summary, body_text)
            source = "fallback"
            response_model_used_total.labels(model="fallback").inc()

        # -------- Firewall --------
        if _fabrication_detected(resp, body_text):
            SANITIZATION_TRIGGERED.labels(stage="response").inc()
            resp = get_custom_fallback(state.summary, body_text)
            source = "sanitized"
            response_model_used_total.labels(model="sanitized").inc()
            state.requires_human_review = True

        if not resp.strip():
            resp = FALLBACK_RESPONSE
            source = "fallback"
            response_model_used_total.labels(model="fallback").inc()

        response_latency_seconds.observe(time.time() - start_time)

        # -------- Confidence --------
        confidence = 1.0
        if source != "gemini":
            confidence -= 0.25
        if len(resp) < 40:
            confidence -= 0.1
        confidence = max(0.0, round(confidence, 2))

        # -------- Store --------
        state.generated_response_body = resp
        state.confidence_score = confidence
        state.metadata.setdefault(email_id, {})["response_source"] = source
        state.metadata[email_id]["confidence"] = confidence

        state.requires_human_review = (source != "gemini" and confidence < 0.45)

        state.formatted_email = format_email(
            subject=email.get("subject", "Re: No Subject"),
            recipient_name=recipient_name,
            body=resp,
            user_name=your_name,
        )

        EMAIL_LATENCY.observe(time.time() - start_time)
        state.record_history(stage="respond", note=f"{source}/{confidence}")

    except Exception as e:
        logger.error(f"[Response] UNHANDLED ERROR: {e}", exc_info=True)
        state.generated_response_body = FALLBACK_RESPONSE
        state.formatted_email = FALLBACK_RESPONSE
        state.processing_error = f"Response error: {e}"
        state.requires_human_review = True

    finally:
        try:
            PIPELINE_ACTIVE.dec()
        except:
            pass

    return state

# ===========================================================
# ROUTING
# ===========================================================

def route_after_filtering(state: EmailState) -> str:
    if state.classification in ["spam", "promotional"]:
        return "end_workflow"
    if state.processing_error:
        return "end_workflow"
    return "summarize"

# ===========================================================
# SUPERVISOR ENTRY
# ===========================================================

def supervisor_langgraph(selected_email: dict, your_name: str, recipient_name: str) -> EmailState:
    email_id = selected_email.get("id", f"email_{int(time.time())}")
    logger.info(f"[Supervisor] Starting pipeline for {email_id}")

    initial = EmailState(
        current_email=selected_email,
        current_email_id=email_id,
        metadata={email_id: {}},
        emails=[selected_email],
    )

    PIPELINE_ACTIVE.inc()
    EMAILS_PROCESSED.labels(status="started").inc()

    workflow = StateGraph(EmailState)
    workflow.add_node("filter", filter_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("respond", partial(respond_node, your_name=your_name, recipient_name=recipient_name))

    workflow.set_entry_point("filter")
    workflow.add_conditional_edges("filter", route_after_filtering, {
        "summarize": "summarize",
        "end_workflow": END
    })
    workflow.add_edge("summarize", "respond")
    workflow.add_edge("respond", END)

    app = workflow.compile()

    try:
        output = app.invoke(initial)
        final = EmailState(**output)
        EMAILS_PROCESSED.labels(status="success").inc()
        final.record_history(stage="pipeline_complete", note="success")

    except Exception as e:
        EMAILS_PROCESSED.labels(status="failed").inc()
        logger.critical(f"[Supervisor] CRASH: {e}", exc_info=True)

        final = EmailState(
            current_email=selected_email,
            current_email_id=email_id,
            classification="error",
            summary="Pipeline failed.",
            generated_response_body=FALLBACK_RESPONSE,
            processing_error=str(e),
            requires_human_review=True,
        )
        final.record_history(stage="pipeline_failed", note=str(e))

    finally:
        PIPELINE_ACTIVE.dec()

    return final
