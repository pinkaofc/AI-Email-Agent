import os
from pathlib import Path
from dotenv import load_dotenv
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma


# ============================================================
# SAFETY FILTERS (Prevent Sensitive Data From Being Embedded)
# ============================================================

SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",       # actual order IDs
    r"\btracking number\b",       # avoid hallucinating a number
    r"\bAWB\b",                   # airway bill numbers
    r"\bETA\b",                   # exact ETA
    r"\border id\b",              # specific identifiers
    r"\bclient address\b",        # PII
    r"\bphone\b",                 # PII
]


def scrub_sensitive_text(text: str) -> str:
    """Remove sensitive/operational details from text."""
    if not text:
        return ""

    for pattern in SUSPICIOUS_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)

    return " ".join(text.split()).strip()


# ============================================================
# LOAD ALL DOCUMENTS
# ============================================================

def load_all_documents(data_path: str):
    all_docs = []
    data_dir = Path(data_path)

    if not data_dir.exists():
        raise FileNotFoundError(f"Data folder not found: {data_dir.resolve()}")

    # TXT files
    for txt_file in data_dir.glob("*.txt"):
        try:
            loader = TextLoader(str(txt_file), encoding="utf-8")
            docs = loader.load()

            for d in docs:
                d.page_content = scrub_sensitive_text(d.page_content)

            all_docs.extend(docs)
            print(f"Loaded {len(docs)} clean documents from {txt_file.name}")

        except Exception as e:
            print(f"Error loading {txt_file.name}: {e}")

    # PDFs
    for pdf_file in data_dir.glob("*.pdf"):
        try:
            loader = PyPDFLoader(str(pdf_file))
            docs = loader.load()

            for d in docs:
                d.page_content = scrub_sensitive_text(d.page_content)

            all_docs.extend(docs)
            print(f"Loaded {len(docs)} sanitized pages from {pdf_file.name}")

        except Exception as e:
            print(f"Error loading {pdf_file.name}: {e}")

    print(f"Total sanitized documents loaded: {len(all_docs)}")
    return all_docs


# ============================================================
# CHUNKING
# ============================================================

def chunk_documents(docs):
    if not docs:
        print("No documents found to split.")
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=120
    )

    chunks = splitter.split_documents(docs)

    # Remove duplicates
    cleaned_chunks = []
    seen = set()

    for c in chunks:
        cleaned = scrub_sensitive_text(c.page_content)

        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            c.page_content = cleaned
            cleaned_chunks.append(c)

    print(f"Created {len(cleaned_chunks)} unique, safe chunks.")
    return cleaned_chunks


# ============================================================
# EMBEDDINGS + VECTOR STORE
# ============================================================

def embed_and_store(chunks, persist_path):
    if not chunks:
        raise ValueError("No chunks available to embed.")

    load_dotenv()
    hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")

    if not hf_token:
        raise ValueError("HUGGINGFACEHUB_API_TOKEN missing in .env")

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # CRITICAL FIX: Explicitly name the collection
    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_path,
        collection_name="email_kb"       # ← IMPORTANT
    )

    print(f"Knowledge Base stored safely at: {Path(persist_path).resolve()}")


# ============================================================
# MAIN
# ============================================================

def main():
    DATA_PATH = "knowledge_base/data"
    VECTOR_STORE_PATH = "knowledge_base/vector_store"

    print("Starting ShipCube Safe Knowledge Base Ingestion Pipeline...\n")

    docs = load_all_documents(DATA_PATH)
    if not docs:
        print("No documents found — cannot continue.")
        return

    chunks = chunk_documents(docs)
    if not chunks:
        print("Chunk creation failed — cannot continue.")
        return

    embed_and_store(chunks, VECTOR_STORE_PATH)

    print("\nKnowledge Base ingestion complete (SAFE MODE ENABLED).")


if __name__ == "__main__":
    main()
