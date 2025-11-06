from langgraph.graph import END, StateGraph
from agents import filtering_agent, summarization_agent, response_agent
from core.state import EmailState
from utils.logger import get_logger
from functools import partial
from datetime import datetime

# --- RAG Integration ---
from knowledge_base.query import query_knowledge_base

logger = get_logger(__name__)

# ============================================================
#                     PIPELINE NODES
# ============================================================

def filter_node(state: EmailState) -> EmailState:
    """Filters and classifies an email using Gemini."""
    email_data = state.current_email
    email_id = email_data.get("id", "N/A")
    logger.info(f"[Filtering] Started for email ID: {email_id}")

    try:
        classification = filtering_agent.filter_email(email_data)
        state.classification = classification
        state.metadata[email_id] = state.metadata.get(email_id, {})
        state.metadata[email_id]["classification"] = classification
        state.processing_error = None
        logger.info(f"[Filtering] Completed for ID {email_id} — Classification: {classification}")
    except Exception as e:
        state.classification = "unknown"
        state.metadata[email_id] = state.metadata.get(email_id, {})
        state.metadata[email_id]["classification"] = "error_during_filtering"
        state.processing_error = f"Filtering failed: {str(e)}"
        logger.error(f"[Filtering] Error for email ID {email_id}: {e}", exc_info=True)

    return state


def summarize_node(state: EmailState) -> EmailState:
    """Summarizes email content using Gemini."""
    email_data = state.current_email
    email_id = email_data.get("id", "N/A")
    logger.info(f"[Summarization] Started for email ID: {email_id}")

    try:
        if state.classification in ["spam", "promotional"] or state.processing_error:
            state.summary = "Summary skipped due to classification or previous error."
            logger.info(f"[Summarization] Skipped for email ID: {email_id}")
        else:
            summary = summarization_agent.summarize_email(email_data)
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
    """Generates an AI response using Gemini, enriched with RAG context."""
    email_data = state.current_email
    email_id = email_data.get("id", "N/A")

    if state.classification in ["spam", "promotional"] or state.processing_error:
        state.generated_response_body = "Skipped — email filtered out or errored earlier."
        state.metadata[email_id]["response_status"] = "skipped"
        logger.info(f"[Response] Skipped for email ID {email_id}.")
        return state

    try:
        logger.info(f"[RAG] Retrieving knowledge base context for email ID: {email_id}")
        query_input = state.summary or email_data.get("body", "")
        kb_context = query_knowledge_base(query_input)
        logger.debug(f"[RAG] KB context retrieved (first 250 chars): {kb_context[:250]}")

        # Combine knowledge and summary clearly
        combined_context = (
            f"Relevant company knowledge:\n{kb_context.strip()}\n\n"
            f"Email summary:\n{state.summary}\n\n"
            f"Original email:\n{email_data.get('body', '')}"
        )

        logger.info(f"[Response] Generating Gemini response for ID {email_id}")
        response_text = response_agent.generate_response(
            email=email_data,
            summary=combined_context,  # Combined context + email summary
            recipient_name=recipient_name,
            your_name=your_name
        )

        state.generated_response_body = response_text
        state.metadata[email_id]["raw_generated_response"] = response_text
        state.processing_error = None

        # Flag for human review if needed
        state.requires_human_review = (
            state.classification == "needs_review"
            or "?" in response_text and state.classification != "spam"
        )

        if state.requires_human_review:
            state.metadata[email_id]["response_status"] = "awaiting_human_review"
            logger.info(f"[Response] ID {email_id} flagged for human review.")
        else:
            state.metadata[email_id]["response_status"] = "ready_to_send"

        # Track full history
        state.history.append({
            "email_id": email_id,
            "classification": state.classification,
            "summary": state.summary,
            "raw_response": state.generated_response_body,
            "requires_human_review": state.requires_human_review,
            "timestamp": email_data.get("timestamp") or datetime.now().isoformat(),
        })

        logger.info(f"[Response] Completed successfully for ID: {email_id}")

    except Exception as e:
        state.generated_response_body = "Response generation failed."
        state.metadata[email_id]["response_status"] = "error_during_response_generation"
        state.processing_error = f"Response generation failed: {str(e)}"
        logger.error(f"[Response] Error for email ID {email_id}: {e}", exc_info=True)

    return state

# ============================================================
#                   ROUTING + SUPERVISOR
# ============================================================

def route_after_filtering(state: EmailState) -> str:
    """Decides next step after filtering."""
    if state.classification in ["spam", "promotional"]:
        logger.info(f"[Supervisor] Email {state.current_email_id} classified as {state.classification}. Ending workflow.")
        return "end_workflow"
    elif state.processing_error:
        logger.warning(f"[Supervisor] Email {state.current_email_id} encountered an error. Ending workflow.")
        return "end_workflow"
    return "summarize"


def supervisor_langgraph(selected_email: dict, your_name: str, recipient_name: str) -> EmailState:
    """Supervises the entire LangGraph-driven email processing workflow."""
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
        if "quota" in str(e).lower() or "429" in str(e):
            logger.warning(f"[Supervisor] Quota exceeded for email ID {email_id}. Skipping.")
            final_state_instance = EmailState(
                current_email=selected_email,
                current_email_id=email_id,
                classification="error",
                summary="Quota exceeded.",
                generated_response_body="Gemini quota exceeded. Retry later.",
                processing_error="Quota exceeded",
            )
        else:
            logger.critical(f"[Supervisor] Critical error during LangGraph execution: {e}", exc_info=True)
            final_state_instance = EmailState(
                current_email=selected_email,
                current_email_id=email_id,
                classification="error",
                summary="LangGraph invocation failed.",
                generated_response_body="Error during workflow execution.",
                processing_error=f"LangGraph execution failed: {str(e)}",
            )

    return final_state_instance
