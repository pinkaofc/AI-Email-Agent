"""
Configuration module for the AI Email Agent.
Loads all environment variables and provides sane defaults.
"""

import os
from dotenv import load_dotenv
from utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# Gemini + Hugging Face API Configuration
# --------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

if not GEMINI_API_KEY:
    logger.error("[CONFIG] GEMINI_API_KEY is missing! Please add it to your .env file.")
else:
    logger.info("[CONFIG] Gemini API key loaded successfully.")

if not HUGGINGFACEHUB_API_TOKEN:
    logger.warning("[CONFIG] HUGGINGFACEHUB_API_TOKEN not found. Knowledge base embedding may fail.")

# Optional embedding model
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "models/embedding-001")

# --------------------------------------------------
# SMTP Email Configuration (for sending)
# --------------------------------------------------
EMAIL_SERVER = os.getenv("EMAIL_SERVER", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))  # TLS default port
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD") or os.getenv("EMAIL_APP_PASSWORD")

if not EMAIL_USERNAME or not EMAIL_PASSWORD:
    logger.error("[CONFIG] Missing email credentials. Outgoing emails will fail.")
else:
    logger.info(f"[CONFIG] Outgoing email configured for: {EMAIL_USERNAME}")

# --------------------------------------------------
# IMAP Configuration (for fetching)
# --------------------------------------------------
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
IMAP_USERNAME = os.getenv("IMAP_USERNAME", EMAIL_USERNAME)
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", EMAIL_PASSWORD)

logger.info(f"[CONFIG] IMAP server: {IMAP_SERVER}:{IMAP_PORT}")

# --------------------------------------------------
# Agent / User Profile
# --------------------------------------------------
YOUR_NAME = os.getenv("YOUR_NAME", "AI Email Agent")
YOUR_GMAIL_ADDRESS_FOR_DRAFTS = os.getenv("YOUR_GMAIL_ADDRESS_FOR_DRAFTS", EMAIL_USERNAME)

if not YOUR_GMAIL_ADDRESS_FOR_DRAFTS:
    logger.warning("[CONFIG] Draft destination email not set. Using EMAIL_USERNAME as fallback.")

# --------------------------------------------------
# Knowledge Base Paths
# --------------------------------------------------
KNOWLEDGE_BASE_PATH = os.getenv("KNOWLEDGE_BASE_PATH", "knowledge_base/data")
VECTOR_STORE_PATH = os.getenv("VECTOR_STORE_PATH", "knowledge_base/vector_store")

logger.info(f"[CONFIG] Knowledge base path: {KNOWLEDGE_BASE_PATH}")

# --------------------------------------------------
# CSV Records Path (Email Logging)
# --------------------------------------------------
RECORDS_CSV_PATH = os.getenv("RECORDS_CSV_PATH", "records/records.csv")
CSV_HEADERS = [
    "SR No", "Timestamp", "Sender Email", "Sender Name", "Recipient Email",
    "Original Subject", "Original Content", "Classification", "Summary",
    "Generated Response", "Requires Human Review", "Response Status",
    "Processing Error", "Record Save Time",
]

# --------------------------------------------------
# Sanity Diagnostics
# --------------------------------------------------
logger.info(f"[CONFIG] Email server: {EMAIL_SERVER}:{EMAIL_PORT}")
logger.info(f"[CONFIG] IMAP username: {IMAP_USERNAME}")
logger.info(f"[CONFIG] Draft destination: {YOUR_GMAIL_ADDRESS_FOR_DRAFTS}")
logger.info(f"[CONFIG] Records CSV path: {RECORDS_CSV_PATH}")