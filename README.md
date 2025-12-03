# AI Email Agent (ShipCube)

ShipCube’s AI Email Agent is a complete automation system designed to read, understand, summarize, and respond to emails intelligently. It uses a LangGraph-powered multi-agent workflow, processes emails via IMAP/SMTP, retrieves contextual data using a RAG knowledge base, and generates structured responses using Google Gemini.

The system includes a FastAPI dashboard for real-time monitoring, Prometheus metrics for observability, Dockerized Grafana dashboards, and detailed logging for production use.

---

## Table of Contents

* [Overview](#overview)
* [Features](#features)
* [Tech Stack](#tech-stack)
* [Installation](#installation)

  * [Prerequisites](#prerequisites)
  * [Setup](#setup)
* [Configuration](#configuration)
* [SMTP and IMAP Setup Guide](#smtp-and-imap-setup-guide)
* [Usage](#usage)
* [Monitoring Setup (Prometheus + Grafana)](#monitoring-setup-prometheus--grafana)
* [Execution Flow](#execution-flow)
* [Directory Structure](#directory-structure)
* [Testing](#testing)
* [Contributing](#contributing)
* [Acknowledgments](#acknowledgments)

---

## Overview

The AI Email Agent automates the full lifecycle of email handling. It fetches messages from your inbox, identifies intent, summarizes content, retrieves relevant knowledge entries, generates high-quality replies, and sends them via SMTP or saves them as Gmail drafts for review.

LangGraph enables deterministic multi-agent transitions, while FastAPI provides a dashboard to visualize processing. Prometheus and Grafana offer metrics and long-term monitoring suited for production environments.

---

## Features

### Email Intelligence

* Fetches emails using IMAP
* Extracts sender metadata and intent
* Performs LLM-based classification
* Produces concise summaries
* Generates professional, structured replies

### Multi-Agent Workflow

* LangGraph orchestrated pipeline
* Agents include: Preprocessing, Filtering, Summarization, Retrieval, Response Generation, Human Review
* Supports retries, fallbacks, and custom behaviors

### RAG Knowledge Base

* ChromaDB vector search
* Sentence-Transformer embeddings
* Retrieves FAQs, business policies, and internal docs

### Monitoring & Dashboard

* FastAPI dashboard showing:

  * Processed emails
  * Summaries
  * Predictions
  * Responses
  * Pipeline metadata
* Prometheus metrics for:

  * Total emails processed
  * Latency
  * Agent execution time
  * Failures and retries
* Grafana dashboards (Dockerized) for visualization

### Logging & Storage

* All processed emails stored in `records/records.csv`
* Excel files generated automatically as needed
* Structured logs for audits and debugging

---

## Tech Stack

### LangChain & Workflow

* langchain
* langchain-core
* langchain-community
* langchain-chroma
* langchain-google-genai
* langgraph
* langsmith

### Models & Transformers

* transformers
* sentence-transformers
* torch + accelerate
* tiktoken
* pydantic

### Environment & Utilities

* python-dotenv
* pandas
* openpyxl
* typing-extensions
* email-validator

### Web API & Metrics

* fastapi
* uvicorn
* prometheus-fastapi-instrumentator
* prometheus-client

### Additional Dependencies

* beautifulsoup4
* nltk
* jinja2
* requests

---

## Installation

### Prerequisites

* Python 3.9+
* pip
* Gmail account with App Password
* IMAP enabled

### Setup

Clone the repository:

```bash
git clone https://github.com/pinkaofc/AI-Email-Agent.git
cd AI-Email-Agent
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate environment:

```bash
# macOS / Linux
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
# Gemini API Keys
GEMINI_API_KEY1=your_key
GEMINI_API_KEY2=your_key

# Hugging Face Token
HUGGINGFACEHUB_API_TOKEN=your_hf_token

# SMTP Settings
EMAIL_SERVER=smtp.gmail.com
EMAIL_USERNAME=your_email@gmail.com
EMAIL_APP_PASSWORD=your_app_password
EMAIL_PORT=587

# IMAP Settings
IMAP_SERVER=imap.gmail.com
IMAP_USERNAME=your_email@gmail.com
IMAP_APP_PASSWORD=your_app_password
IMAP_PORT=993

# Developer
YOUR_NAME=Your Name
YOUR_GMAIL_ADDRESS_FOR_DRAFTS=your_email@gmail.com
```

---

## SMTP and IMAP Setup Guide

### 1. Enable 2-Step Verification

Enable at:
[https://myaccount.google.com/security](https://myaccount.google.com/security)

### 2. Generate a Gmail App Password

Go to:
[https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)

Choose:

* App: Mail
* Device: Other

Paste password into `.env`:

```dotenv
EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
IMAP_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### 3. Enable IMAP in Gmail

Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP

### 4. Required Ports

**SMTP**

* Host: smtp.gmail.com
* Port: 587 (TLS)

**IMAP**

* Host: imap.gmail.com
* Port: 993 (SSL)

---

## Usage

Start the Email Agent:

```bash
python main.py
```

Start the FastAPI server:

```bash
uvicorn server.apps:app --reload
```

Useful endpoints:

* `/dashboard`
* `/records`
* `/metrics`
* `/health`
* Test endpoints using GET/POST

---

## Monitoring Setup (Prometheus + Grafana)

The project includes a complete monitoring stack located inside:

```
/monitoring
├── grafana
│   ├── dashboards
│   └── provisioning
│       ├── dashboards
│       └── datasources
├── prometheus.yml
├── docker-compose.yml
└── metrics.py
```

### Start Prometheus + Grafana

```bash
cd monitoring
docker-compose up -d
```

### Access Services

Grafana:
[http://localhost:3000](http://localhost:3000)

Prometheus:
[http://localhost:9090](http://localhost:9090)

Default Grafana login:
`admin / admin`

Dashboards load automatically from:

```
monitoring/grafana/provisioning/
```

### Prometheus Integration

Prometheus scrapes FastAPI metrics from:

```
/metrics
```

Metrics captured include:

* Email processing counts
* Agent execution durations
* Error/success ratio
* Latency
* RAG search performance

---

## Execution Flow

1. **Email Fetching** – Retrieve emails via IMAP or JSON.
2. **Preprocessing** – Extract IDs, names, margin values.
3. **Filtering Agent** – Predict spam, category, intent, sentiment.
4. **Summarization Agent** – Generate a 2–3 sentence summary.
5. **Knowledge Base Retrieval** – Query ChromaDB.
6. **Response Generation Agent** – Create structured final reply.
7. **Formatting Module** – Clean greeting and signature.
8. **Human Review Decision** – Draft to Gmail or send automatically.
9. **Logging** – Store results in CSV, logs, and metrics.

---

## Directory Structure

```plaintext
.
├── agents
├── core
├── knowledge_base
├── vector_store
├── server
├── monitoring
├── docker-compose.yml
├── records
├── utils
├── logs
├── sample_emails.json
├── requirements.txt
├── main.py
└── README.md
```

---

## Testing

```bash
pytest
```

or:

```bash
python -m unittest discover
```

---

## Contributing

* Fork repository
* Create a feature branch
* Commit and push
* Submit a Pull Request

---

## Acknowledgments

* Google Gemini
* LangChain / LangGraph
* Hugging Face
* ChromaDB
* FastAPI
* Prometheus
* Grafana
* Open-source community

---

