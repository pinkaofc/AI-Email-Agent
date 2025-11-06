import os
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma


def main():
    load_dotenv()
    hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    if not hf_token:
        raise ValueError("HUGGINGFACEHUB_API_TOKEN not found. Please add it to .env")

    # Use the same model you used in ingest.py
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    db = Chroma(
        persist_directory="knowledge_base/vector_store",
        embedding_function=embeddings
    )

    print("\nShipCube Knowledge Base Query Tool (Hugging Face Edition)")
    print("Type your question below (or 'exit' to quit):\n")

    while True:
        query = input("Query: ")
        if query.lower() in ["exit", "quit"]:
            print("Exiting Query Tool.")
            break

        try:
            results = db.similarity_search(query, k=3)
            if not results:
                print("No matching documents found.\n")
                continue

            print("\nTop Matches:\n")
            for i, doc in enumerate(results, 1):
                print(f"Result {i}:")
                print(doc.page_content[:500])
                print("-" * 60)
            print()

        except Exception as e:
            print(f"Error while searching: {e}\n")


if __name__ == "__main__":
    main()
