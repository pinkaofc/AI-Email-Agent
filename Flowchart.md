+---------------------------------------------------+
|                   START PIPELINE                  |
|     Initialize environment, logger, and config    |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|        FETCH EMAIL (choose input source)          |
| - Option 1: Fetch unread emails via IMAP          |
| - Option 2: Load from sample_emails.json          |
| - Limit and mark_as_seen handled dynamically      |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|        CREATE INITIAL EmailState OBJECT           |
| - Stores: current_email, id, metadata, status     |
| - Prepares context for supervisor_langgraph       |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|                 SUPERVISOR PIPELINE               |
|   (Manages the complete AI reasoning workflow)    |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|             FILTERING NODE (Gemini)               |
| - Analyze email subject/body                      |
| - Classify sentiment or type:                     |
|     spam / negative / positive / neutral /        |
|     needs_review / informational                  |
| - If spam or promotional → skip processing        |
+---------------------------------------------------+
                     |
                     v
            +-----------------------------+
            | Is classification == spam?  |
            +-----------------------------+
                     |
        Yes -------->| Skip and exit loop  |
                     |
        No  -------->v
+---------------------------------------------------+
|           SUMMARIZATION NODE (Gemini)             |
| - Generates a clear summary of sender’s request   |
| - Extracts main intent, issue, or requirement     |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|           KNOWLEDGE BASE RETRIEVAL (RAG)          |
| - Uses ChromaDB and Hugging Face embeddings       |
| - Retrieves context documents from knowledge_base |
| - Adds retrieved info to prompt context           |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|         RESPONSE GENERATION NODE (Gemini)         |
| - Composes a context-aware reply                  |
| - Uses: summary + classification + KB context     |
| - Produces structured AI response text            |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|             EMAIL FORMATTING MODULE               |
| - Uses utils/formatter.py                         |
| - Cleans body, removes redundant greetings        |
| - Adds proper name extraction                     |
| - Final structure:                                |
|       Hi <CustomerName>,                          |
|       <Generated Response Body>                   |
|       Best regards,                               |
|       <Your Name>                                 |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|           RESPONSE REVIEW DECISION NODE           |
| - Checks EmailState.requires_human_review         |
| - If True: draft email to your Gmail for review   |
| - If False: auto-send to original sender          |
+---------------------------------------------------+
          /                                 \
         /                                   \
        v                                     v
+---------------------------------+   +-----------------------------------+
|   send_draft_to_gmail()         |   |        send_email()               |
| - Sends draft to YOUR_GMAIL_    |   | - Sends directly via SMTP         |
|   ADDRESS_FOR_DRAFTS (config)   |   | - Recipient = sender in JSON/mail |
| - Allows manual review          |   | - Auto-formatted with formatter   |
+---------------------------------+   +-----------------------------------+
          \                                   /
           \                                 /
            +-------------------------------+
                     |
                     v
+---------------------------------------------------+
|           UPDATE EMAIL RECORDS (CSV)              |
| - Logs timestamp, classification, summary,        |
|   response, review flag, and send status          |
| - Stored in records/records.csv                   |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|     DELAY AND CONTINUE TO NEXT EMAIL              |
| - 10-second sleep to prevent rate-limit spam      |
| - Moves to next fetched or simulated email        |
+---------------------------------------------------+
                     |
                     v
+---------------------------------------------------+
|               END PIPELINE EXECUTION              |
| - All emails processed or limit reached           |
| - Logs summary completion message                 |
+---------------------------------------------------+
