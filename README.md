---

# AI Email Agent 

An AI-powered email automation system that fetches, filters, summarizes, and generates intelligent replies to emails using advanced language models. The system integrates with IMAP and SMTP servers and uses a state-driven LangGraph workflow to manage the complete lifecycle of email processing — from ingestion to automated response generation.

---

## Table of Contents

- [Table of Contents](#table-of-contents)
- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Execution Flow](#execution-flow)
- [Directory Structure](#directory-structure)
- [Testing](#testing)
- [Contributing](#contributing)
- [Acknowledgments](#acknowledgments)

---

## Overview

This repository implements an **AI-driven email assistant** capable of automatically reading, understanding, and responding to emails with minimal human supervision. It utilizes **Google’s Gemini API** for reasoning and text generation, **LangGraph** for orchestrating multi-agent workflows, and **Hugging Face embeddings** for retrieving relevant context from a local knowledge base (RAG).

The pipeline supports both **real-world emails** via IMAP and **simulated emails** via JSON files, making it suitable for production and testing environments.

The workflow performs the following tasks:

* **Email Ingestion** – Fetches live emails or reads simulated ones.
* **Filtering** – Classifies emails as spam, urgent, or informational.
* **Summarization** – Generates concise summaries of long messages.
* **Response Generation** – Drafts polite, context-aware replies.
* **Sending or Drafting** – Sends emails directly or as drafts for review.
* **Logging** – Tracks all actions, statuses, and AI responses in CSV logs.

---

## Features

* **IMAP & SMTP Integration:** Works with Gmail and other email servers for real-time inbox management.
* **Filtering Agent:** Classifies emails into meaningful categories using Gemini models.
* **Summarization Agent:** Produces clear, 2–3 sentence summaries of email content.
* **Response Agent:** Generates professional, human-like replies using contextual reasoning.
* **Knowledge Base Support:** Retrieves relevant company data or FAQs from local ChromaDB storage.
* **Human Review Mode:** Option to send drafts for manual review before final dispatch.
* **State Graph Workflow:** Manages transitions between agents using LangGraph.
* **Advanced Logging:** Detailed logs and CSV record tracking for every processed email.

---

## Installation

### Prerequisites

* Python 3.9 or higher
* [pip](https://pip.pypa.io/) package manager
* (Optional) [virtualenv](https://virtualenv.pypa.io/) for environment isolation

### Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/pinkaofc/AI-Email-Agent.git
   cd AI-Email-Agent
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python -m venv venv
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

The system requires credentials and API keys defined in a `.env` file at the project root.

Example `.env` file:

```dotenv
# Gemini API
GEMINI_API_KEY=your_gemini_api_key

# SMTP Settings
EMAIL_SERVER=smtp.gmail.com
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_PORT=587

# IMAP Settings
IMAP_SERVER=imap.gmail.com
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=your_app_password
IMAP_PORT=993

# Developer Settings
YOUR_NAME=Priyanka Kumari
YOUR_GMAIL_ADDRESS_FOR_DRAFTS=your_email@gmail.com
```

You can use [App Passwords](https://support.google.com/accounts/answer/185833) for Gmail authentication.

---

## Usage

To start the assistant:

```bash
python main.py
```

### Execution Flow

1. **Email Fetching**

   * Choose whether to use live IMAP emails or simulated emails from `sample_emails.json`.
   * The system loads up to the configured number of messages.

2. **Pipeline Execution**
   Each email passes through the full pipeline:

   * **Filtering Agent** – Determines sentiment and category.
   * **Summarization Agent** – Creates a brief summary of the message.
   * **Knowledge Base Query** – Retrieves related information via embeddings.
   * **Response Agent** – Generates a clear, structured, and human-like reply.

3. **Formatting**

   * The reply is passed through `formatter.py` for proper greeting, body cleaning, and signature formatting.

4. **Send or Draft**

   * In review/dry-run mode → `send_draft_to_gmail()` sends a draft to your Gmail for review.
   * In production mode → `send_email()` dispatches directly to the sender.

5. **Logging**

   * Each action is logged in `records/records.csv` with timestamps, classification, and status.

---

## Directory Structure

```plaintext
.
├── agents
│   ├── filtering_agent.py          # Classifies emails (spam, urgent, etc.)
│   ├── summarization_agent.py      # Generates summaries
│   ├── response_agent.py           # Creates AI-based responses
│   ├── human_review_agent.py       # Handles manual review steps
│   └── __init__.py
│
├── config.py                       # Loads .env, sets API & email configuration
│
├── core
│   ├── email_ingestion.py          # Handles IMAP fetch & JSON simulation
│   ├── email_sender.py             # Sends emails via SMTP or drafts via Gmail
│   ├── state.py                    # Defines EmailState dataclass
│   ├── supervisor.py               # Manages LangGraph pipeline
│   └── __init__.py
│
├── knowledge_base
│   ├── ingest.py                   # Embeds and stores KB documents in ChromaDB
│   ├── query.py                    # Retrieves context for RAG
│   └── data/                       # Source documents for knowledge base
│
├── records
│   └── records.csv                 # Logs all processed email metadata
│
├── utils
│   ├── formatter.py                # Formats email text and structure
│   ├── logger.py                   # Logger setup for system-wide tracking
│   ├── records_manager.py          # CSV logging for email metadata
│   └── __init__.py
│
├── sample_emails.json              # Sample emails for simulation/testing
├── requirements.txt                # Python dependencies
├── flowchart.md                    # Visual pipeline documentation
├── main.py                         # Main orchestration entry point
└── README.md                       # Project documentation
```

---

## Testing

Run all tests using `pytest` or Python’s built-in `unittest`:

```bash
pytest
```

or

```bash
python -m unittest discover
```

Ensure that your `.env` variables are configured before running tests.

---

## Contributing

Contributions are welcome.

1. Fork the repository on GitHub.
2. Create a feature branch:

   ```bash
   git checkout -b feature/new-feature
   ```
3. Commit your changes and push to your branch.
4. Open a Pull Request with a detailed description of your modifications.

All code contributions should follow Pythonic conventions (PEP8) and include appropriate logging.

---

## Acknowledgments

* **Google Gemini API** – For powering classification, summarization, and response generation.
* **LangGraph & LangChain** – For providing the workflow orchestration and agent framework.
* **Hugging Face** – For embeddings and knowledge base integration.
* **ChromaDB** – For efficient vector storage and retrieval.
* **Open Source Community** – For maintaining the essential libraries that make this system possible.

---

