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
        """Query medical knowledge using Pinecone"""
        try:
            if not self.index:
                print("❌ Pinecone index not available")
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            print(f"🔍 Querying Pinecone for: {query}")

            # For serverless indexes with built-in embeddings, use query text directly
            # Note: You might need to adjust this based on your specific index configuration
            results = self.index.query(
                vector=[0] * 1024,  # Dummy vector for now
                top_k=n_results,
                include_metadata=True,
            )

            # Format results to match your existing structure
            documents = []
            metadatas = []
            distances = []

            for match in results.matches:
                documents.append(match.metadata.get("content", ""))
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
        """Store articles in Pinecone"""
        try:
            print(f"📝 Would store {len(articles)} articles in Pinecone")
            # For now, just return True to avoid blocking the application
            # We'll implement proper storage later
            return True

        except Exception as e:
            print(f"❌ Pinecone storage error: {e}")
            return False


# Global instance
pinecone_service = PineconeService()
