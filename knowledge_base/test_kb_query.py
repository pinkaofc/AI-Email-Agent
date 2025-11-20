import os
from dotenv import load_dotenv
from chromadb import PersistentClient
from chromadb.utils import embedding_functions


def main():
    load_dotenv()

    hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    if not hf_token:
        raise ValueError("HUGGINGFACEHUB_API_TOKEN not found. Add it to .env first.")

    # Exact same embedding model used in ingest.py
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    VECTOR_PATH = "knowledge_base/vector_store"

    print(f"\nLoading persistent vector store from: {VECTOR_PATH}")

    client = PersistentClient(path=VECTOR_PATH)

    # MUST match ingest.py:
    collection = client.get_or_create_collection(
        name="email_kb",
        embedding_function=embedding_fn
    )

    print("\nShipCube Knowledge Base Query Tool (Corrected Chroma Edition)")
    print("Type your question below (or 'exit' to quit):\n")

    while True:
        query = input("Query: ").strip()
        if query.lower() in ("exit", "quit"):
            print("Exiting Query Tool.")
            break

        try:
            results = collection.query(
                query_texts=[query],
                n_results=5,
                include=["documents", "distances", "metadatas"]
            )

            docs = results.get("documents", [[]])[0]

            if not docs:
                print("No matching documents found.\n")
                continue

            print("\nTop Matches:\n")

            for i, chunk in enumerate(docs, 1):
                print(f"Result {i}:")
                print(chunk[:600])  # preview first 600 chars
                print("-" * 60)

            print()

        except Exception as e:
            print(f"Error while searching: {e}\n")


if __name__ == "__main__":
    main()
