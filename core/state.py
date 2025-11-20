from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmailState:
    """
    Global state object passed through every node of the LangGraph workflow.

    Tracks:
      - Email input
      - Agent outputs (classification, summary, response body)
      - Metadata
      - Errors
      - Human-review flags
      - RAG context
      - Priority / confidence scores
      - Final formatted email (ready to send)
    """

    # ------------------------------
    # Base email data
    # ------------------------------
    emails: List[Dict[str, Any]] = field(default_factory=list)
    current_email: Dict[str, Any] = field(default_factory=dict)
    current_email_id: Optional[str] = None

    # ------------------------------
    # Metadata for analytics
    # ------------------------------
    metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    # ------------------------------
    # Pipeline outputs
    # ------------------------------
    classification: Optional[str] = None
    summary: Optional[str] = None
    generated_response_body: Optional[str] = None
    formatted_email: Optional[str] = None  # final full email after formatting

    # ------------------------------
    # Error & workflow control
    # ------------------------------
    processing_error: Optional[str] = None
    requires_human_review: bool = False

    # ------------------------------
    # RAG + Confidence + Priority
    # ------------------------------
    retrieved_context: Optional[str] = None
    confidence_score: Optional[float] = None      # future scoring model
    priority: Optional[str] = None                # “high”, “normal”, etc.

    # ------------------------------
    # Timestamps
    # ------------------------------
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    # ------------------------------
    # Methods
    # ------------------------------
    def update_timestamp(self):
        """Refresh internal timestamp when state is modified."""
        self.last_updated = datetime.now().isoformat()

    def record_history(self, stage: str, note: str = ""):
        """
        Store a structured snapshot after each pipeline stage.
        Useful for debugging, dashboards, audit logs, QA, etc.
        """
        snapshot = {
            "stage": stage,
            "timestamp": datetime.now().isoformat(),
            "classification": self.classification,
            "summary": self.summary,
            "generated_response": self.generated_response_body,
            "formatted_email": self.formatted_email,
            "error": self.processing_error,
            "requires_human_review": self.requires_human_review,
            "priority": self.priority,
            "confidence_score": self.confidence_score,
            "note": note,
        }
        self.history.append(snapshot)
