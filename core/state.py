from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmailState:
    """
    Represents the current working state of the email processing workflow.
    Tracks the email being processed, metadata, agent outputs, and errors.

    This object passes through the LangGraph nodes:
    filter → summarize → respond → (optional human review)
    """

    # All emails fetched or simulated
    emails: List[Dict[str, Any]] = field(default_factory=list)

    # History of processed states or actions
    history: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata per email (classification, summary, response, etc.)
    metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # The current email under processing
    current_email: Dict[str, Any] = field(default_factory=dict)
    current_email_id: Optional[str] = None

    # --- Agent outputs ---
    classification: Optional[str] = None        # Result from filtering_agent (e.g., "positive", "spam", "promotional")
    summary: Optional[str] = None               # Generated summary from summarization_agent
    generated_response_body: Optional[str] = None  # Final Gemini-generated response body

    # --- Error tracking ---
    processing_error: Optional[str] = None      # Any error encountered during workflow

    # --- Review flags ---
    requires_human_review: bool = False         # Flag for human intervention before sending

    # --- Utility fields (optional, for analytics or extended RAG tracking) ---
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    retrieved_context: Optional[str] = None     # Text retrieved from knowledge base (for debugging or fine-tuning)

    def update_timestamp(self):
        """Updates the state's last modified timestamp."""
        self.last_updated = datetime.now().isoformat()

    def record_history(self, stage: str, note: str = ""):
        """Helper to append state snapshot to history for debugging."""
        snapshot = {
            "stage": stage,
            "timestamp": datetime.now().isoformat(),
            "classification": self.classification,
            "summary": self.summary,
            "generated_response": self.generated_response_body,
            "error": self.processing_error,
            "note": note
        }
        self.history.append(snapshot)
