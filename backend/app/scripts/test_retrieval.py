"""
Retrieval accuracy evaluation for the medical-knowledge RAG pipeline.

There's no hand-labeled "gold" relevance dataset for this project yet, so
this harness uses a practical proxy that's standard for small RAG projects:
each eval query is paired with a set of expected keywords/topics a truly
relevant article should mention. A returned article "hits" if enough of
those keywords appear in its title+content.

From that we compute, at k = TOP_K:
  - Hit Rate@k      - fraction of queries with >=1 relevant doc in top k
  - Precision@k     - avg fraction of the top k docs that were relevant
  - MRR             - mean reciprocal rank of the first relevant doc
  - Avg similarity  - average cosine similarity (relevance_score) Pinecone
                       itself reported for the top k docs, hit or not

Run it with:
    cd backend
    python -m app.scripts.test_retrieval

Requires PINECONE_API_KEY to be set (see backend/.env.example) and the
index to already be populated (run load_medical_data.py first if empty).
"""

import json
import statistics
from datetime import datetime, timezone

from app.services.vector_store import query_medical_knowledge

TOP_K = 5

# Each entry: a symptom query a patient might type, plus keywords we'd
# expect a genuinely relevant medical article to contain. Extend this list
# as you add more symptoms/specialties to the knowledge base.
EVAL_SET = [
    {
        "query": "I have a bad headache and sensitivity to light",
        "expected_keywords": ["headache", "migraine", "photophobia"],
    },
    {
        "query": "persistent dry cough for two weeks",
        "expected_keywords": ["cough", "respiratory", "bronch"],
    },
    {
        "query": "sharp chest pain when breathing deeply",
        "expected_keywords": ["chest pain", "cardiac", "pulmonary", "pleuritic"],
    },
    {
        "query": "lower back pain after lifting something heavy",
        "expected_keywords": ["back pain", "musculoskeletal", "lumbar", "strain"],
    },
    {
        "query": "feeling dizzy and lightheaded when standing up",
        "expected_keywords": ["dizziness", "orthostatic", "vertigo", "hypotension"],
    },
    {
        "query": "sore throat and difficulty swallowing",
        "expected_keywords": ["sore throat", "pharyngitis", "throat"],
    },
    {
        "query": "joint pain and swelling in my knees",
        "expected_keywords": ["joint pain", "arthritis", "inflammation"],
    },
    {
        "query": "nausea and stomach cramps after eating",
        "expected_keywords": ["nausea", "abdominal", "gastro", "stomach"],
    },
    {
        "query": "shortness of breath during light exercise",
        "expected_keywords": ["shortness of breath", "dyspnea", "respiratory", "cardiac"],
    },
    {
        "query": "skin rash that is red and itchy",
        "expected_keywords": ["rash", "dermat", "skin"],
    },
]

MIN_KEYWORD_HITS = 1  # how many expected keywords must appear for a doc to count as "relevant"


def is_relevant(doc_text: str, expected_keywords: list[str]) -> bool:
    text = doc_text.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in text)
    return hits >= MIN_KEYWORD_HITS


def evaluate_query(query: str, expected_keywords: list[str], k: int = TOP_K) -> dict:
    results = query_medical_knowledge(query, n_results=k)
    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]

    relevant_flags = [is_relevant(doc, expected_keywords) for doc in documents]
    similarities = [1 - d for d in distances] if distances else []

    precision_at_k = sum(relevant_flags) / k if k else 0.0
    hit = any(relevant_flags)

    reciprocal_rank = 0.0
    for rank, is_rel in enumerate(relevant_flags, start=1):
        if is_rel:
            reciprocal_rank = 1 / rank
            break

    return {
        "query": query,
        "num_returned": len(documents),
        "precision_at_k": round(precision_at_k, 3),
        "hit": hit,
        "reciprocal_rank": round(reciprocal_rank, 3),
        "avg_similarity": round(statistics.mean(similarities), 3) if similarities else 0.0,
    }


def run_evaluation() -> dict:
    per_query_results = [
        evaluate_query(item["query"], item["expected_keywords"]) for item in EVAL_SET
    ]

    precisions = [r["precision_at_k"] for r in per_query_results]
    hits = [r["hit"] for r in per_query_results]
    rr = [r["reciprocal_rank"] for r in per_query_results]
    sims = [r["avg_similarity"] for r in per_query_results]

    aggregate = {
        "num_queries": len(per_query_results),
        "top_k": TOP_K,
        f"hit_rate_at_{TOP_K}": round(sum(hits) / len(hits), 3) if hits else 0.0,
        f"mean_precision_at_{TOP_K}": round(statistics.mean(precisions), 3)
        if precisions
        else 0.0,
        "mean_reciprocal_rank": round(statistics.mean(rr), 3) if rr else 0.0,
        "mean_similarity": round(statistics.mean(sims), 3) if sims else 0.0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return {"aggregate": aggregate, "per_query": per_query_results}


if __name__ == "__main__":
    report = run_evaluation()

    print("\n=== Retrieval Accuracy Report ===")
    for key, value in report["aggregate"].items():
        print(f"{key}: {value}")

    print("\n--- Per-query breakdown ---")
    for r in report["per_query"]:
        status = "OK" if r["hit"] else "MISS"
        print(
            f"[{status}] \"{r['query']}\" -> precision={r['precision_at_k']}, "
            f"MRR={r['reciprocal_rank']}, avg_sim={r['avg_similarity']}"
        )

    out_path = "retrieval_eval_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to {out_path}")
