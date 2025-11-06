import os
from pathlib import Path
from dotenv import load_dotenv

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma


def load_all_documents(data_path: str):
    """
    Loads all .txt and .pdf documents from the data directory.
    Ignores unreadable or empty files and reports errors gracefully.
    """
    all_docs = []
    data_dir = Path(data_path)

    if not data_dir.exists():
        raise FileNotFoundError(f"Data folder not found: {data_dir.resolve()}")

    # Load all text files
    for txt_file in data_dir.glob("*.txt"):
        try:
            loader = TextLoader(str(txt_file), encoding="utf-8")
            docs = loader.load()
            all_docs.extend(docs)
            print(f"Loaded {len(docs)} documents from {txt_file.name}")
        except Exception as e:
            print(f"Error loading {txt_file.name}: {e}")

    # Load all PDFs
    for pdf_file in data_dir.glob("*.pdf"):
        try:
            loader = PyPDFLoader(str(pdf_file))
            docs = loader.load()
            all_docs.extend(docs)
            print(f"Loaded {len(docs)} pages from {pdf_file.name}")
        except Exception as e:
            print(f"Error loading {pdf_file.name}: {e}")

    print(f"Total documents loaded: {len(all_docs)}")
    return all_docs


def chunk_documents(docs):
    """
    Splits loaded documents into manageable overlapping text chunks.
    These chunks are used for embedding and semantic search.
    """
    if not docs:
        print("No documents found to split. Exiting.")
        return []

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    print(f"Created {len(chunks)} text chunks.")
    return chunks


def embed_and_store(chunks, persist_path):
    """
    Generates embeddings using Hugging Face and saves them to a Chroma vector store.
    """
    if not chunks:
        raise ValueError("No document chunks available to embed. Ensure data files exist and are readable.")

    load_dotenv()
    hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    if not hf_token:
        raise ValueError("HUGGINGFACEHUB_API_TOKEN missing from .env file")

    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_path
    )

    # .persist() is deprecated — saving is automatic
    print(f"Knowledge Base stored automatically at: {Path(persist_path).resolve()}")


def main():
    DATA_PATH = "knowledge_base/data"
    VECTOR_STORE_PATH = "knowledge_base/vector_store"

    print("Starting ShipCube Knowledge Base Ingestion Pipeline...")
    docs = load_all_documents(DATA_PATH)

    if not docs:
        print("No documents were loaded. Please check your data directory and try again.")
        return

    chunks = chunk_documents(docs)
    if not chunks:
        print("No text chunks were created. Aborting ingestion.")
        return

    embed_and_store(chunks, VECTOR_STORE_PATH)
    print("Knowledge Base ingestion complete.")


if __name__ == "__main__":
    main()
