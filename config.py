"""
Configuration module for the AI Email Agent.
Loads environment variables, supports multi-key Gemini rotation,
validates credentials, and exposes shared constants.
"""

import os
import random
from pathlib import Path
from dotenv import load_dotenv
from utils.logger import get_logger

# Optional Prometheus metric
try:
    from monitoring.metrics import GEMINI_KEY_HEALTH
    PROM_METRICS_ENABLED = True
except Exception:
    PROM_METRICS_ENABLED = False

# --------------------------------------------------
# Logger
# --------------------------------------------------
logger = get_logger(__name__)

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# Gemini API Keys
# --------------------------------------------------
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY1"),
    os.getenv("GEMINI_API_KEY2"),
    os.getenv("GEMINI_API_KEY3"),
]

# Filter out empty keys
GEMINI_KEYS = [k.strip() for k in GEMINI_KEYS if k and k.strip()]

if GEMINI_KEYS:
    logger.info(f"[CONFIG] Loaded {len(GEMINI_KEYS)} Gemini API key(s).")
else:
    logger.error("[CONFIG] No Gemini API keys found. Set GEMINI_API_KEY in .env")

def get_gemini_api_key() -> str:
    """Return Gemini key with safe rotation."""
    if not GEMINI_KEYS:
        raise RuntimeError("No Gemini API keys configured.")

    if len(GEMINI_KEYS) == 1:
        if PROM_METRICS_ENABLED:
            GEMINI_KEY_HEALTH.labels(api_key_id="1").set(1)
        return GEMINI_KEYS[0]

    idx = random.randint(0, len(GEMINI_KEYS) - 1)
    if PROM_METRICS_ENABLED:
        GEMINI_KEY_HEALTH.labels(api_key_id=str(idx + 1)).set(1)
    return GEMINI_KEYS[idx]

GEMINI_API_KEY = get_gemini_api_key()

# Optional embedding model
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "models/embedding-001")

# --------------------------------------------------
# HuggingFace Token
# --------------------------------------------------
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
if HUGGINGFACEHUB_API_TOKEN:
    logger.info("[CONFIG] Hugging Face token loaded.")
else:
    logger.warning("[CONFIG] Missing Hugging Face token — KB embedding may fail.")

# --------------------------------------------------
# SMTP
# --------------------------------------------------
EMAIL_SERVER = os.getenv("EMAIL_SERVER", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")

if EMAIL_USERNAME and EMAIL_APP_PASSWORD:
    logger.info(f"[CONFIG] SMTP configured for: {EMAIL_USERNAME}")
else:
    logger.error("[CONFIG] SMTP credentials missing — outgoing email will fail.")

# --------------------------------------------------
# IMAP
# --------------------------------------------------
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
IMAP_USERNAME = os.getenv("IMAP_USERNAME", EMAIL_USERNAME)
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", EMAIL_APP_PASSWORD)

logger.info(f"[CONFIG] IMAP server: {IMAP_SERVER}:{IMAP_PORT}")

# --------------------------------------------------
# Agent Identity
# --------------------------------------------------
YOUR_NAME = os.getenv("YOUR_NAME", "AI Email Agent")
YOUR_GMAIL_ADDRESS_FOR_DRAFTS = os.getenv(
    "YOUR_GMAIL_ADDRESS_FOR_DRAFTS", EMAIL_USERNAME
)

logger.info(f"[CONFIG] Drafts go to: {YOUR_GMAIL_ADDRESS_FOR_DRAFTS}")

# --------------------------------------------------
# Correct Project ROOT (VERY IMPORTANT FIX)
# --------------------------------------------------
# This ROOT always anchors to:
# C:\Supply-Chain-Client-Management\Email-AI-Agent
ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------
# Knowledge Base (Correct Absolute Paths)
# --------------------------------------------------
ROOT = Path(__file__).resolve().parent

KNOWLEDGE_BASE_PATH = ROOT / "knowledge_base" / "data"
VECTOR_STORE_PATH = ROOT / "knowledge_base" / "vector_store"


logger.info(f"[CONFIG] KB Data Path: {KNOWLEDGE_BASE_PATH}")
logger.info(f"[CONFIG] Vector Store Path: {VECTOR_STORE_PATH}")

# --------------------------------------------------
# Records CSV
# --------------------------------------------------
RECORDS_CSV_PATH = Path(
    os.getenv("RECORDS_CSV_PATH", ROOT / "records" / "records.csv")
).resolve()

CSV_HEADERS = [
    "SR No",
    "Timestamp",
    "Sender Email",
    "Sender Name",
    "Recipient Email",
    "Original Subject",
    "Original Content",
    "Classification",
    "Summary",
    "Generated Response",
    "Requires Human Review",
    "Response Status",
    "Processing Error",
    "Record Save Time",
]

logger.info(f"[CONFIG] Records CSV Path: {RECORDS_CSV_PATH}")

# --------------------------------------------------
# Summary
# --------------------------------------------------
logger.info("[CONFIG] Configuration loaded successfully.")
logger.info(f"[CONFIG] Email Server: {EMAIL_SERVER}:{EMAIL_PORT}")
logger.info(f"[CONFIG] IMAP Username: {IMAP_USERNAME}")
