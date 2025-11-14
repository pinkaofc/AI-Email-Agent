from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import csv
import time
from pathlib import Path

# --- Core Imports ---
from core.supervisor import supervisor_langgraph
from core.email_ingestion import fetch_email
from core.state import EmailState
from knowledge_base.query import query_knowledge_base
from utils.records_manager import log_email_record, RECORDS_CSV_PATH
from utils.logger import get_logger

# ------------------------------------------------------
# Initialize Logger & FastAPI App
# ------------------------------------------------------
logger = get_logger(__name__)

app = FastAPI(
    title="ShipCube AI Email Agent",
    description=(
        "<b>ShipCube AI Email Automation System</b> — integrates Gemini, Hugging Face, "
        "and RAG Knowledge Base for intelligent logistics email processing.<br><br>"
        "🔗 <a href='/dashboard'>Open Dashboard</a><br>"
        "📘 <a href='/docs'>View API Docs</a><br>"
    ),
    version="2.0.0",
)

# ------------------------------------------------------
# Static and Templates Configuration
# ------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Path to CSV records
RECORDS_FILE = BASE_DIR.parent / "records" / "records.csv"

# ------------------------------------------------------
# Request Schema
# ------------------------------------------------------
class EmailRequest(BaseModel):
    sender_email: str
    sender_name: Optional[str] = "Customer"
    subject: str
    body: str
    simulate: Optional[bool] = False


# ------------------------------------------------------
# Root Endpoint — Overview
# ------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def api_overview():
    """Display API overview with useful links."""
    return """
    <html>
    <head><title>ShipCube AI Email API</title></head>
    <body style="font-family:Arial, sans-serif; padding:20px; color:#333;">
        <h2> ShipCube AI Email Automation API</h2>
        <p>Welcome to the ShipCube AI automation system. Access the tools below:</p>
        <ul>
            <li><a href="/dashboard"> Dashboard (Processed Emails)</a></li>
            <li><a href="/docs"> API Docs (Swagger UI)</a></li>
            <li><a href="/redoc"> API Reference (ReDoc)</a></li>
        </ul>
        <hr>
        <h3>Available Endpoints:</h3>
        <ul>
            <li>POST /process_email</li>
            <li>GET /fetch_emails</li>
            <li>GET /query_kb</li>
            <li>GET /batch_run</li>
        </ul>
    </body>
    </html>
    """


# ------------------------------------------------------
# Dashboard View
# ------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Render the ShipCube Dashboard with the latest 50 processed email records.
    """
    records = []
    if RECORDS_FILE.exists():
        try:
            with open(RECORDS_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                records = sorted(reader, key=lambda r: r.get("Timestamp", ""), reverse=True)
        except Exception as e:
            logger.error(f"[Dashboard] Error reading records.csv: {e}")

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "records": records[:50]},
    )


# ------------------------------------------------------
# Endpoint: Process a Single Email
# ------------------------------------------------------
@app.post("/process_email")
async def process_email(request: EmailRequest):
    """
    Executes the full AI pipeline:
    1. Filtering / Sentiment
    2. Summarization
    3. Knowledge Base Retrieval (RAG)
    4. Response Generation
    Logs the result into records.csv.
    """
    try:
        email_data = {
            "from": request.sender_email,
            "sender_name": request.sender_name,
            "subject": request.subject,
            "body": request.body,
        }

        final_state: EmailState = supervisor_langgraph(
            selected_email=email_data,
            your_name="ShipCube",
            recipient_name=request.sender_name,
        )

        # Log record in CSV
        record = {
            "Timestamp": datetime.now().isoformat(),
            "Sender Email": request.sender_email,
            "Sender Name": request.sender_name,
            "Original Subject": request.subject,
            "Original Content": request.body,
            "Classification": final_state.classification,
            "Summary": final_state.summary,
            "Generated Response": final_state.generated_response_body,
            "Requires Human Review": final_state.requires_human_review,
            "Response Status": "Processed via API",
            "Processing Error": final_state.processing_error,
        }
        log_email_record(record, RECORDS_CSV_PATH)

        return {
            "status": "success",
            "classification": final_state.classification,
            "summary": final_state.summary,
            "generated_response": final_state.generated_response_body[:500],
            "requires_review": final_state.requires_human_review,
            "message": "Email processed successfully.",
        }

    except Exception as e:
        logger.error(f"[Process Email] Pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline Error: {str(e)}")


# ------------------------------------------------------
# Endpoint: Fetch Emails
# ------------------------------------------------------
@app.get("/fetch_emails")
async def fetch_emails(simulate: bool = True, limit: int = 3):
    """Fetches emails either via IMAP or local simulation."""
    try:
        emails = fetch_email(simulate=simulate, limit=limit)
        if not emails:
            return {"message": "No new emails found or IMAP unavailable."}
        return {"emails_fetched": len(emails), "sample": emails[:2]}
    except Exception as e:
        logger.error(f"[Fetch Emails] {e}")
        raise HTTPException(status_code=500, detail=f"Email Fetch Error: {e}")


# ------------------------------------------------------
# Endpoint: Knowledge Base Query
# ------------------------------------------------------
@app.get("/query_kb")
async def query_kb(query: str):
    """Query the Knowledge Base for contextual data (RAG component)."""
    try:
        result = query_knowledge_base(query)
        return {"query": query, "kb_context": result}
    except Exception as e:
        logger.error(f"[KB Query] {e}")
        raise HTTPException(status_code=500, detail=f"KB Query Error: {str(e)}")


# ------------------------------------------------------
# Endpoint: Batch Run
# ------------------------------------------------------
@app.get("/batch_run")
async def batch_run(simulate: bool = True, limit: int = 3):
    """Run AI pipeline on multiple emails sequentially with rate-limit delay."""
    try:
        emails = fetch_email(simulate=simulate, limit=limit)
        if not emails:
            return {"message": "No emails found to process."}

        processed = []
        for i, email_data in enumerate(emails, 1):
            final_state: EmailState = supervisor_langgraph(
                selected_email=email_data,
                your_name="ShipCube",
                recipient_name=email_data.get("sender_name", "Customer"),
            )
            processed.append({
                "id": i,
                "subject": email_data.get("subject"),
                "classification": final_state.classification,
                "summary": final_state.summary,
                "generated_response": final_state.generated_response_body[:300],
                "requires_review": final_state.requires_human_review,
            })
            time.sleep(6)  # Protect against Gemini API rate limits

        return {
            "processed_count": len(processed),
            "details": processed,
            "status": "Batch run completed successfully.",
        }

    except Exception as e:
        logger.error(f"[Batch Run] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch Pipeline Error: {str(e)}")


# ------------------------------------------------------
# Endpoint: Serve Records as JSON (for live dashboard updates)
# ------------------------------------------------------
@app.get("/api/records")
async def get_records(limit: int = 50):
    """Returns the latest processed email records for dashboard live updates."""
    try:
        if not RECORDS_FILE.exists():
            return {"records": [], "message": "No records file found."}

        with open(RECORDS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = sorted(reader, key=lambda r: r.get("Timestamp", ""), reverse=True)

        return {
            "records": records[:limit],
            "count": len(records[:limit]),
            "timestamp": datetime.now().isoformat(),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"[API Records] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load records: {str(e)}")
# --------------------------------------------------