from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmailState:
    """
    Central state object passed across the LangGraph workflow.

    Tracks:
      • Raw email
      • Classification / summarization / response
      • RAG (knowledge base) results
      • Fallback usage & reasons
      • Safety flags (hallucinations, sanitization)
      • Confidence scores
      • Metrics-friendly metadata
      • Stage-by-stage history for full auditability
    """

    # ----------------------------------------------------
    # Base email payload
    # ----------------------------------------------------
    emails: List[Dict[str, Any]] = field(default_factory=list)
    current_email: Dict[str, Any] = field(default_factory=dict)
    current_email_id: Optional[str] = None

    # ----------------------------------------------------
    # Metadata and pipeline history
    # ----------------------------------------------------
    metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    # ----------------------------------------------------
    # Agent outputs
    # ----------------------------------------------------
    classification: Optional[str] = None
    summary: Optional[str] = None
    generated_response_body: Optional[str] = None
    formatted_email: Optional[str] = None

    # ----------------------------------------------------
    # Error / safety / review flags
    # ----------------------------------------------------
    processing_error: Optional[str] = None
    requires_human_review: bool = False
    hallucination_detected: bool = False
    sanitization_reason: Optional[str] = None  # <– NEW: supervisor uses this

    # ----------------------------------------------------
    # RAG (Knowledge Base)
    # ----------------------------------------------------
    retrieved_context: Optional[str] = None
    context_quality: Optional[float] = None

    # ----------------------------------------------------
    # Confidence + priority
    # ----------------------------------------------------
    confidence_score: Optional[float] = None
    priority: Optional[str] = "normal"

    # ----------------------------------------------------
    # Fallback tracking
    # ----------------------------------------------------
    used_fallback: bool = False
    fallback_reason: Optional[str] = None

    # ----------------------------------------------------
    # Timestamp
    # ----------------------------------------------------
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    # ====================================================
    # METHODS
    # ====================================================
    def update_timestamp(self):
        """Refresh last_modified timestamp."""
        self.last_updated = datetime.now().isoformat()

    def record_history(self, stage: str, note: str = ""):
        """
        Detailed audit trace of each stage.
        Supervisor calls this:
            - filter
            - summarize
            - respond
            - formatter
            - sanitize
        """
        self.history.append({
            "stage": stage,
            "timestamp": datetime.now().isoformat(),
            "classification": self.classification,
            "summary": self.summary,
            "generated_response_body": self.generated_response_body,
            "formatted_email": self.formatted_email,
            "retrieved_context": (self.retrieved_context or "")[:200],
            "priority": self.priority,
            "confidence_score": self.confidence_score,
            "requires_human_review": self.requires_human_review,
            "used_fallback": self.used_fallback,
            "fallback_reason": self.fallback_reason,
            "hallucination_detected": self.hallucination_detected,
            "sanitization_reason": self.sanitization_reason,
            "error": self.processing_error,
            "note": note,
        })
