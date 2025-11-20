from config import VECTOR_STORE_PATH
from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from utils.logger import get_logger

logger = get_logger(__name__)

embedding_model = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

client = PersistentClient(path=VECTOR_STORE_PATH)
col = client.get_or_create_collection(name="email_kb", embedding_function=embedding_model)

try:
    # try to list ids / metadatas (API varies by chroma version)
    ids = col.get(ids=[])
    logger.info("Sample collection call succeeded")
except Exception as e:
    logger.info("collection.get() not supported; will try query sample")

res = col.query(query_texts=["test"], n_results=3, include=["documents", "metadatas", "distances"])
print("QUERY RESULT KEYS:", res.keys())
print("Docs:", res.get("documents"))
print("Distances:", res.get("distances"))
print("Metadatas:", res.get("metadatas"))
