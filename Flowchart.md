+-------------------------------------------------------------+
|                   AI EMAIL AGENT PIPELINE                   |
|    Initialize environment, logger, config, and Prometheus   |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                    SELECT EMAIL INPUT SOURCE                |
|  - IMAP inbox (unread)                                      |
|  - sample_emails.json (simulation/testing)                  |
|  - Mark-as-seen or retention handled dynamically            |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                 CREATE INITIAL EmailState OBJECT            |
|  - Stores email ID, body, subject, metadata                 |
|  - Tracks all agent outputs, flags, errors                  |
|  - Initializes metrics counters for this message            |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  SUPERVISOR (LANGGRAPH ENGINE)             |
|  Orchestrates the multi-agent reasoning workflow            |
|  Ensures deterministic transitions + state persistence      |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  PREPROCESSING & EXTRACTION                 |
|  - Extract Customer Account ID from email text              |
|  - Lookup corresponding company + margin rules              |
|  - Prepare parameters for downstream invoice logic          |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                 FILTERING AGENT (Gemini LLM)                |
|  - Classifies email into categories                         |
|    spam / informational / positive / negative / neutral     |
|    requires_review / action_required                        |
|  - Sentiment + intent detection                             |
|  - Spam or promo emails are skipped                         |
+-------------------------------------------------------------+
                              |
                              v
               +-----------------------------------+
               |  Is classification == spam/promo? |
               +-----------------------------------+
                       |                 |
                 Yes ->|     SKIP EMAIL  |<- No
                       |  Update metrics |
                       v
+-------------------------------------------------------------+
|          SUMMARIZATION AGENT (Gemini LLM)                   |
|  - Generates 2–3 sentence high-quality summary              |
|  - Extracts key request, issue, or intent                   |
|  - Output stored in EmailState for dashboard                |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|            KNOWLEDGE BASE RETRIEVAL (RAG ENGINE)            |
|  - ChromaDB vector search using MiniLM embeddings           |
|  - Retrieves company FAQs, policies, workflow docs          |
|  - RAG hit ratio logged for monitoring                      |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|             RESPONSE GENERATION AGENT (Gemini LLM)          |
|  - Generates final response using:                          |
|    summary + classification + retrieved context + margin    |
|  - Produces structured, clean, professional replies         |
|  - Generates invoice-level outputs if required              |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                      FORMATTING MODULE                      |
|  - Removes duplicate greetings                              |
|  - Extracts sender name                                     |
|  - Builds final template:                                   |
|       Hi <Name>,                                            |
|       <Generated Body>                                      |
|       Regards,                                              |
|       <Your Name>                                           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|              HUMAN REVIEW DECISION (State Flag)             |
|  - If EmailState.requires_human_review == True              |
|       → Save draft to Gmail                                 |
|  - Else                                                     |
|       → Auto-send email via SMTP                            |
+-------------------------------------------------------------+
          /                                         \
         /                                           \
        v                                             v
+----------------------------------+     +----------------------------------+
|        send_draft_to_gmail()     |     |           send_email()           |
|  - Draft created in Gmail        |     |  - SMTP delivery to sender       |
|  - Visible in FastAPI dashboard  |     |  - Delivery metrics recorded     |
+----------------------------------+     +----------------------------------+
         \                                             /
          \                                           /
           +-----------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  STORE ALL RESULTS & FILES                  |
|  - Save entry to records/records.csv                        |
|  - Save transformed Excel invoice file to /drive storage    |
|  - Expose records via FastAPI for dashboard                 |
|  - Emit Prometheus metrics (duration, status, type, etc.)   |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                 FASTAPI + GRAFANA MONITORING                |
|  - /dashboard shows processed emails, outputs, insights     |
|  - /metrics exposes Prometheus counters                     |
|  - Grafana panels show lifetime totals, performance trends  |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|          RATE LIMIT GUARD AND CONTINUE TO NEXT EMAIL        |
|  - Sleep if necessary to avoid spam-detection throttling    |
|  - Move to next message in queue                            |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  END OF PIPELINE EXECUTION                  |
|  - All emails processed                                      |
|  - Final summary logged + metrics pushed                     |
+-------------------------------------------------------------+
