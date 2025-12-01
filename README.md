
# AI Email Agent (ShipCube)

An upgraded AI-driven email automation system designed for enterprise-grade processing of inbound emails. The system fetches, filters, transforms, summarizes, augments, and generates intelligent responses using a multi-agent workflow built on LangGraph and Google Gemini. It now includes a robust FastAPI backend, a real-time monitoring dashboard, Prometheus metrics, and full historical logging for long-term analytics.

---

## Overview

ShipCube’s AI Email Agent automates the end-to-end lifecycle of email processing. It integrates rule-based filtering, LLM-driven reasoning, RAG-powered retrieval, and a state-managed workflow graph. The system supports both fully autonomous execution and human-review modes, ensuring reliability and transparency.

Recent upgrades include:

* FastAPI backend with endpoints for predictions, logs, health checks, and real-time data access
* Prometheus metrics capturing pipeline activity, latency, and agent performance
* Grafana dashboard with lifetime counts, throughput, trends, and agent-level instrumentation
* Storage of transformed Excel outputs for invoice-processing workflows
* Margin-based company lookup logic and dynamic parameter extraction
* Improved agentic workflow for multi-step email → data → output transformations

---

## Features

### Email Intelligence

* Automatic ingestion via IMAP with label-based filtering
* Multi-stage reasoning: extraction, categorization, sentiment, summarization, RAG retrieval, and response generation
* AI-structured replies using Gemini with enforceable formatting guidelines
* Optional draft mode or direct SMTP send-out

### Workflow Automation

* LangGraph-based agents with deterministic state transitions
* Agents include: ingestion, preprocessing, filtering, summarization, retrieval, response generation, human review, and error recovery
* Retry + fallback logic, timeout guards, and message-level isolation
* Fully auditable execution path per email

### Retrieval-Augmented Generation (RAG)

* ChromaDB vector store with MiniLM embeddings
* Semantic knowledge retrieval for company data, FAQs, business policies, and profile details
* Supports multi-doc and multi-section retrieval with ranking

### Monitoring and Metrics

* Live FastAPI Dashboard displaying processed emails, summaries, outputs, predictions, and errors
* Prometheus metrics:

  * Total emails processed
  * Agent-level execution durations
  * Success/failure counts
  * RAG hit ratio
  * Response generation latency
* Grafana dashboard with lifetime (no time-window) metrics and panels
* Integrated logging: both CSV and structured logs

### Developer-Friendly

* Clear modular structure
* Extensible agent system
* Centralized configuration
* Separately testable modules
* Works in simulation or production mode
* Supports pluggable LLMs and embedding models

---

## Installation

### Prerequisites

* Python 3.9 or above
* pip
* virtualenv recommended
* Gmail App Password for IMAP/SMTP

### Setup

Clone the repository:

```bash
git clone https://github.com/pinkaofc/AI-Email-Agent.git
cd AI-Email-Agent
```

Create and activate a virtual environment:

```bash
python -m venv venv

# macOS/Linux
source venv/bin/activate  

# Windows
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file:

```dotenv
# Gemini API

HUGGINGFACEHUB_API_TOKEN=your_key
GEMINI_API_KEY1=your_key
GEMINI_API_KEY2=your_key

# SMTP
EMAIL_SERVER=smtp.gmail.com
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_PORT=587

# IMAP
IMAP_SERVER=imap.gmail.com
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=your_app_password
IMAP_PORT=993

# Developer
YOUR_NAME=Your Name
YOUR_GMAIL_ADDRESS_FOR_DRAFTS=your_email@gmail.com
```

---

## Usage

Start the full pipeline:

```bash
python main.py
```

Start the FastAPI server:

```bash
uvicorn server.apps:app --reload
```

Prometheus metrics are exposed at:

```
/metrics
```

Health checks:

```
/health
```

### Execution Flow

The updated workflow operates as follows:

1. Email Fetching
   Emails are fetched via IMAP or loaded from sample JSON for offline testing.

2. Data Extraction & Transformation
   Customer Account IDs, company identifiers, and parameters are extracted for downstream margin-lookup processing.

3. Filtering and Classification
   Categorization, sentiment evaluation, and intent recognition.

4. Summarization
   Gemini generates concise summaries for storage and dashboard display.

5. Knowledge Base Retrieval
   Relevant documents are retrieved using vector search for enriched contextual output.

6. Response Generation
   Context-aware responses are generated using the Response Agent with safety and formatting guards.

7. Output Storage
   Results saved to:

   * `records/records.csv`
   * Excel sheets for invoice-processing logic
   * Dashboard storage for historical display

8. Email Delivery or Draft
   The reply is either drafted or sent automatically.

9. Monitoring
   All stages emit Prometheus metrics and structured logs consumed by Grafana.

---

## Directory Structure

```plaintext
.
├── agents
│   ├── filtering_agent.py
│   ├── summarization_agent.py
│   ├── response_agent.py
│   ├── human_review_agent.py
│   └── ...
│
├── core
│   ├── email_ingestion.py
│   ├── email_sender.py
│   ├── state.py
│   ├── supervisor.py
│   └── ...
│
├── server
│   ├── apps.py
│   ├── static
│   └── templates
│
├── monitoring
│   ├── metrics.py
│   
│
├── knowledge_base
│   ├── ingest.py
│   ├── query.py
│   └── data
│
├── vector_store
│   └── chroma.sqlite3
│
├── notebooks
│   └── model training notebooks
│
├── utils
│   ├── formatter.py
│   ├── logger.py
│   ├── records_manager.py
│   └── rate_limit_guard.py
│
├── records
│   └── records.csv
│
├── flowchart.md
├── sample_emails.json
├── main.py
├── config.py
└── README.md
```

---

## Testing

Run the test suite:

```bash
pytest
```

or:

```bash
python -m unittest discover
```

---

## Contributing

* Fork the repository
* Create a new branch
* Add your feature or fix
* Open a Pull Request with a clear explanation
* Follow PEP8 and include logs for new pipelines

---

## Acknowledgments

ShipCube's AI Email Agent uses contributions from the open-source community and incorporates technologies such as Google Gemini, LangGraph, LangChain, Hugging Face embeddings, ChromaDB, Prometheus, and Grafana.

---

