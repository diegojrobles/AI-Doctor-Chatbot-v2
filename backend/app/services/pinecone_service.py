import pinecone
import os
from dotenv import load_dotenv

load_dotenv()  # so local runs pick up .env


class PineconeService:
    def __init__(self):
        self.api_key = os.getenv("PINECONE_API_KEY")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "medical-knowledge")

        if not self.api_key:
            print("❌ PINECONE_API_KEY not set — Pinecone service disabled")
            self.index = None
            return

        try:
            # Initialize Pinecone with the new SDK
            self.pc = pinecone.Pinecone(api_key=self.api_key)

            # Connect to your existing index
            self.index = self.pc.Index(self.index_name)
            print("✅ Pinecone initialized successfully")

        except Exception as e:
            print(f"❌ Pinecone initialization error: {e}")
            self.index = None

    def query_medical_knowledge(self, query: str, n_results: int = 5):
        """Query medical knowledge using Pinecone's integrated embeddings"""
        try:
            if not self.index:
                print("❌ Pinecone index not available")
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            print(f"🔍 Querying Pinecone for: {query}")

            
            # Use search() for integrated embeddings
            results = self.index.search(
                namespace="medical-namespace",
                query={"inputs": {"text": query}, "top_k": n_results},
                # Omit `fields` so Pinecone returns all stored metadata
                # (title, year, journal, pubmed_id, etc.), not just "text".
            )

            # Format results to match your existing structure
            documents = []
            metadatas = []
            distances = []

            for hit in results["result"]["hits"]:
                documents.append(hit["fields"].get("text", ""))
                metadatas.append(hit["fields"])
                distances.append(1 - hit["score"])  # Convert similarity to distance

            print(f"✅ Found {len(documents)} results in Pinecone")
            return {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
            }

        except Exception as e:
            print(f"❌ Pinecone query error: {e}")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    def store_articles(self, articles):
        """Store PubMed articles in Pinecone using integrated embeddings"""
        try:
            if not self.index:
                print("❌ Pinecone index not available for storage")
                return False

            print(f"📝 Storing {len(articles)} PubMed articles in Pinecone")

            records = []
            for i, article in enumerate(articles):
                content = article.get("content", "")
                if not content or len(content.strip()) < 10:
                    continue

                # Format for upsert_records with integrated embedding
                record = {
                    "_id": f"pubmed_{article.get('pubmed_id', i)}",
                    "text": content,  # This field gets auto-embedded
                    "title": article.get("title", "No title"),
                    "year": article.get("year", "Unknown"),
                    "journal": article.get("journal", "Unknown"),
                    "pubmed_id": article.get("pubmed_id", "Unknown"),
                    "abstract": article.get("abstract", ""),
                    "keywords": ", ".join(article.get("keywords", [])),
                    "article_type": article.get("article_type", "research"),
                }
                records.append(record)

            if not records:
                print("❌ No valid articles to store")
                return False

            # Pinecone rejects overly large request bodies in one shot, so
            # send records in smaller batches instead of all at once.
            batch_size = 90
            total_stored = 0
            for start in range(0, len(records), batch_size):
                batch = records[start : start + batch_size]
                print(
                    f"🚀 Upserting batch {start // batch_size + 1} "
                    f"({len(batch)} records) to Pinecone..."
                )
                # (SDK requires these as keyword args: records=, namespace=)
                self.index.upsert_records(records=batch, namespace="medical-namespace")
                total_stored += len(batch)

            print(f"✅ Successfully stored {total_stored} articles in Pinecone")
            return True

        except Exception as e:
            print(f"❌ Pinecone storage error: {e}")
            return False


# Global instance
pinecone_service = PineconeService()
