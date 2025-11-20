import warnings
warnings.filterwarnings("ignore")

from langgraph.graph import END, StateGraph
from agents import filtering_agent, summarization_agent, response_agent
from core.state import EmailState
from utils.logger import get_logger
from utils.formatter import format_email
from functools import partial
from datetime import datetime
from knowledge_base.query import query_knowledge_base
from transformers import pipeline
from utils.custom_fallbacks import get_custom_fallback   # ★ NEW: custom fallback integration
from utils.formatter import FALLBACK_RESPONSE
import re

logger = get_logger(__name__)

# ============================================================
#                   FALLBACK MODELS
# ============================================================

hf_summarizer = pipeline(
    "summarization",
    model="facebook/bart-large-cnn"
)

hf_sentiment = pipeline(
    "sentiment-analysis",
    model="distilbert-base-uncased-finetuned-sst-2-english",
    revision="af0f99b",
)

# Suspicious patterns → block hallucinations
SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",
    r"\btracking number\b",
    r"\bAWB\b",
    r"\bETA\b",
    r"\border id\b",
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


def local_summarize(text: str) -> str:
    try:
        if not text.strip():
            return "No summary available."
        summary = hf_summarizer(text[:1000], max_length=130, min_length=30, do_sample=False)
        return summary[0].get("summary_text", "Summary unavailable.")
    except Exception:
        return "Summary unavailable."


def local_classify(text: str) -> str:
    try:
        if not text.strip():
            return "neutral"
        result = hf_sentiment(text[:500])[0]
        label = result["label"].lower()
        if "neg" in label:
            return "negative"
        if "pos" in label:
            return "positive"
        return "neutral"
    except:
        return "neutral"


# ============================================================
#                       FILTER NODE
# ============================================================

def filter_node(state: EmailState) -> EmailState:
    email = state.current_email
    email_id = email.get("id", "N/A")

    logger.info(f"[Filtering] Email ID: {email_id}")

    try:
        try:
            classification = filtering_agent.filter_email(email)
        except Exception as e:
            logger.warning(f"[Filter] Gemini failed, using fallback sentiment: {e}")
            classification = local_classify(email.get("body", ""))

        state.classification = classification
        state.metadata[email_id] = {"classification": classification}

        if classification == "negative":
            state.requires_human_review = True

        return state

    except Exception as e:
        state.classification = "error"
        state.processing_error = str(e)
        return state


# ============================================================
#                     SUMMARIZATION NODE
# ============================================================

def summarize_node(state: EmailState) -> EmailState:
    email = state.current_email
    email_id = email.get("id", "N/A")

    logger.info(f"[Summarization] Email ID: {email_id}")

    if state.classification in ["spam", "promotional"]:
        state.summary = "Skipped."
        return state

    try:
        try:
            summary = summarization_agent.summarize_email(email)
        except Exception as e:
            logger.warning(f"[Summarization] Gemini failed → fallback: {e}")
            summary = local_summarize(email.get("body", ""))

        # sanitize summary
        if not summary or _contains_suspicious(summary):
            summary = "The customer has shared a message and is requesting assistance."

        state.summary = summary
        state.metadata[email_id]["summary"] = summary
        return state

    except Exception as e:
        state.summary = "Summary unavailable."
        state.processing_error = str(e)
        return state


# ============================================================
#                      RESPONSE NODE
# ============================================================

def respond_node(state: EmailState, your_name: str, recipient_name: str) -> EmailState:
    email = state.current_email
    email_id = email.get("id", "N/A")
    body_text = email.get("body", "")

    if state.classification in ["spam", "promotional"]:
        state.generated_response_body = "Skipped (spam/promotional)"
        return state

    logger.info(f"[Response] Email ID: {email_id}")

    # 1. Retrieve KB context (does not enter LLM)
    kb_context = query_knowledge_base(state.summary or body_text).strip()
    state.metadata[email_id]["kb_context"] = kb_context[:400]

    # 2. Try Gemini
    try:
        response_body = response_agent.generate_response(
            email=email,
            summary=state.summary,
            recipient_name=recipient_name,
            your_name=your_name,
        )
        response_source = "gemini"
    except Exception as e:
        logger.warning(f"[Response] Gemini failed → using custom fallback: {e}")
        response_body = get_custom_fallback(state.summary, body_text)   # ★ new fallback logic
        response_source = "custom_fallback"

    # 3. If Gemini hallucinated → sanitize + fallback
    if _contains_suspicious(response_body):
        logger.warning("[Response] Suspicious Gemini output → sanitizing + fallback.")
        response_body = get_custom_fallback(state.summary, body_text)
        response_source = "sanitized_custom_fallback"
        state.requires_human_review = True

    # 4. Confidence score
    confidence = 1.0
    if response_source != "gemini":
        confidence -= 0.4
    if len(response_body) < 60:
        confidence -= 0.2
    confidence = max(0.0, min(1.0, round(confidence, 2)))

    state.metadata[email_id]["response_source"] = response_source
    state.metadata[email_id]["confidence"] = confidence

    # 5. Priority rules
    if "urgent" in body_text.lower() or "asap" in body_text.lower():
        state.requires_human_review = True
    if state.classification == "negative":
        state.requires_human_review = True

    # 6. Final formatting (adds greeting + signature)
    formatted_email = format_email(
        subject=email.get("subject", "Re: No Subject"),
        recipient_name=recipient_name,
        body=response_body,
        user_name=your_name,
    )

    state.generated_response_body = response_body
    state.formatted_email = formatted_email
    return state


# ============================================================
#                    SUPERVISOR GRAPH
# ============================================================

def route_after_filtering(state: EmailState) -> str:
    if state.classification in ["spam", "promotional"]:
        return "end_workflow"
    if state.processing_error:
        return "end_workflow"
    return "summarize"


def supervisor_langgraph(selected_email: dict, your_name: str, recipient_name: str) -> EmailState:
    email_id = selected_email.get("id", "N/A")

    initial_state = EmailState(
        current_email=selected_email,
        current_email_id=email_id,
        metadata={email_id: {}},
        emails=[selected_email],
    )

    workflow = StateGraph(EmailState)

    workflow.add_node("filter", filter_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("respond", partial(respond_node, your_name=your_name, recipient_name=recipient_name))

    workflow.set_entry_point("filter")

    workflow.add_conditional_edges(
        "filter",
        route_after_filtering,
        {"summarize": "summarize", "end_workflow": END},
    )
    workflow.add_edge("summarize", "respond")
    workflow.add_edge("respond", END)

    app = workflow.compile()

    try:
        final_state = app.invoke(initial_state)
        return EmailState(**final_state)
    except Exception as e:
        logger.critical(f"[Supervisor] Workflow crashed: {e}")
        return EmailState(
            current_email=selected_email,
            current_email_id=email_id,
            classification="error",
            summary="Failed.",
            generated_response_body="Workflow error.",
            processing_error=str(e),
        )
