"""
Configuration module for the AI Email Agent.
Loads environment variables, supports multi-key Gemini rotation,
and provides defaults for email, IMAP, and knowledge base setup.
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
# Gemini API Configuration (with key rotation)
# --------------------------------------------------
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY1"),
    os.getenv("GEMINI_API_KEY2"),
]

# Filter out any empty or None keys
GEMINI_KEYS = [key for key in GEMINI_KEYS if key]

if not GEMINI_KEYS:
    logger.error("[CONFIG]  No Gemini API keys found! Add GEMINI_API_KEY1 and GEMINI_API_KEY2 in your .env file.")
else:
    logger.info(f"[CONFIG]  Loaded {len(GEMINI_KEYS)} Gemini API key(s).")

def get_gemini_api_key() -> str:
    """Randomly rotates between available Gemini API keys."""
    return random.choice(GEMINI_KEYS)

# For backward compatibility — some scripts may import GEMINI_API_KEY directly
GEMINI_API_KEY = get_gemini_api_key()

# Optional embedding model
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "models/embedding-001")

# --------------------------------------------------
# Hugging Face API Configuration
# --------------------------------------------------
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

if not HUGGINGFACEHUB_API_TOKEN:
    logger.warning("[CONFIG]  HUGGINGFACEHUB_API_TOKEN not found. Knowledge base embeddings may fail.")
else:
    logger.info("[CONFIG]  Hugging Face API token loaded successfully.")

# --------------------------------------------------
# SMTP Email Configuration (for sending)
# --------------------------------------------------
EMAIL_SERVER = os.getenv("EMAIL_SERVER", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))  # TLS default
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")

if not EMAIL_USERNAME or not EMAIL_APP_PASSWORD:
    logger.error("[CONFIG]  Missing email credentials — outgoing emails will fail.")
else:
    logger.info(f"[CONFIG] Outgoing email configured for: {EMAIL_USERNAME}")

# --------------------------------------------------
# IMAP Configuration (for fetching)
# --------------------------------------------------
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
IMAP_USERNAME = os.getenv("IMAP_USERNAME", EMAIL_USERNAME)
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", EMAIL_APP_PASSWORD)

logger.info(f"[CONFIG] IMAP server: {IMAP_SERVER}:{IMAP_PORT}")

# --------------------------------------------------
# Agent / User Profile
# --------------------------------------------------
YOUR_NAME = os.getenv("YOUR_NAME", "AI Email Agent")
YOUR_GMAIL_ADDRESS_FOR_DRAFTS = os.getenv("YOUR_GMAIL_ADDRESS_FOR_DRAFTS", EMAIL_USERNAME)

if not YOUR_GMAIL_ADDRESS_FOR_DRAFTS:
    logger.warning("[CONFIG]  Draft destination not set. Using EMAIL_USERNAME as fallback.")
else:
    logger.info(f"[CONFIG] Draft destination: {YOUR_GMAIL_ADDRESS_FOR_DRAFTS}")

# --------------------------------------------------
# Knowledge Base Configuration
# --------------------------------------------------
KNOWLEDGE_BASE_PATH = os.getenv("KNOWLEDGE_BASE_PATH", "knowledge_base/data")
VECTOR_STORE_PATH = os.getenv("VECTOR_STORE_PATH", "knowledge_base/vector_store")

logger.info(f"[CONFIG] Knowledge base path: {KNOWLEDGE_BASE_PATH}")
logger.info(f"[CONFIG] Vector store path: {VECTOR_STORE_PATH}")

# --------------------------------------------------
# CSV Records Configuration (Email Logs)
# --------------------------------------------------
RECORDS_CSV_PATH = os.getenv("RECORDS_CSV_PATH", "records/records.csv")
CSV_HEADERS = [
    "SR No", "Timestamp", "Sender Email", "Sender Name", "Recipient Email",
    "Original Subject", "Original Content", "Classification", "Summary",
    "Generated Response", "Requires Human Review", "Response Status",
    "Processing Error", "Record Save Time",
]

# --------------------------------------------------
# Sanity Diagnostics Summary
# --------------------------------------------------
logger.info(f"[CONFIG] Email server: {EMAIL_SERVER}:{EMAIL_PORT}")
logger.info(f"[CONFIG] IMAP username: {IMAP_USERNAME}")
logger.info(f"[CONFIG] Records CSV path: {RECORDS_CSV_PATH}")
logger.info("[CONFIG] Configuration successfully loaded.")
