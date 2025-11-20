"""
Configuration module for the AI Email Agent.
Loads environment variables, supports multi-key Gemini rotation,
validates critical credentials, and exposes shared constants.
"""

import os
import random
from dotenv import load_dotenv
from utils.logger import get_logger

# --------------------------------------------------
# Initialize logger
# --------------------------------------------------
logger = get_logger(__name__)

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# Gemini API Key Handling (Safe Rotation)
# --------------------------------------------------
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY1"),
    os.getenv("GEMINI_API_KEY2"),
    os.getenv("GEMINI_API_KEY3"),
]

# Remove None or empty strings
GEMINI_KEYS = [k for k in GEMINI_KEYS if k and k.strip()]

if not GEMINI_KEYS:
    logger.error(
        "[CONFIG] No valid Gemini API keys found. "
        "Set GEMINI_API_KEY, GEMINI_API_KEY1, etc., in .env."
    )
else:
    logger.info(f"[CONFIG] Loaded {len(GEMINI_KEYS)} Gemini key(s).")

def get_gemini_api_key() -> str:
    """
    Returns one of the Gemini keys in rotation.

    Deterministic and safe: if only one key exists, it returns that key.
    """
    if not GEMINI_KEYS:
        raise RuntimeError(
            "No Gemini API keys available. Configure GEMINI_API_KEY in .env."
        )
    if len(GEMINI_KEYS) == 1:
        return GEMINI_KEYS[0]

    return random.choice(GEMINI_KEYS)


# Backward compatibility
GEMINI_API_KEY = get_gemini_api_key()

# Optional embedding model
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "models/embedding-001")

# --------------------------------------------------
# HuggingFace Token
# --------------------------------------------------
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

if not HUGGINGFACEHUB_API_TOKEN:
    logger.warning(
        "[CONFIG] HUGGINGFACEHUB_API_TOKEN missing — "
        "Knowledge base embeddings may fail."
    )
else:
    logger.info("[CONFIG] Hugging Face token loaded.")

# --------------------------------------------------
# Outgoing Email (SMTP)
# --------------------------------------------------
EMAIL_SERVER = os.getenv("EMAIL_SERVER", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")

if EMAIL_USERNAME and EMAIL_APP_PASSWORD:
    logger.info(f"[CONFIG] SMTP ready for: {EMAIL_USERNAME}")
else:
    logger.error(
        "[CONFIG] Missing EMAIL_USERNAME or EMAIL_APP_PASSWORD. "
        "Outgoing emails will fail."
    )

# --------------------------------------------------
# IMAP (Incoming Email)
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
    "YOUR_GMAIL_ADDRESS_FOR_DRAFTS",
    EMAIL_USERNAME
)

if not YOUR_GMAIL_ADDRESS_FOR_DRAFTS:
    logger.warning(
        "[CONFIG] Draft inbox not set — falling back to EMAIL_USERNAME."
    )

logger.info(
    f"[CONFIG] Draft emails will be sent to: {YOUR_GMAIL_ADDRESS_FOR_DRAFTS}"
)

# --------------------------------------------------
# Knowledge Base Paths
# --------------------------------------------------
KNOWLEDGE_BASE_PATH = os.getenv("KNOWLEDGE_BASE_PATH", "knowledge_base/data")
VECTOR_STORE_PATH = os.getenv("VECTOR_STORE_PATH", "knowledge_base/vector_store")

logger.info(f"[CONFIG] KB data path: {KNOWLEDGE_BASE_PATH}")
logger.info(f"[CONFIG] Vector store path: {VECTOR_STORE_PATH}")

# --------------------------------------------------
# Records CSV Configuration
# --------------------------------------------------
RECORDS_CSV_PATH = os.getenv("RECORDS_CSV_PATH", "records/records.csv")
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

# --------------------------------------------------
# Final Summary
# --------------------------------------------------
logger.info("[CONFIG] All configuration variables loaded successfully.")
logger.info(f"[CONFIG] Email server: {EMAIL_SERVER}:{EMAIL_PORT}")
logger.info(f"[CONFIG] IMAP username: {IMAP_USERNAME}")
logger.info(f"[CONFIG] Records CSV path: {RECORDS_CSV_PATH}")
