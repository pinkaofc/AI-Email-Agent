# monitoring/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# ============================================================
#  SAFE HELPERS (used by agents to avoid crashing on metric ops)
# ============================================================

def safe_increment_counter(counter_obj, **labels):
    try:
        if labels:
            counter_obj.labels(**labels).inc()
        else:
            counter_obj.inc()
    except Exception:
        pass


def safe_observe(hist_obj, value, **labels):
    try:
        if labels:
            hist_obj.labels(**labels).observe(value)
        else:
            hist_obj.observe(value)
    except Exception:
        pass


# ============================================================
#  FILTERING METRICS
# ============================================================

FILTERING_COUNT = Counter(
    "shipcube_filtering_total",
    "Total filtering operations performed"
)

FILTERING_FAILURES = Counter(
    "shipcube_filtering_failures_total",
    "Total filtering failures"
)

FILTERING_LATENCY = Histogram(
    "shipcube_filtering_latency_seconds",
    "Time taken for filtering operation"
)

FILTERING_MODEL_USED = Counter(
    "shipcube_filtering_model_used_total",
    "Which model was used in filtering (gemini/huggingface/keyword/neutral)",
    ["model"]
)

FILTERING_LAST_SCORE = Gauge(
    "shipcube_filtering_last_score",
    "Stores last filtering confidence score (0–1)"
)


# ============================================================
#  SUMMARIZATION METRICS
# ============================================================

summarization_attempts_total = Counter(
    "shipcube_summarization_attempts_total",
    "Total Gemini summarization attempts"
)

summarization_failures_total = Counter(
    "shipcube_summarization_failures_total",
    "Total summarization failures"
)

summarization_fallback_used_total = Counter(
    "shipcube_summarization_fallback_total",
    "Times fallback summarization was used"
)

summarization_model_used_total = Counter(
    "shipcube_summarization_model_used_total",
    "Which summarization model was used",
    ["model"]  # gemini / huggingface / fallback
)

summarization_latency_seconds = Histogram(
    "shipcube_summarization_latency_seconds",
    "Time taken for summarization"
)


# ============================================================
#  RESPONSE GENERATION METRICS
# ============================================================

response_attempts_total = Counter(
    "shipcube_response_attempts_total",
    "Total Gemini response generation attempts"
)

response_failures_total = Counter(
    "shipcube_response_failures_total",
    "Total failures during response generation"
)

response_fallback_used_total = Counter(
    "shipcube_response_fallback_total",
    "Times fallback was used for response generation"
)

response_model_used_total = Counter(
    "shipcube_response_model_used_total",
    "Which model was used for response generation",
    ["model"]  # gemini / huggingface / fallback / sanitized
)

response_latency_seconds = Histogram(
    "shipcube_response_latency_seconds",
    "Latency of response generation"
)


# ============================================================
#  KNOWLEDGE BASE (RAG)
# ============================================================

KB_QUERIES = Counter(
    "shipcube_kb_queries_total",
    "Total KB queries"
)

KB_EMPTY_RESULTS = Counter(
    "shipcube_kb_empty_results_total",
    "KB queries that returned empty result"
)

KB_HEALTH = Gauge(
    "shipcube_kb_health_status",
    "KB health status (1 OK / 0 ERROR)"
)


# ============================================================
#  GEMINI METRICS (KEY ROTATION / FAILURES)
# ============================================================

GEMINI_CALLS = Counter(
    "shipcube_gemini_calls_total",
    "Total Gemini API calls made",
    ["module"]
)

GEMINI_FAILURES = Counter(
    "shipcube_gemini_failures_total",
    "Times Gemini API failed",
    ["module", "reason"]
)

GEMINI_FALLBACK_USED = Counter(
    "shipcube_gemini_fallback_used_total",
    "Times fallback was used instead of Gemini",
    ["module"]
)

GEMINI_KEY_HEALTH = Gauge(
    "shipcube_gemini_key_health",
    "Gemini API key health",
    ["api_key_id"]
)


def record_gemini_failure(module: str, reason: str):
    safe_increment_counter(GEMINI_FAILURES, module=module, reason=reason)
    safe_increment_counter(GEMINI_FALLBACK_USED, module=module)


# ============================================================
#  PIPELINE HEALTH
# ============================================================

PIPELINE_ACTIVE = Gauge(
    "shipcube_pipeline_active_count",
    "Number of active pipeline executions"
)

PIPELINES_STARTED = Counter(
    "shipcube_pipelines_started_total",
    "Pipelines started"
)

PIPELINES_FAILED = Counter(
    "shipcube_pipelines_failed_total",
    "Pipeline failures"
)

PIPELINES_SUCCEEDED = Counter(
    "shipcube_pipelines_succeeded_total",
    "Pipeline successes"
)


# ============================================================
#  APP-LEVEL EMAIL METRICS (used in apps.py)
# ============================================================

EMAILS_PROCESSED = Counter(
    "shipcube_emails_processed_total",
    "Emails processed",
    ["status"]
)

EMAIL_CLASSIFICATION_COUNTER = Counter(
    "shipcube_email_classification_total",
    "Classification count",
    ["classification"]
)

EMAIL_LATENCY = Histogram(
    "shipcube_email_processing_latency_seconds",
    "Email-to-response pipeline latency"
)

PROMPT_INJECTION_DETECTED = Counter(
    "shipcube_prompt_injection_detected_total",
    "Times user attempted prompt injection"
)

SANITIZATION_TRIGGERED = Counter(
    "shipcube_sanitization_triggered_total",
    "Times sanitization logic triggered",
    ["stage"]
)


def mark_email_processed(success: bool):
    EMAILS_PROCESSED.labels(
        status="success" if success else "failed"
    ).inc()


def set_kb_health(is_ok: bool):
    KB_HEALTH.set(1 if is_ok else 0)
