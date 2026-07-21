from fastapi import APIRouter
from app.utils.metrics import summary

router = APIRouter()


@router.get("/metrics/latency")
def get_latency_metrics():
    """
    Returns count/avg/p50/p95/p99/min/max (in ms) for:
      - retrieval_latency_ms   (Pinecone vector search, in rag_service.get_medical_context)
      - llm_latency_ms         (OpenRouter chat completion call)
      - end_to_end_latency_ms  (full /ehr-advice request: retrieval + LLM + DB writes)

    Samples accumulate in-memory from live traffic since the server started
    (resets on restart). Great for a before/after latency chart or a quick
    screenshot for a demo video.
    """
    return {"success": True, "metrics": summary()}
