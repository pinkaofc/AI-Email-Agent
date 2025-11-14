+---------------------------------------------------+
|                   EMAIL BOT PIPELINE                  |
|     Initialize environment, logger, and config    |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|        FETCH EMAIL (choose input source)          |
| - Option 1: Fetch unread emails via IMAP          |
| - Option 2: Load from sample_emails.json          |
| - Limits, mark_as_seen handled dynamically        |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|         CREATE INITIAL EmailState OBJECT          |
| - Stores email content, ID, metadata, status      |
| - Prepares context for supervisor workflow        |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|                 SUPERVISOR PIPELINE               |
|   (LangGraph orchestrates full reasoning steps)   |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|             FILTERING NODE (Gemini)               |
| - Analyze subject + body                           |
| - Predict sentiment/type:                          |
|     spam / negative / positive / neutral /         |
|     needs_review / informational                   |
| - Spam & promos → skipped automatically            |
+---------------------------------------------------+
                     |
                     v
            +-----------------------------+
            | Is classification == spam?  |
            +-----------------------------+
                     |
        Yes -------->|        SKIP        |
                     |   Exit this email  |
        No  -------->v
+---------------------------------------------------+
|           SUMMARIZATION NODE (Gemini)             |
| - Generates a concise 2–3 sentence summary        |
| - Extracts request, intent, or issue              |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|           KNOWLEDGE BASE RETRIEVAL (RAG)          |
| - ChromaDB + HF MiniLM embeddings                  |
| - Semantic search based on email context           |
| - Retrieves matched chunks from knowledge_base/    |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|         RESPONSE GENERATION NODE (Gemini)         |
| - Creates final structured reply                   |
| - Uses summary + classification + KB context       |
| - Ensures professional tone and clarity            |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|             EMAIL FORMATTING MODULE               |
| - Cleans redundant greetings & spacing             |
| - Extracts sender name                             |
| - Builds final structure:                          |
|       Hi <Name>,                                   |
|       <Generated response>                         |
|       Best regards,                                |
|       <Your Name>                                  |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|           RESPONSE REVIEW DECISION NODE           |
| - Check EmailState.requires_human_review          |
| - If True → send draft to your Gmail              |
| - If False → auto-send to original sender         |
+---------------------------------------------------+
          /                                   \
         /                                     \
        v                                       v
+---------------------------------+   +-----------------------------------+
|         send_draft_to_gmail()   |   |            send_email()           |
| - Sends draft to your Gmail     |   | - Sends via SMTP                  |
| - For manual review/approval    |   | - Delivered to original sender    |
+---------------------------------+   +-----------------------------------+
          \                                     /
           \                                   /
            +---------------------------------+
                     |
                     v
+---------------------------------------------------+
|           UPDATE EMAIL RECORDS (CSV)              |
| - Logs: timestamp, classification, summary,        |
|   AI reply, review flag, send status               |
| - Saved in records/records.csv                     |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|     DELAY AND CONTINUE TO NEXT EMAIL              |
| - 10-second sleep (rate-limit protection)         |
| - Move to next fetched/simulated message          |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|               END PIPELINE EXECUTION              |
| - All emails processed or limit reached           |
| - Logs final completion summary                   |
+---------------------------------------------------+
