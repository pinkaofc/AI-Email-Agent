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

# Monitoring (final metrics)
from monitoring.metrics import (
    EMAILS_PROCESSED,
    EMAIL_CLASSIFICATION_COUNTER,
    EMAIL_LATENCY,
    KB_QUERIES,
    KB_EMPTY_RESULTS,
    SANITIZATION_TRIGGERED,
    PIPELINE_ACTIVE,
)

from transformers import pipeline

logger = get_logger(__name__)

# =====================================================================
# Local fallback models (used when agents fail)
# =====================================================================
try:
    hf_summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
except Exception as e:
    hf_summarizer = None
    logger.warning(f"[Supervisor] HF summarizer unavailable: {e}")

try:
    hf_sentiment = pipeline(
        "sentiment-analysis",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        revision="af0f99b",
    )
except Exception as e:
    hf_sentiment = None
    logger.warning(f"[Supervisor] HF sentiment unavailable: {e}")

# =====================================================================
# Safety patterns (hallucination / PII / operational claims)
# =====================================================================
SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",
    r"\border id\b",
    r"\btracking number\b",
    r"\bETA\b",
    r"\bAWB\b",
    r"\binvestigation\b",
    r"\brefund\b",
    r"\bclient address\b",
    r"\bphone\b",
]


def _contains_suspicious(text: str) -> bool:
    if not text:
        return False
    for p in SUSPICIOUS_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


# =====================================================================
# Lightweight local fallbacks
# =====================================================================
def local_classify(text: str) -> str:
    try:
        if not text or not text.strip():
            return "neutral"
        if hf_sentiment:
            r = hf_sentiment(text[:500])[0].get("label", "").lower()
            if "neg" in r:
                return "negative"
            if "pos" in r:
                return "positive"
        return "neutral"
    except Exception:
        return "neutral"


def local_summarize(text: str) -> str:
    try:
        if not text or not text.strip():
            return "No summary available."
        if hf_summarizer:
            r = hf_summarizer(text[:800], max_length=80, min_length=25, do_sample=False)[0]
            return r.get("summary_text", "Summary unavailable.")
        return "Summary unavailable."
    except Exception:
        return "Summary unavailable."


# =====================================================================
# FILTER NODE
# - calls filtering_agent.filter_email (Gemini primary, HF fallback)
# - updates EmailState fields and metrics
# - records history snapshot
# =====================================================================
def filter_node(state: EmailState) -> EmailState:
    email = state.current_email
    email_id = state.current_email_id or "N/A"

    logger.info(f"[Filtering] Email ID: {email_id}")
    # mark pipeline active metrics handled at supervisor entry/exit

    try:
        # attempt primary agent
        try:
            classification = filtering_agent.filter_email(email)
            state.used_fallback = False
            state.fallback_reason = None
        except Exception as e:
            logger.warning(f"[Filtering] agent failed → using local fallback: {e}")
            classification = local_classify(email.get("body", ""))
            state.used_fallback = True
            state.fallback_reason = f"filter_agent_failure: {str(e)[:250]}"

        # store classification
        state.classification = classification
        state.metadata.setdefault(email_id, {})["classification"] = classification

        # metrics
        try:
            EMAIL_CLASSIFICATION_COUNTER.labels(classification=(classification or "unknown")).inc()
        except Exception:
            pass

        # human review & priority heuristics
        if classification == "negative":
            state.requires_human_review = True
            state.priority = "high"
            state.metadata[email_id]["priority"] = "high"

        # history
        state.record_history(stage="filter", note=f"classified:{classification}")

        logger.info(f"[Filtering] {email_id} -> {classification}")
    except Exception as e:
        # fatal filtering error -> mark state
        state.classification = "error"
        state.processing_error = f"Filtering error: {e}"
        state.record_history(stage="filter_error", note=str(e))
        logger.error(f"[Filtering] Unhandled error for {email_id}: {e}", exc_info=True)

    return state


# =====================================================================
# SUMMARIZATION NODE
# - calls summarization_agent.summarize_email (Gemini primary)
# - sanitizes hallucinated operational details
# - updates EmailState fields, metrics, history
# =====================================================================
def summarize_node(state: EmailState) -> EmailState:
    email = state.current_email
    email_id = state.current_email_id or "N/A"

    logger.info(f"[Summarization] Email ID: {email_id}")

    # skip for spam/promotional or if previously errored
    if state.classification in ["spam", "promotional"] or state.processing_error:
        state.summary = "Summary skipped."
        state.record_history(stage="summarize_skipped", note=f"classification:{state.classification}")
        return state

    try:
        try:
            summary = summarization_agent.summarize_email(email)
            state.used_fallback = False
            state.fallback_reason = None
        except Exception as e:
            logger.warning(f"[Summarization] agent failed → local fallback: {e}")
            summary = local_summarize(email.get("body", ""))
            state.used_fallback = True
            state.fallback_reason = f"summarization_agent_failure: {str(e)[:250]}"

        # sanitize suspicious content
        if not summary or _contains_suspicious(summary):
            logger.warning(f"[Summarization] Suspicious or empty summary → sanitizing for {email_id}")
            SANITIZATION_TRIGGERED.labels(stage="summarization").inc()
            summary = "The customer has shared a message and is requesting assistance."
            state.hallucination_detected = True
            state.fallback_reason = state.fallback_reason or "summary_sanitized"
            state.used_fallback = True

        state.summary = summary
        state.metadata.setdefault(email_id, {})["summary"] = summary
        state.record_history(stage="summarize", note=f"used_fallback:{state.used_fallback}")

        logger.info(f"[Summarization] Completed for {email_id}")
    except Exception as e:
        state.summary = "Summary unavailable."
        state.processing_error = f"Summarization failed: {e}"
        state.record_history(stage="summarize_error", note=str(e))
        logger.error(f"[Summarization] Error for {email_id}: {e}", exc_info=True)

    return state


# =====================================================================
# RESPONSE NODE
# - fetch KB safely, call response_agent.generate_response
# - sanitize hallucinations, compute confidence, update EmailState
# - record history
# =====================================================================
def respond_node(state: EmailState, your_name: str, recipient_name: str) -> EmailState:
    email = state.current_email
    email_id = state.current_email_id or "N/A"

    logger.info(f"[Response] Email ID: {email_id}")

    start_ts = time.time()
    PIPELINE_ACTIVE.inc()

    try:
        # ---------- RAG: safe KB retrieval ----------
        kb_context = ""
        try:
            KB_QUERIES.inc()
            kb_context = query_knowledge_base(state.summary or email.get("body", "")) or ""
            state.retrieved_context = kb_context
            # naive context_quality heuristic: length-based
            state.context_quality = round(min(1.0, max(0.0, len(kb_context) / 800.0)), 2)
            state.metadata.setdefault(email_id, {})["kb_ok"] = bool(kb_context)
            if not kb_context:
                KB_EMPTY_RESULTS.inc()
        except Exception as e:
            logger.warning(f"[RAG] KB query failed for {email_id}: {e}")
            KB_EMPTY_RESULTS.inc()
            state.retrieved_context = ""
            state.context_quality = 0.0
            state.metadata.setdefault(email_id, {})["kb_ok"] = False
            # continue — KB must not block response

        state.metadata[email_id]["kb_context_preview"] = (kb_context or "")[:400]

        # ---------- build composite context ----------
        composite_summary = (
            f"CompanyKnowledge:\n{kb_context}\n\n"
            f"Summary:\n{state.summary}\n\n"
            f"OriginalEmail:\n{email.get('body', '')}"
        )

        # ---------- call response agent ----------
        response_body = ""
        response_source = "unknown"
        try:
            response_body = response_agent.generate_response(
                email=email,
                summary=composite_summary,
                recipient_name=recipient_name,
                your_name=your_name,
            )
            response_source = "gemini"
            state.used_fallback = False
            state.fallback_reason = None
        except Exception as e:
            logger.warning(f"[Response] agent failed for {email_id}: {e}")
            response_body = get_custom_fallback(state.summary, email.get("body", ""))
            response_source = "custom_fallback"
            state.used_fallback = True
            state.fallback_reason = f"response_agent_failure: {str(e)[:250]}"

        # ---------- sanitize hallucinations ----------
        if _contains_suspicious(response_body):
            logger.warning(f"[Response] Hallucinated operational details detected for {email_id}; sanitizing.")
            SANITIZATION_TRIGGERED.labels(stage="response").inc()
            state.hallucination_detected = True
            # replace with safe template
            response_body = get_custom_fallback(state.summary, email.get("body", ""))
            response_source = "sanitized_custom_fallback"
            state.used_fallback = True
            state.fallback_reason = state.fallback_reason or "response_sanitized"
            state.requires_human_review = True
            state.metadata[email_id]["sanitization_reason"] = "suspicious_operational_details_detected"

        # ---------- ensure non-empty response ----------
        if not response_body or not response_body.strip():
            logger.warning(f"[Response] Empty response for {email_id}; using global fallback.")
            response_body = FALLBACK_RESPONSE
            response_source = "global_fallback"
            state.used_fallback = True
            state.fallback_reason = state.fallback_reason or "empty_response_fallback"

        # ---------- compute simple confidence ----------
        confidence = 1.0
        if response_source != "gemini":
            confidence -= 0.4
        if "?" in response_body:
            confidence -= 0.15
        if len(response_body) < 60:
            confidence -= 0.2
        confidence = max(0.0, min(1.0, round(confidence, 2)))

        # ---------- store provenance & metadata ----------
        state.generated_response_body = response_body
        state.metadata[email_id]["raw_generated_response"] = response_body
        state.metadata[email_id]["response_source"] = response_source
        state.metadata[email_id]["confidence_score"] = confidence
        state.confidence_score = confidence

        # priority heuristics: urgent words or negative sentiment escalate
        body_lower = (email.get("body") or "").lower()
        if any(x in body_lower for x in ["urgent", "asap", "immediately"]):
            state.requires_human_review = True
            state.priority = "high"
            state.metadata[email_id]["priority"] = "high"

        if state.classification == "negative":
            state.requires_human_review = True
            state.priority = "high"
            state.metadata[email_id]["priority"] = "high"

        if confidence < 0.5:
            state.requires_human_review = True
            state.metadata[email_id]["requires_review_reason"] = "low_confidence"

        state.metadata[email_id]["response_status"] = (
            "awaiting_human_review" if state.requires_human_review else "ready_to_send"
        )

        # ---------- format final email ----------
        formatted_email = format_email(
            subject=email.get("subject", "Re: No Subject"),
            recipient_name=recipient_name,
            body=response_body,
            user_name=your_name,
        )

        state.formatted_email = formatted_email

        # ---------- record metrics & history ----------
        EMAIL_LATENCY.observe(time.time() - start_ts)
        state.record_history(stage="respond", note=f"source:{response_source},confidence:{confidence}")

        logger.info(f"[Response] Completed for {email_id} (source={response_source}, confidence={confidence})")

    except Exception as e:
        # ensure we never crash the caller — provide safe fallbacks
        EMAIL_LATENCY.observe(time.time() - start_ts)
        state.generated_response_body = FALLBACK_RESPONSE
        state.formatted_email = FALLBACK_RESPONSE
        state.processing_error = f"Response generation failed: {e}"
        state.requires_human_review = True
        state.used_fallback = True
        state.fallback_reason = f"response_unhandled_exception: {str(e)[:250]}"
        state.record_history(stage="respond_error", note=str(e))
        logger.error(f"[Response] Unhandled error for {email_id}: {e}", exc_info=True)

    finally:
        try:
            PIPELINE_ACTIVE.dec()
        except Exception:
            pass

    return state


# =====================================================================
# Routing helper
# =====================================================================
def route_after_filtering(state: EmailState) -> str:
    if state.classification in ["spam", "promotional"]:
        logger.info(f"[Supervisor] Email {state.current_email_id} marked as {state.classification}. Ending workflow.")
        return "end_workflow"
    if state.processing_error:
        logger.warning(f"[Supervisor] Email {state.current_email_id} has processing_error: {state.processing_error}. Ending workflow.")
        return "end_workflow"
    return "summarize"


# =====================================================================
# supervisor_langgraph: entry point
# - creates initial EmailState
# - increments pipeline metrics
# - ensures robust error handling and full-state return
# =====================================================================
def supervisor_langgraph(selected_email: dict, your_name: str, recipient_name: str) -> EmailState:
    email_id = selected_email.get("id", f"email_{int(time.time())}")
    logger.info(f"[Supervisor] Starting pipeline for {email_id}")

    # initial EmailState
    initial_state = EmailState(
        current_email=selected_email,
        current_email_id=email_id,
        metadata={email_id: {}},
        emails=[selected_email],
    )

    # mark pipeline start in metrics
    try:
        EMAILS_PROCESSED.labels(status="started").inc()
        PIPELINE_ACTIVE.inc()
    except Exception:
        pass

    workflow = StateGraph(EmailState)
    workflow.add_node("filter", filter_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("respond", partial(respond_node, your_name=your_name, recipient_name=recipient_name))

    workflow.set_entry_point("filter")
    workflow.add_conditional_edges("filter", route_after_filtering, {"summarize": "summarize", "end_workflow": END})
    workflow.add_edge("summarize", "respond")
    workflow.add_edge("respond", END)

    app = workflow.compile()

    try:
        final_state_dict = app.invoke(initial_state)
        final_state = EmailState(**final_state_dict)

        # finalize metrics
        try:
            EMAILS_PROCESSED.labels(status="success").inc()
        except Exception:
            pass

        # final metadata housekeeping
        final_state.record_history(stage="pipeline_complete", note="finished_success")
        logger.info(f"[Supervisor] Pipeline finished for {email_id} status={final_state.metadata.get(email_id, {}).get('response_status')}")
        return final_state

    except Exception as e:
        # pipeline failure — return safe error state
        try:
            EMAILS_PROCESSED.labels(status="failed").inc()
        except Exception:
            pass

        logger.critical(f"[Supervisor] Workflow execution failed for {email_id}: {e}", exc_info=True)

        error_state = EmailState(
            current_email=selected_email,
            current_email_id=email_id,
            classification="error",
            summary="Execution failed.",
            generated_response_body=FALLBACK_RESPONSE,
            processing_error=f"Supervisor failure: {str(e)}",
            requires_human_review=True,
            used_fallback=True,
            fallback_reason="supervisor_crash"
        )
        error_state.record_history(stage="pipeline_failed", note=str(e))
        return error_state
