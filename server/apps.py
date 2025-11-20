import os
import re
import time
import csv
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Core system
from core.supervisor import supervisor_langgraph
from core.email_ingestion import fetch_email
from core.state import EmailState
from knowledge_base.query import query_knowledge_base
from utils.records_manager import log_email_record, RECORDS_CSV_PATH
from utils.logger import get_logger
from utils.formatter import FALLBACK_RESPONSE

# ---------------------------------------------------------
# App & Logger
# ---------------------------------------------------------
logger = get_logger(__name__, log_to_file=True)

app = FastAPI(
    title="ShipCube AI Email Agent",
    version="3.0.0",
    description="Production-grade AI Email Automation System for Logistics"
)

# ---------------------------------------------------------
# Security: CORS (allow only local + ShipCube domain)
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# Templates & Static Files
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ---------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# Anti-prompt-injection helpers & limits
# ---------------------------------------------------------
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
    # remove suspicious phrases completely (replace with placeholder)
    cleaned = PROMPT_INJECTION_RE.sub("[redacted_instruction]", text)
    # remove any weird control characters and trim
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


# ---------------------------------------------------------
# Global exception handler (no stack traces leaked to clients)
# ---------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[GLOBAL ERROR] {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": "An unexpected error occurred."}
    )


# ---------------------------------------------------------
# Startup check: ensure knowledge base available
# ---------------------------------------------------------
@app.on_event("startup")
def startup_check():
    try:
        logger.info("[Startup] Validating knowledge base availability...")
        # lightweight test query (should not be expensive)
        ctx = query_knowledge_base("ShipCube overview")
        logger.info("[Startup] Knowledge base check OK. Preview: %s", (ctx or "")[:200])
    except Exception as e:
        logger.error(f"[Startup] Knowledge base validation failed: {e}", exc_info=True)


# ---------------------------------------------------------
# Root & Dashboard
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <h2> ShipCube AI Email Automation API</h2>
    <p>Use the dashboard and API docs below:</p>
    <ul>
        <li><a href='/dashboard'>Dashboard</a></li>
        <li><a href='/docs'>Swagger Docs</a></li>
        <li><a href='/redoc'>API Reference</a></li>
        <li><a href='/health'>Health Check</a></li>
    </ul>
    """


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    records = []
    if RECORDS_CSV_PATH.exists():
        try:
            with open(RECORDS_CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                records = sorted(reader, key=lambda r: r.get("Timestamp", ""), reverse=True)
        except Exception as e:
            logger.error(f"[Dashboard] Error reading records.csv: {e}")
    return templates.TemplateResponse("dashboard.html", {"request": request, "records": records[:75]})


# ---------------------------------------------------------
# Health check (restricted to localhost by default)
# ---------------------------------------------------------
@app.get("/health")
async def health_check(request: Request):
    client_ip = request.client.host if request.client else None
    allowed_ips = {"127.0.0.1", "localhost", "::1"}
    # allow on server if running in docker or internal (you can extend via env)
    extra_allowed = os.getenv("ALLOWED_HEALTH_IPS")
    if extra_allowed:
        allowed_ips.update(ip.strip() for ip in extra_allowed.split(",") if ip.strip())
    if client_ip not in allowed_ips:
        logger.warning(f"[Health] Access denied from IP: {client_ip}")
        raise HTTPException(status_code=403, detail="Health endpoint restricted")
    return {"status": "ok", "time": datetime.now().isoformat()}


# ---------------------------------------------------------
# Process Email Endpoint (safe & sanitized)
# ---------------------------------------------------------
@app.post("/process_email", response_model=ProcessEmailResponse)
async def process_email_api(req: EmailRequest, request: Request):
    start_time = time.time()

    # Basic size limit
    if len(req.body or "") > MAX_EMAIL_BODY_CHARS:
        logger.warning("[ProcessEmail] Rejected email: body too large (%d chars)", len(req.body or ""))
        raise HTTPException(status_code=400, detail=f"Email body too large (max {MAX_EMAIL_BODY_CHARS} chars)")

    # Sanitize input to prevent prompt injection
    sanitized_body = sanitize_user_text(req.body)
    if sanitized_body != req.body:
        logger.info("[ProcessEmail] Prompt-injection patterns removed from input.")

    email_data = {
        "from": req.sender_email,
        "sender_name": req.sender_name,
        "subject": req.subject,
        # pass sanitized body into pipeline (keeps original in records)
        "body": sanitized_body,
    }

    try:
        # Run pipeline
        state: EmailState = supervisor_langgraph(
            selected_email=email_data,
            your_name="ShipCube",
            recipient_name=req.sender_name,
        )

        # Lightweight token/size logging (approx)
        body_words = len((req.body or "").split())
        summary_words = len((state.summary or "").split())
        logger.info(
            "[TokenStats] processed email | body_words=%d summary_words=%d elapsed=%.2fs",
            body_words, summary_words, time.time() - start_time
        )

        # Log result (we store the original body in records for auditing)
        log_email_record(
            {
                "Timestamp": datetime.now().isoformat(),
                "Sender Email": req.sender_email,
                "Sender Name": req.sender_name,
                "Original Subject": req.subject,
                "Original Content": req.body,
                "Classification": state.classification,
                "Summary": state.summary,
                "Generated Response": state.generated_response_body,
                "Requires Human Review": state.requires_human_review,
                "Response Status": "Processed via API",
                "Processing Error": state.processing_error,
            }
        )

        return ProcessEmailResponse(
            status="success",
            classification=state.classification,
            summary=state.summary,
            generated_response=(state.generated_response_body or "")[:400],
            requires_review=state.requires_human_review,
            processing_error=state.processing_error,
            timestamp=datetime.now().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Process Email] Pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Pipeline failure")


# ---------------------------------------------------------
# Fetch latest processed records as JSON
# ---------------------------------------------------------
@app.get("/api/records")
async def get_records(limit: int = 50):
    if not RECORDS_CSV_PATH.exists():
        return {"count": 0, "records": []}
    try:
        with open(RECORDS_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = sorted(reader, key=lambda r: r.get("Timestamp", ""), reverse=True)
    except Exception as e:
        logger.error(f"[API Records] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not read records file")
    return {
        "count": len(rows[:limit]),
        "records": rows[:limit],
        "stats": {
            "positive": sum(1 for r in rows if r.get("Classification") == "positive"),
            "negative": sum(1 for r in rows if r.get("Classification") == "negative"),
            "neutral": sum(1 for r in rows if r.get("Classification") == "neutral"),
            "needs_review": sum(1 for r in rows if str(r.get("Requires Human Review")).lower() == "true"),
        },
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------
# Query Knowledge Base (RAG)
# ---------------------------------------------------------
@app.get("/query_kb")
async def query_kb_api(query: str):
    try:
        context = query_knowledge_base(query)
        return {"query": query, "result": context}
    except Exception as e:
        logger.error(f"[KB Query] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Knowledge base query failed")


# ---------------------------------------------------------
# Batch run (rate-limited)
# ---------------------------------------------------------
@app.get("/batch_run")
async def batch_run(simulate: bool = True, limit: int = 3):
    try:
        emails = fetch_email(simulate=simulate, limit=limit)
        if not emails:
            return {"message": "No emails fetched"}
        results = []
        for email_data in emails:
            # sanitize fetched content as well
            email_data["body"] = sanitize_user_text(email_data.get("body", ""))
            state = supervisor_langgraph(
                selected_email=email_data,
                your_name="ShipCube",
                recipient_name=email_data.get("sender_name", "Customer"),
            )
            results.append({
                "subject": email_data.get("subject"),
                "classification": state.classification,
                "requires_review": state.requires_human_review,
            })
            time.sleep(6)  # avoid Gemini rate limit
        return {
            "count": len(results),
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"[Batch Run] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Batch run failed")
