# knowledge_base/query.py

# --- Fix sys.path when running this file directly ---
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import re
from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from config import VECTOR_STORE_PATH
from utils.logger import get_logger

# Monitoring metrics
from monitoring.metrics import (
    KB_QUERIES,
    KB_EMPTY_RESULTS,
)

logger = get_logger(__name__)

# ============================================================
#                 EMBEDDING MODEL
# ============================================================
embedding_model = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# ============================================================
#       SAFETY: prevent leaking sensitive KB chunks
# ============================================================
SUSPICIOUS_PATTERNS = [
    r"\bclient address\b",
    r"\bphone\b",
]

def _contains_sensitive(text: str) -> bool:
    """Detect sensitive or dangerous operational details."""
    if not text:
        return False
    return any(re.search(p, text, re.IGNORECASE) for p in SUSPICIOUS_PATTERNS)


# ============================================================
#                     CHROMA CLIENT
# ============================================================
def get_chroma_client():
    """Ensure vector store exists and return client."""
    os.makedirs(VECTOR_STORE_PATH, exist_ok=True)
    return PersistentClient(path=VECTOR_STORE_PATH)


# ============================================================
#         MAIN KB QUERY — SAFE, SANITIZED, METRICS
# ============================================================
def query_knowledge_base(query_text: str, top_k: int = 3) -> str:
    """
    Safe RAG retrieval (never throws errors):

    ✓ Never breaks pipeline  
    ✓ Sanitizes operational details  
    ✓ Deduplicates chunks  
    ✓ Logs metrics (KB_QUERIES, KB_EMPTY_RESULTS)  
    ✓ Returns "" on failure or no match  
    """

    KB_QUERIES.inc()

    try:
        client = get_chroma_client()

        try:
            collection = client.get_or_create_collection(
                name="email_kb",
                embedding_function=embedding_model
            )
        except Exception as e:
            logger.error(f"[KnowledgeBase] Could not load collection: {e}")
            KB_EMPTY_RESULTS.inc()
            return ""

        # Execute similarity search
        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=top_k,
                include=["documents", "distances"]
            )
        except Exception as e:
            logger.error(f"[KnowledgeBase] Query execution failed: {e}")
            KB_EMPTY_RESULTS.inc()
            return ""

        if not results or not results.get("documents"):
            logger.warning("[KnowledgeBase] No documents found.")
            KB_EMPTY_RESULTS.inc()
            return ""

        docs = results["documents"][0]
        clean_chunks = []
        seen = set()

        for chunk in docs:
            if not chunk:
                continue

            cleaned = " ".join(chunk.split()).strip()

            # Deduplicate
            if cleaned in seen or not cleaned:
                continue
            seen.add(cleaned)

            # Sanitize sensitive KB
            if _contains_sensitive(cleaned):
                logger.debug("[KnowledgeBase] Suppressed sensitive KB chunk.")
                continue

            clean_chunks.append(cleaned)

        if not clean_chunks:
            logger.warning("[KnowledgeBase] No sanitized KB chunks returned.")
            KB_EMPTY_RESULTS.inc()
            return ""

        final_text = "\n\n---\n\n".join(clean_chunks[:top_k]).strip()
        logger.info(f"[KnowledgeBase] Returning {len(clean_chunks)} chunk(s).")

        return final_text

    except Exception as e:
        logger.error(f"[KnowledgeBase] Fatal RAG error: {e}", exc_info=True)
        KB_EMPTY_RESULTS.inc()
        return ""


# ============================================================
#                        TESTING ENTRY
# ============================================================
if __name__ == "__main__":
    print("\n>> Testing KB Query ...")
    result = query_knowledge_base("What is ShipCube?")
    print("\nRESULT:\n", result)
