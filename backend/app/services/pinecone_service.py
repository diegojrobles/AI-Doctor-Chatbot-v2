import pinecone
import os


class PineconeService:
    def __init__(self):
        self.api_key = "***REMOVED***"
        self.index_name = "medical-knowledge"

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

            # Use Pinecone's integrated embeddings for querying
            results = self.index.query(
                namespace="medical-namespace",
                query=query,  # Pinecone automatically embeds this text
                top_k=n_results,
                include_metadata=True,
            )

            # Format results to match your existing structure
            documents = []
            metadatas = []
            distances = []

            for match in results.matches:
                documents.append(match.metadata.get("chunk_text", ""))
                metadatas.append(match.metadata)
                distances.append(1 - match.score)  # Convert similarity to distance

            print(f"✅ Found {len(documents)} results in Pinecone")
            return {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
            }

        except Exception as e:
            print(f"❌ Pinecone query error: {e}")
            # Return empty results but don't break the app
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
                    "chunk_text": content,  # This field gets auto-embedded
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

            print(f"🚀 Upserting {len(records)} records to Pinecone...")

            # Use upsert_records for integrated embeddings
            self.index.upsert_records("medical-namespace", records)

            print(f"✅ Successfully stored {len(records)} articles in Pinecone")
            return True

        except Exception as e:
            print(f"❌ Pinecone storage error: {e}")
            return False


# Global instance
pinecone_service = PineconeService()
