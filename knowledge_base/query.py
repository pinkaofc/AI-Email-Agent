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

logger = get_logger(__name__)

# -------------------------------
# Embedding Model
# -------------------------------
embedding_model = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# -------------------------------
# Sensitive Leak Firewall (light)
# -------------------------------
SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",      # real order IDs
    r"\btracking number\b",
    r"\bAWB\b",
    r"\bETA\b",
    r"\border id\b",
    r"\bclient address\b",
    r"\bphone\b",
]

def _contains_sensitive(text: str) -> bool:
    """Detect if a KB chunk contains risky operational or personal info."""
    for p in SUSPICIOUS_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False

# -------------------------------
# Connect to Chroma
# -------------------------------
def get_chroma_client():
    os.makedirs(VECTOR_STORE_PATH, exist_ok=True)
    return PersistentClient(path=VECTOR_STORE_PATH)

# -------------------------------
# Improved RAG Query (SAFE + LESS STRICT)
# -------------------------------
def query_knowledge_base(query_text: str, top_k: int = 3) -> str:
    """
    RAG retrieval (testing mode):
    - No sensitive filtering
    - No relevance threshold
    - Guarantees output
    """
    try:
        client = get_chroma_client()
        collection = client.get_or_create_collection(
            name="email_kb",
            embedding_function=embedding_model
        )

        results = collection.query(
            query_texts=[query_text],
            n_results=top_k,
            include=["documents", "distances"]
        )

        if not results or not results.get("documents"):
            logger.warning("[KnowledgeBase] No results found.")
            return ""

        documents = results["documents"][0]
        clean_chunks = []

        seen = set()

        for doc_text in documents:
            cleaned = " ".join(doc_text.split()).strip()
            if cleaned and cleaned not in seen:
                clean_chunks.append(cleaned)
                seen.add(cleaned)

        if not clean_chunks:
            logger.warning("[KnowledgeBase] No chunks survived normalization.")
            return ""

        logger.info(f"[KnowledgeBase] Returning {len(clean_chunks)} raw chunks (TEST MODE).")

        return "\n\n---\n\n".join(clean_chunks[:3]).strip()

    except Exception as e:
        logger.error(f"[KnowledgeBase] Query failed: {e}", exc_info=True)
        return ""

# -------------------------------
# Manual Test
# -------------------------------
if __name__ == "__main__":
    print("\n>> Testing KB Query ...")
    res = query_knowledge_base("What is ShipCube?")
    print("\nRESULT:\n", res)
