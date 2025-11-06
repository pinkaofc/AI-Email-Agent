# knowledge_base/query.py

import os
from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from config import VECTOR_STORE_PATH
from utils.logger import get_logger

logger = get_logger(__name__)

# Load embeddings (Hugging Face)
embedding_model = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

def get_chroma_client():
    """Initialize or connect to persistent Chroma client."""
    os.makedirs(VECTOR_STORE_PATH, exist_ok=True)
    return PersistentClient(path=VECTOR_STORE_PATH)

def query_knowledge_base(query_text: str, top_k: int = 3) -> str:
    """
    Queries the Chroma vector store to find the most relevant knowledge chunks.

    Args:
        query_text (str): The query to search for (email summary or question).
        top_k (int): Number of top similar documents to retrieve.

    Returns:
        str: Concatenated text from top matching chunks for context.
    """
    try:
        client = get_chroma_client()
        collection = client.get_or_create_collection(
            name="email_kb",
            embedding_function=embedding_model
        )

        results = collection.query(
            query_texts=[query_text],
            n_results=top_k
        )

        if results and results.get("documents"):
            context_chunks = results["documents"][0]
            context_text = "\n".join(context_chunks)
            logger.info(f"[KnowledgeBase] Retrieved {len(context_chunks)} context chunks.")
            return context_text.strip()
        else:
            logger.warning("[KnowledgeBase] No relevant context found.")
            return "No relevant context found in knowledge base."

    except Exception as e:
        logger.error(f"[KnowledgeBase] Query failed: {e}", exc_info=True)
        return "Knowledge base retrieval failed."
