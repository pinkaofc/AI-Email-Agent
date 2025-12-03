+-------------------------------------------------------------+
|                    EMAIL BOT PIPELINE                       |
|       Initialize environment, logger, config, metrics       |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                    FETCH EMAIL (Input Source)               |
|  - IMAP: Fetch unread emails from inbox                     |
|  - JSON: Load emails from sample_emails.json (test mode)    |
|  - mark_as_seen and fetch_limit handled dynamically         |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|              CREATE INITIAL EmailState OBJECT               |
|  - Stores subject, body, sender, metadata                   |
|  - Holds pipeline flags (review, spam, error state)         |
|  - Initializes Prometheus counters for this email           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                    SUPERVISOR PIPELINE                     |
|     (LangGraph orchestrates multi-agent state transitions)  |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                 PREPROCESSING / EXTRACTION                  |
|  - Extract account ID, company name, margin, parameters     |
|  - Normalizes subject/body for downstream agents            |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                 FILTERING NODE (Gemini Model)               |
|  - Analyze subject + body                                   |
|  - Predict: spam / neutral / positive / negative            |
|    informational / needs_review / action_required           |
|  - Spam or promotion → auto-skip                            |
+-------------------------------------------------------------+
                              |
                              v
                +----------------------------------+
                |  Is classification == spam?       |
                +----------------------------------+
                        |                 |
            Yes --------|-----> SKIP EMAIL         |
                        |        Update metrics     |
            No  --------v
+-------------------------------------------------------------+
|                SUMMARIZATION NODE (Gemini)                  |
|  - Generate concise 2–3 sentence summary                    |
|  - Extract problem, request, or intent                      |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  KNOWLEDGE BASE RETRIEVAL (RAG)             |
|  - ChromaDB + MiniLM embeddings                             |
|  - Semantic search using summary + email context            |
|  - Retrieve relevant FAQ/policy/company data                |
|  - Log RAG hit ratio (Prometheus)                           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|               RESPONSE GENERATION NODE (Gemini)             |
|  - Generate final structured reply                          |
|  - Use: summary + classification + RAG context + margin     |
|  - Maintain polite, professional tone                       |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                   EMAIL FORMATTING MODULE                   |
|  - Remove duplicate greetings                               |
|  - Detect sender name                                        |
|  - Build final structure:                                   |
|       Hi <Name>,                                            |
|       <Generated Response>                                  |
|       Regards,                                              |
|       <Your Name>                                           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|               HUMAN REVIEW DECISION NODE                    |
|  - If EmailState.requires_human_review == True             |
|       → route to Gmail Draft                                |
|  - Else                                                    |
|       → auto-send via SMTP                                  |
+-------------------------------------------------------------+
           /                                               \
          /                                                 \
         v                                                   v
+-------------------------------------+     +--------------------------------+
|          send_draft_to_gmail()      |     |            send_email()        |
|  - Save email to Gmail Drafts       |     |  - Send email via SMTP         |
|  - Visible on dashboard             |     |  - Deliver to recipient        |
+-------------------------------------+     +--------------------------------+
          \                                                  /
           \                                                /
            +----------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  UPDATE RECORDS & METRICS                   |
|  - Append entry to records/records.csv                      |
|  - Log summary, classification, reply, status               |
|  - Update Prometheus counters (latency, success, failures) |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|       CONTINUE PIPELINE (Rate Limit & Next Email)           |
|  - Optional sleep for Gmail safety throttling               |
|  - Move to next fetched or simulated email                  |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                   END PIPELINE EXECUTION                    |
|  - All emails processed or limit reached                    |
|  - Final summary logged + metrics pushed                    |
+-------------------------------------------------------------+
