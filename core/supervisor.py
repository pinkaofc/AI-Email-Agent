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

logger = get_logger(__name__)

# ============================================================
#                   FALLBACK MODELS
# ============================================================

hf_summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
hf_sentiment = pipeline("sentiment-analysis")

FALLBACK_RESPONSE = (
    "Thank you for reaching out. We’ve received your message and our team will get back to you shortly."
)

def local_summarize(text: str) -> str:
    try:
        short_text = text[:1000] if text else ""
        if not short_text.strip():
            return "No summary available."
        summary = hf_summarizer(short_text, max_length=130, min_length=30, do_sample=False)
        return summary[0].get("summary_text", "Summary unavailable.")
    except Exception as e:
        logger.error(f"[LocalSummarizer] Failed: {e}")
        return "Summary unavailable."


def local_classify(text: str) -> str:
    try:
        short_text = text[:500] if text else ""
        if not short_text.strip():
            return "neutral"
        result = hf_sentiment(short_text)[0]
        label = result["label"].lower()
        return "negative" if "neg" in label else "positive" if "pos" in label else "neutral"
    except Exception as e:
        logger.error(f"[LocalClassifier] Failed: {e}")
        return "neutral"


# ============================================================
#                   PIPELINE NODES
# ============================================================

def filter_node(state: EmailState) -> EmailState:
    email_data = state.current_email
    email_id = email_data.get("id", "N/A")
    logger.info(f"[Filtering] Started for email ID: {email_id}")

    try:
        try:
            classification = filtering_agent.filter_email(email_data)
        except Exception as e:
            logger.warning(f"[Filtering] Gemini failed, using local model: {e}")
            classification = local_classify(email_data.get("body", ""))

        state.classification = classification
        state.metadata[email_id] = state.metadata.get(email_id, {})
        state.metadata[email_id]["classification"] = classification
        state.processing_error = None
        logger.info(f"[Filtering] Completed for ID {email_id} — Classification: {classification}")

    except Exception as e:
        state.classification = "unknown"
        state.metadata[email_id]["classification"] = "error_during_filtering"
        state.processing_error = f"Filtering failed: {str(e)}"
        logger.error(f"[Filtering] Error for email ID {email_id}: {e}", exc_info=True)

    return state


def summarize_node(state: EmailState) -> EmailState:
    email_data = state.current_email
    email_id = email_data.get("id", "N/A")
    logger.info(f"[Summarization] Started for email ID: {email_id}")

    try:
        if state.classification in ["spam", "promotional"] or state.processing_error:
            state.summary = "Summary skipped."
            logger.info(f"[Summarization] Skipped for ID: {email_id}")
        else:
            try:
                summary = summarization_agent.summarize_email(email_data)
            except Exception as e:
                logger.warning(f"[Summarization] Gemini failed, switching to local summarizer: {e}")
                summary = local_summarize(email_data.get("body", ""))

            state.summary = summary
            state.metadata[email_id]["summary"] = summary
            state.processing_error = None
            logger.info(f"[Summarization] Completed for ID {email_id}")

    except Exception as e:
        state.summary = "Summary generation failed."
        state.metadata[email_id]["summary"] = "error_during_summarization"
        state.processing_error = f"Summarization failed: {str(e)}"
        logger.error(f"[Summarization] Error for email ID {email_id}: {e}", exc_info=True)

    return state


def respond_node(state: EmailState, your_name: str, recipient_name: str) -> EmailState:
    email_data = state.current_email
    email_id = email_data.get("id", "N/A")

    if state.classification in ["spam", "promotional"] or state.processing_error:
        state.generated_response_body = "Skipped — filtered or errored earlier."
        state.metadata[email_id]["response_status"] = "skipped"
        logger.info(f"[Response] Skipped for ID {email_id}")
        return state

    try:
        logger.info(f"[RAG] Retrieving knowledge base context for email ID: {email_id}")
        query_input = state.summary or email_data.get("body", "")
        kb_context = query_knowledge_base(query_input)
        logger.debug(f"[RAG] KB context retrieved (first 250 chars): {kb_context[:250]}")

        combined_context = (
            f"Company Knowledge:\n{kb_context.strip()}\n\n"
            f"Email Summary:\n{state.summary}\n\n"
            f"Original Email:\n{email_data.get('body', '')}"
        )

        # Main Gemini generation with fallback
        logger.info(f"[Response] Generating response via Gemini...")
        try:
            response_text = response_agent.generate_response(
                email=email_data,
                summary=combined_context,
                recipient_name=recipient_name,
                your_name=your_name,
            )
        except Exception as e:
            logger.warning(f"[Response] Gemini quota exceeded, using fallback: {e}")
            response_text = (
                f"Hi {recipient_name},\n\n{FALLBACK_RESPONSE}\n\nBest regards,\n{your_name}"
            )

        # Guarantee message is not blank
        if not response_text.strip():
            logger.warning(f"[Response] Empty body generated for ID {email_id} — using fallback.")
            response_text = (
                f"Hi {recipient_name},\n\n{FALLBACK_RESPONSE}\n\nBest regards,\n{your_name}"
            )

        # Merge KB context internally (for internal logs, not user)
        if kb_context and "Company Knowledge" not in response_text:
            response_text += f"\n\n---\n[Internal KB Reference]\n{kb_context[:400]}"

        # Store AI-generated response
        state.generated_response_body = response_text
        state.metadata[email_id]["raw_generated_response"] = response_text
        state.requires_human_review = (
            state.classification == "needs_review"
            or "?" in response_text and state.classification != "spam"
        )
        state.metadata[email_id]["response_status"] = (
            "awaiting_human_review" if state.requires_human_review else "ready_to_send"
        )
        state.history.append({
            "email_id": email_id,
            "classification": state.classification,
            "summary": state.summary,
            "raw_response": state.generated_response_body,
            "requires_human_review": state.requires_human_review,
            "timestamp": email_data.get("timestamp") or datetime.now().isoformat(),
        })

        # Build final formatted email
        formatted_email = format_email(
            subject=email_data.get("subject", "Re: No Subject"),
            recipient_name=recipient_name,
            body=response_text,
            user_name=your_name,
        )
        state.formatted_email = formatted_email
        logger.debug(f"[Response] Final formatted email:\n{formatted_email}")

        logger.info(f"[Response] Completed successfully for ID: {email_id}")

    except Exception as e:
        state.generated_response_body = "Response generation failed."
        state.metadata[email_id]["response_status"] = "error_during_response_generation"
        state.processing_error = f"Response generation failed: {str(e)}"
        logger.error(f"[Response] Error for email ID {email_id}: {e}", exc_info=True)

    return state


# ============================================================
#                   SUPERVISOR GRAPH
# ============================================================

def route_after_filtering(state: EmailState) -> str:
    if state.classification in ["spam", "promotional"]:
        logger.info(f"[Supervisor] Email {state.current_email_id} marked as {state.classification}.")
        return "end_workflow"
    elif state.processing_error:
        logger.warning(f"[Supervisor] Email {state.current_email_id} encountered an error.")
        return "end_workflow"
    return "summarize"


def supervisor_langgraph(selected_email: dict, your_name: str, recipient_name: str) -> EmailState:
    email_id = selected_email.get("id", "N/A")
    initial_state = EmailState(
        current_email=selected_email,
        current_email_id=email_id,
        emails=[selected_email],
        metadata={email_id: {}},
    )

    workflow = StateGraph(EmailState)
    workflow.add_node("filter", filter_node)
    workflow.add_node("summarize", summarize_node)
    respond_partial_node = partial(respond_node, your_name=your_name, recipient_name=recipient_name)
    workflow.add_node("respond", respond_partial_node)

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
        final_state_dict = app.invoke(initial_state)
        final_state_instance = EmailState(**final_state_dict)
    except Exception as e:
        logger.critical(f"[Supervisor] Workflow execution failed: {e}", exc_info=True)
        final_state_instance = EmailState(
            current_email=selected_email,
            current_email_id=email_id,
            classification="error",
            summary="Execution failed.",
            generated_response_body="Workflow error occurred.",
            processing_error=f"Supervisor failure: {str(e)}",
        )

    return final_state_instance
