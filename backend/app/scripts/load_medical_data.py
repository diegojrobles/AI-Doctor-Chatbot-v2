"""
One-time (or occasional) data loader: pulls medical research articles from
PubMed for a list of common symptoms, and upserts them into the Pinecone
"medical-knowledge" index so the RAG pipeline has something to retrieve.

Run it with:
    cd backend
    python -m app.scripts.load_medical_data
"""

from app.services.pubmed_service import get_article_from_pubmed, common_symptoms
from app.services.pinecone_service import pinecone_service


def load_medical_data(symptoms: list[str] = None) -> None:
    symptoms = symptoms or common_symptoms

    if not pinecone_service.index:
        print(
            "❌ Pinecone index not available — check PINECONE_API_KEY and "
            "PINECONE_INDEX_NAME in your .env file before running this."
        )
        return

    print(f"📚 Fetching PubMed articles for {len(symptoms)} symptoms: {symptoms}")
    articles = get_article_from_pubmed(symptoms)
    print(f"📥 Retrieved {len(articles)} articles from PubMed")

    if not articles:
        print("❌ No articles retrieved — nothing to store. Check your network/PubMed access.")
        return

    success = pinecone_service.store_articles(articles)

    if success:
        print(f"✅ Successfully loaded {len(articles)} articles into Pinecone")
    else:
        print("❌ Failed to store articles in Pinecone — check the error above")


if __name__ == "__main__":
    load_medical_data()
