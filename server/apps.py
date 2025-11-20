# server/apps.py
"""
Rewritten FastAPI app for ShipCube AI Email Agent.

- Prometheus instrumentator is initialized at module import time so middleware gets
  added before the app starts (prevents "Cannot add middleware after an application has started").
- CSV reading is done in a thread via asyncio.to_thread to avoid blocking event loop.
- Timestamp parsing normalizes to UTC for safe sorting (handles naive and aware ISO strings).
- Clear, modular helpers and improved error handling.
"""

import os
import re
import time
import csv
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Prometheus instrumentator
from prometheus_fastapi_instrumentator import Instrumentator

# Core system (existing modules in your project)
from core.supervisor import supervisor_langgraph
from core.email_ingestion import fetch_email
from core.state import EmailState
from knowledge_base.query import query_knowledge_base
from utils.records_manager import log_email_record, RECORDS_CSV_PATH
from utils.logger import get_logger
from utils.formatter import FALLBACK_RESPONSE

# Custom metrics from monitoring/metrics.py (existing)
from monitoring.metrics import (
    EMAILS_PROCESSED,
    EMAIL_CLASSIFICATION_COUNTER,
    EMAIL_LATENCY,
    KB_QUERIES,
    KB_EMPTY_RESULTS,
    PROMPT_INJECTION_DETECTED,
    SANITIZATION_TRIGGERED,
    PIPELINE_ACTIVE,
    record_gemini_failure,
    set_kb_health,
    mark_email_processed,
)

# ---------------------------
# App & basic config
# ---------------------------
logger = get_logger(__name__, log_to_file=True)
app = FastAPI(
    title="ShipCube AI Email Agent",
    version="3.1.0",
    description="Production-grade AI Email Automation System with Monitoring Enabled"
)

# ---------------------------
# Prometheus instrumentator - initialize early (module import)
# ---------------------------
instrumentator = Instrumentator()
try:
    # Instrument app now so middleware is added before uvicorn starts serving requests.
    instrumentator.instrument(app)
    instrumentator.expose(app)
    logger.info("[Init] Prometheus Instrumentator initialized at import time.")
except Exception as e:
    logger.error("[Init] Prometheus Instrumentator failed to initialize at import: %s", e, exc_info=True)

# ---------------------------
# CORS
# ---------------------------
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://shipcube.ai",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Templates & Static
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ---------------------------
# Pydantic request/response models
# ---------------------------
class EmailRequest(BaseModel):
    sender_email: str
    sender_name: Optional[str] = "Customer"
    subject: str
    body: str


class ProcessEmailResponse(BaseModel):
    status: str
    classification: Optional[str]
    summary: Optional[str]
    generated_response: Optional[str]
    requires_review: bool
    processing_error: Optional[str]
    timestamp: str


# ---------------------------
# Prompt injection sanitizer
# ---------------------------
MAX_EMAIL_BODY_CHARS = int(os.getenv("MAX_EMAIL_BODY_CHARS", "5000"))

PROMPT_INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"you are now",
    r"act as",
    r"system:",
    r"assistant:",
    r"follow these instructions",
    r"obey the following",
]
PROMPT_INJECTION_RE = re.compile("|".join(PROMPT_INJECTION_PATTERNS), re.IGNORECASE)


def sanitize_user_text(text: str) -> str:
    if not text:
        return text
    cleaned = PROMPT_INJECTION_RE.sub("[redacted_instruction]", text)
    return " ".join(cleaned.split()).strip()


# ---------------------------
# Helpers: timestamp parsing & CSV helpers
# ---------------------------
def _parse_iso_to_utc(dt_str: str) -> datetime:
    """
    Parse an ISO-style timestamp string and return timezone-aware datetime in UTC.
    If parsing fails, return a very small UTC datetime to push invalid timestamps to the end.
    Accepts naive or offset-aware ISO strings.
    """
    if not dt_str or not isinstance(dt_str, str):
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        # handle trailing Z (UTC) or offset-aware strings
        # Python 3.11+ supports fromisoformat with offsets; replace 'Z' with '+00:00' for compatibility
        s = dt_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        # fallback: try parsing only the date portion or return min-utc
        try:
            return datetime.fromisoformat(dt_str.split("T")[0]).replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)


async def _read_records_csv_async(path: Path) -> List[Dict[str, Any]]:
    """
    Read CSV file in a thread to avoid blocking the event loop.
    Returns list of dict rows (csv.DictReader semantics).
    Filters out completely-empty rows.
    """
    def _read_sync(p: Path):
        rows = []
        if not p.exists():
            return rows
        with p.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                # keep rows that have at least one non-empty string field
                if any((v and isinstance(v, str) and v.strip()) for v in r.values()):
                    rows.append(r)
        return rows

    return await asyncio.to_thread(_read_sync, path)


def _normalize_row_for_api(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse JSON fields if present and return a normalized shallow copy.
    """
    parsed = dict(r)
    # parse metadata/history if JSON encoded
    for key in ("Metadata", "metadata", "Meta", "StateMetadata"):
        if key in parsed and parsed.get(key):
            try:
                parsed["metadata_parsed"] = json.loads(parsed.get(key))
            except Exception:
                parsed["metadata_parsed"] = parsed.get(key)
    for key in ("History", "history"):
        if key in parsed and parsed.get(key):
            try:
                parsed["history_parsed"] = json.loads(parsed.get(key))
            except Exception:
                parsed["history_parsed"] = parsed.get(key)
    return parsed


# ---------------------------
# Global exception handler
# ---------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[GLOBAL ERROR] {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": "An unexpected error occurred."}
    )


# ---------------------------
# Startup event: KB health check (non-blocking)
# ---------------------------
@app.on_event("startup")
async def startup_event():
    # lightweight KB check to set metric; don't block if KB is slow
    try:
        logger.info("[Startup] Validating KB…")
        # run the KB query in a thread if it is blocking
        ctx = await asyncio.to_thread(query_knowledge_base, "ShipCube overview")
        logger.info("[Startup] KB Ready. Preview: %s", (ctx or "")[:200])
        set_kb_health(bool(ctx))
    except Exception as e:
        logger.error("[Startup] KB validation failed: %s", e, exc_info=True)
        set_kb_health(False)


# ---------------------------
# Basic routes
# ---------------------------
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <h2>ShipCube AI Email Automation API</h2>
    <p>Use the dashboard and API docs below:</p>
    <ul>
        <li><a href='/dashboard'>Dashboard</a></li>
        <li><a href='/docs'>Swagger Docs</a></li>
        <li><a href='/redoc'>API Reference</a></li>
        <li><a href='/health'>Health Check</a></li>
        <li><a href='/metrics'>Prometheus Metrics</a></li>
    </ul>
    """


# ---------------------------
# Dashboard (renders template) - async CSV read
# ---------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    records: List[Dict[str, Any]] = []
    try:
        rows = await _read_records_csv_async(RECORDS_CSV_PATH)
        # sort rows by timestamp safely (UTC-aware)
        def key_fn(r):
            t = r.get("Timestamp") or r.get("timestamp") or ""
            return _parse_iso_to_utc(t)
        records = sorted(rows, key=key_fn, reverse=True)
    except Exception as e:
        logger.error("[Dashboard] Cannot read records.csv: %s", e, exc_info=True)

    # limit displayed rows
    return templates.TemplateResponse("dashboard.html", {"request": request, "records": records[:75]})


# ---------------------------
# Health endpoint (restricted by IP)
# ---------------------------
@app.get("/health")
async def health_check(request: Request):
    allowed = {"127.0.0.1", "localhost", "::1"}
    client_ip = request.client.host if request.client else None

    extra = os.getenv("ALLOWED_HEALTH_IPS")
    if extra:
        allowed.update(ip.strip() for ip in extra.split(",") if ip.strip())

    if client_ip not in allowed:
        logger.warning(f"[Health] Access blocked from: {client_ip}")
        raise HTTPException(status_code=403, detail="Health endpoint restricted")

    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ---------------------------
# Process Email API (instrumented & async-safe)
# ---------------------------
@app.post("/process_email", response_model=ProcessEmailResponse)
async def process_email_api(req: EmailRequest):
    start = time.time()

    if len(req.body or "") > MAX_EMAIL_BODY_CHARS:
        logger.warning("[ProcessEmail] Rejected email: body too large (%d chars)", len(req.body or ""))
        raise HTTPException(status_code=400, detail=f"Email body too large (max {MAX_EMAIL_BODY_CHARS} chars)")

    sanitized_body = sanitize_user_text(req.body)
    if sanitized_body != req.body:
        logger.info("[ProcessEmail] Prompt-injection patterns removed from input.")
        try:
            PROMPT_INJECTION_DETECTED.inc()
        except Exception:
            logger.debug("[Metrics] PROMPT_INJECTION_DETECTED inc failed (ignored).")

    email_data = {
        "from": req.sender_email,
        "sender_name": req.sender_name,
        "subject": req.subject,
        "body": sanitized_body,
    }

    pipeline_inc_done = False
    try:
        PIPELINE_ACTIVE.inc()
        pipeline_inc_done = True
    except Exception:
        pipeline_inc_done = False

    success = False
    try:
        # Supervisor may be blocking; run in thread if necessary
        state: EmailState = await asyncio.to_thread(
            supervisor_langgraph,
            dict(selected_email=email_data, your_name="ShipCube", recipient_name=req.sender_name)
        ) if not asyncio.iscoroutinefunction(supervisor_langgraph) else await supervisor_langgraph(
            selected_email=email_data,
            your_name="ShipCube",
            recipient_name=req.sender_name,
        )

        # metrics: classification
        try:
            EMAIL_CLASSIFICATION_COUNTER.labels(classification=(state.classification or "unknown")).inc()
        except Exception:
            try:
                EMAIL_CLASSIFICATION_COUNTER.labels(classification="unknown").inc()
            except Exception:
                logger.debug("[Metrics] EMAIL_CLASSIFICATION_COUNTER inc failed (ignored).")

        # sanitization triggered metric
        try:
            if state.metadata.get(state.current_email_id, {}).get("sanitization_reason"):
                SANITIZATION_TRIGGERED.labels(stage="response_generator").inc()
        except Exception:
            logger.debug("[Metrics] SANITIZATION_TRIGGERED inc failed (ignored).")

        # persist original body for auditing (log_email_record may be blocking - run in thread)
        record_payload = {
            "Timestamp": datetime.now(timezone.utc).isoformat(),
            "Sender Email": req.sender_email,
            "Sender Name": req.sender_name,
            "Original Subject": req.subject,
            "Original Content": req.body,
            "Classification": state.classification,
            "Summary": state.summary,
            "Generated Response": state.generated_response_body,
            "Requires Human Review": state.requires_human_review,
            "Response Status": state.metadata.get(state.current_email_id, {}).get("response_status", "processed"),
            "Processing Error": state.processing_error,
            "Metadata": json.dumps(state.metadata.get(state.current_email_id, {}), default=str),
            "History": json.dumps(state.history, default=str),
        }
        await asyncio.to_thread(log_email_record, record_payload, RECORDS_CSV_PATH)

        # success / failure counts
        if state.processing_error:
            EMAILS_PROCESSED.labels(status="failed").inc()
            mark_email_processed(False)
        else:
            EMAILS_PROCESSED.labels(status="success").inc()
            mark_email_processed(True)

        success = True

        return ProcessEmailResponse(
            status="success" if not state.processing_error else "error",
            classification=state.classification,
            summary=state.summary,
            generated_response=(state.generated_response_body or "")[:400],
            requires_review=state.requires_human_review,
            processing_error=state.processing_error,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Process Email] Pipeline error: {e}", exc_info=True)
        try:
            EMAILS_PROCESSED.labels(status="failed").inc()
        except Exception:
            logger.debug("[Metrics] EMAILS_PROCESSED inc failed (ignored).")
        mark_email_processed(False)
        raise HTTPException(status_code=500, detail="Pipeline failure")
    finally:
        if pipeline_inc_done:
            try:
                PIPELINE_ACTIVE.dec()
            except Exception:
                logger.debug("[ProcessEmail] Failed to decrement PIPELINE_ACTIVE (ignored).")
        logger.info(f"[ProcessEmail] finished | success={success} elapsed={time.time() - start:.2f}s")


# ---------------------------
# Records JSON endpoint (async-safe)
# ---------------------------
@app.get("/api/records")
async def get_records(limit: int = 50) -> Dict[str, Any]:
    if not RECORDS_CSV_PATH.exists():
        return {"count": 0, "records": []}

    try:
        rows = await _read_records_csv_async(RECORDS_CSV_PATH)
        normalized: List[Dict[str, Any]] = [_normalize_row_for_api(r) for r in rows]

        def _safe_time_key(item: Dict[str, Any]):
            t = item.get("Timestamp") or item.get("timestamp") or ""
            return _parse_iso_to_utc(t)

        normalized_sorted = sorted(normalized, key=_safe_time_key, reverse=True)
        limited = normalized_sorted[:limit]

        stats = {
            "positive": sum(1 for r in rows if r.get("Classification") == "positive"),
            "negative": sum(1 for r in rows if r.get("Classification") == "negative"),
            "neutral": sum(1 for r in rows if r.get("Classification") == "neutral"),
            "spam": sum(1 for r in rows if r.get("Classification") == "spam"),
            "promotional": sum(1 for r in rows if r.get("Classification") == "promotional"),
            "needs_review": sum(1 for r in rows if str(r.get("Requires Human Review")).lower() == "true"),
        }

        return {"count": len(limited), "records": limited, "stats": stats, "timestamp": datetime.now(timezone.utc).isoformat()}

    except Exception as e:
        logger.error(f"[API Records] Error reading/parsing records.csv: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not read records file")


# ---------------------------
# Knowledge base query endpoint
# ---------------------------
@app.get("/query_kb")
async def query_kb_api(query: str):
    try:
        KB_QUERIES.inc()
        # call KB in thread to avoid blocking
        context = await asyncio.to_thread(query_knowledge_base, query)
        if not context:
            KB_EMPTY_RESULTS.inc()
        return {"query": query, "result": context}
    except Exception as e:
        logger.error(f"[KB Query] {e}", exc_info=True)
        KB_EMPTY_RESULTS.inc()
        raise HTTPException(status_code=500, detail="Knowledge base query failed")


# ---------------------------
# Batch run endpoint (rate-limited)
# ---------------------------
@app.get("/batch_run")
async def batch_run(simulate: bool = True, limit: int = 3):
    try:
        emails = await asyncio.to_thread(fetch_email, simulate, limit)
        if not emails:
            return {"message": "No emails fetched"}
        results = []
        for email_data in emails:
            original = email_data.get("body", "")
            email_data["body"] = sanitize_user_text(original)
            if email_data["body"] != original:
                try:
                    PROMPT_INJECTION_DETECTED.inc()
                except Exception:
                    logger.debug("[Metrics] PROMPT_INJECTION_DETECTED inc failed (ignored).")

            # run supervisor in thread to avoid blocking
            state = await asyncio.to_thread(
                supervisor_langgraph,
                selected_email=email_data,
                your_name="ShipCube",
                recipient_name=email_data.get("sender_name", "Customer"),
            )

            results.append({
                "subject": email_data.get("subject"),
                "classification": state.classification,
                "requires_review": state.requires_human_review,
            })

            # sleep to respect rate limits (non-blocking)
            await asyncio.sleep(6)
        return {"count": len(results), "results": results, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"[Batch Run] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Batch run failed")
