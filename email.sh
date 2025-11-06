#!/usr/bin/env bash
# ==========================================================
# Email AI Assistant Project Setup Script
# Creates the folder structure and base files for the project
# ==========================================================

set -e  # Exit immediately if any command fails

# --- Project name ---
base_dir="email_assistant"

echo "Setting up project structure for '$base_dir'..."

# --- Directory structure ---
mkdir -p "$base_dir"/{agents,core,utils,knowledge_base/{data,vector_store},records}

# --- Agent modules ---
for file in filtering_agent summarization_agent response_agent human_review_agent; do
  touch "$base_dir/agents/${file}.py"
done
touch "$base_dir/agents/__init__.py"

# --- Core modules ---
for file in email_ingestion email_sender state supervisor email_imap; do
  touch "$base_dir/core/${file}.py"
done
touch "$base_dir/core/__init__.py"

# --- Utility modules ---
for file in logger formatter records_manager; do
  touch "$base_dir/utils/${file}.py"
done
touch "$base_dir/utils/__init__.py"

# --- Root-level project files ---
touch "$base_dir/sample_emails.json"
touch "$base_dir/config.py"
touch "$base_dir/main.py"
touch "$base_dir/requirements.txt"
touch "$base_dir/README.md"
touch "$base_dir/.env"

# --- Pre-fill files with basic boilerplate ---
cat > "$base_dir/requirements.txt" <<EOF
# Core dependencies for Email AI Agent
langchain==1.0.3
langchain-core==1.0.2
langchain-google-genai==3.0.0
langgraph==1.0.2
langsmith==0.4.38
python-dotenv
requests
pydantic>=2.0
tiktoken
transformers
sentence-transformers
nltk
jinja2
beautifulsoup4
chromadb==1.3.3
EOF

cat > "$base_dir/.env" <<EOF
# Environment variables for Email AI Agent

# --- Gemini API ---
GEMINI_API_KEY=your_gemini_api_key_here

# --- Email Credentials (SMTP/IMAP) ---
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
EMAIL_APP_PASSWORD=your_gmail_app_password

# --- Agent Info ---
YOUR_NAME=AI Email Assistant
YOUR_GMAIL_ADDRESS_FOR_DRAFTS=your_email@gmail.com

# --- Servers ---
EMAIL_SERVER=smtp.gmail.com
EMAIL_PORT=587
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
EOF

cat > "$base_dir/README.md" <<EOF
# Email AI Assistant

An autonomous email management system powered by Gemini API, LangChain, and Chroma (RAG).

## Features
- Intelligent email classification and summarization
- Context-aware response generation using Gemini
- Knowledge base integration with ChromaDB and Hugging Face embeddings
- Human review mode for sensitive messages
- Automated draft and send workflows

## Setup
1. Create and activate a virtual environment:
   python -m venv .venv
   source .venv/bin/activate  # or .venv\\Scripts\\activate on Windows

2. Install dependencies:
   pip install -r requirements.txt

3. Add your credentials in .env

4. Run the pipeline:
   python main.py

## Project Structure
- agents/ → LLM task modules (filtering, summarization, response)
- core/ → workflow logic (LangGraph, IMAP/SMTP integration)
- knowledge_base/ → RAG data and embeddings
- utils/ → logging, formatting, and helper utilities
EOF

echo "Project structure for '$base_dir' created successfully."
echo "Next steps:"
echo "1. cd $base_dir"
echo "2. Fill in your .env file with Gemini and Gmail credentials."
echo "3. Create and activate a Python virtual environment."
echo "4. Install dependencies using 'pip install -r requirements.txt'."
echo "5. Run 'python main.py' to start the email agent."
