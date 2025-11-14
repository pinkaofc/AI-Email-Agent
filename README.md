---

# **AI Email Agent (ShipCube)**

An advanced AI-powered email automation system that fetches, filters, summarizes, and generates intelligent replies using state-driven workflows and large language models. The system integrates IMAP/SMTP email handling with **LangGraph**, **Google Gemini**, and a **Retrieval-Augmented Generation (RAG)** knowledge base. It supports end-to-end automation—from inbox ingestion to final email dispatch—while maintaining human-review control when needed.

---

## **Table of Contents**

- [**Table of Contents**](#table-of-contents)
- [**Overview**](#overview)
- [**Features**](#features)
  - [**Email Intelligence**](#email-intelligence)
  - [**Workflow Automation**](#workflow-automation)
  - [**RAG Knowledge Base**](#rag-knowledge-base)
  - [**Dashboard \& Logging**](#dashboard--logging)
  - [**Developer-Friendly**](#developer-friendly)
- [**Installation**](#installation)
  - [**Prerequisites**](#prerequisites)
  - [**Setup**](#setup)
- [**Configuration**](#configuration)
- [**Usage**](#usage)
  - [**Execution Flow**](#execution-flow)
- [**Directory Structure**](#directory-structure)
- [**Testing**](#testing)
- [**Contributing**](#contributing)
- [**Acknowledgments**](#acknowledgments)

---

## **Overview**

ShipCube is an **AI-driven email assistant** designed to automate the complete lifecycle of email handling. It reads, interprets, and replies to emails intelligently while maintaining contextual consistency using a hybrid architecture of rule-based steps and LLM-driven reasoning.

Core technologies include:

* **Google Gemini API** for email understanding, summarization, and high-quality response generation
* **LangGraph** for orchestrating a multi-agent, state-driven processing pipeline
* **Hugging Face Embeddings + ChromaDB** for knowledge-base retrieval
* **FastAPI Backend + Dashboard** (added in Week 6) for monitoring pipeline activity
* **Custom ML Models** (e.g., Categorization Model trained in module A notebook)

The system supports both **live production mode** (IMAP/SMTP) and **offline simulation mode** (JSON files), letting you test workflows safely before deployment.

---

## **Features**

### **Email Intelligence**

* Automatic email ingestion through IMAP
* Multi-stage pipeline: filtering → sentiment → summarization → context retrieval → response generation
* Professional, structured AI-generated replies
* Option to send emails directly or save them as drafts in Gmail

### **Workflow Automation**

* LangGraph-based state machine for repeatable and traceable processing
* Multi-agent design (filtering, summarization, response, human review)
* Error handling, fallback logic, and retry mechanisms

### **RAG Knowledge Base**

* ChromaDB-powered vector store
* Semantic search for company FAQs, service info, client profiles, guidelines
* Hugging Face MiniLM embeddings for high-quality retrieval

### **Dashboard & Logging**

* FastAPI Dashboard to preview:

  * Processed emails
  * Predictions
  * Summaries
  * Generated replies
  * Confidence scores
* CSV logs for all actions and responses

### **Developer-Friendly**

* Modular architecture
* Clean project structure
* Fully documented pipeline
* Easy to extend with new models, knowledge base documents, or agents

---

## **Installation**

### **Prerequisites**

* Python **3.9+**
* pip package manager
* (Optional) `virtualenv` for isolation

### **Setup**

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

## **Configuration**

Create a `.env` file in the project root:

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

Gmail users should configure an **App Password**.

---

## **Usage**

Run the complete agent pipeline:

```bash
python main.py
```

### **Execution Flow**

1. **Email Fetching**

   * Fetches live emails from IMAP or loads simulated emails from JSON.

2. **Processing Pipeline**

   * Filtering Agent → sentiment + category
   * Summarization Agent → short concise summary
   * Knowledge Base Retrieval
   * Response Agent → polite, context-aware AI reply

3. **Formatting**

   * Clean greeting, body structure, and signature via `formatter.py`.

4. **Sending or Drafting**

   * Human-review mode: sends to your Gmail drafts
   * Production mode: sends through SMTP to the original sender

5. **Logging & Dashboard**

   * All results stored in `/records/records.csv`
   * FastAPI dashboard displays real-time predictions and outputs

---

## **Directory Structure**

```plaintext
.
├── agents
│   ├── filtering_agent.py
│   ├── summarization_agent.py
│   ├── response_agent.py
│   ├── human_review_agent.py
│   └── __init__.py
│
├── config.py
│
├── core
│   ├── email_ingestion.py
│   ├── email_sender.py
│   ├── state.py
│   ├── supervisor.py
│   └── __init__.py
│
├── knowledge_base
│   ├── ingest.py
│   ├── query.py
│   └── data/
│
├── vector_store/
│   └── chroma.sqlite3, index files...
│
├── fastapi_app/ (New in Week 6)
│   ├── apps.py     # Dashboard launcher
│   ├── routes/
│   ├── static/
│   └── templates/
│
├── notebooks/
│   ├── module_a_categorization.ipynb
│   ├── module_b_sentiment.ipynb
│   ├── module_c_summarization.ipynb
│   ├── module_d_response_generation.ipynb
│   └── pipeline_integration.ipynb
│
├── records/records.csv
│
├── utils
│   ├── formatter.py
│   ├── logger.py
│   ├── records_manager.py
│   └── rate_limit_guard.py
│
├── sample_emails.json
├── requirements.txt
├── flowchart.md
├── main.py
└── README.md
```

---

## **Testing**

Run tests:

```bash
pytest
```

or:

```bash
python -m unittest discover
```

Ensure `.env` is configured before testing modules involving email or Gemini API.

---

## **Contributing**

1. Fork the repository
2. Create a new feature branch:

   ```bash
   git checkout -b feature/your-feature
   ```
3. Commit and push changes
4. Open a Pull Request with a clear explanation

Follow PEP8 and include proper logging.

---

## **Acknowledgments**

* **Google Gemini API** – for intelligent classification, summarization, and response generation
* **LangGraph & LangChain** – for the orchestration engine
* **Hugging Face** – for embeddings powering the KB
* **ChromaDB** – for efficient vector storage
* **Open Source Community** – for tools that enable this system

---


