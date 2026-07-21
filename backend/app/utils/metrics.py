"""
Lightweight in-memory latency metrics collector.

No external dependencies (no Prometheus/Datadog needed) — good enough to
demo p50/p95 latency for the retrieval step, the LLM call, and the full
request in a video or README chart. Metrics reset when the server restarts;
swap `_STORE` for a persistent backend before deploying to production.
"""

import time
import statistics
from collections import deque
from contextlib import contextmanager
from threading import Lock

# How many recent samples to keep per metric, so memory doesn't grow forever.
_MAX_SAMPLES = 500

_STORE: dict[str, deque] = {}
_LOCK = Lock()


def record(metric_name: str, duration_ms: float) -> None:
    """Record a single latency sample (in milliseconds) for a named metric."""
    with _LOCK:
        if metric_name not in _STORE:
            _STORE[metric_name] = deque(maxlen=_MAX_SAMPLES)
        _STORE[metric_name].append(duration_ms)


@contextmanager
def timer(metric_name: str):
    """
    Context manager that times a block of code and records the duration.

    Usage:
        with timer("retrieval_latency_ms"):
            results = query_medical_knowledge(...)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        record(metric_name, elapsed_ms)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return round(sorted_values[f], 2)
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return round(d0 + d1, 2)


def summary() -> dict:
    """Return count/avg/p50/p95/p99/min/max for every metric recorded so far."""
    with _LOCK:
        snapshot = {name: list(values) for name, values in _STORE.items()}

    result = {}
    for name, values in snapshot.items():
        if not values:
            continue
        sorted_values = sorted(values)
        result[name] = {
            "count": len(values),
            "avg_ms": round(statistics.mean(values), 2),
            "p50_ms": _percentile(sorted_values, 50),
            "p95_ms": _percentile(sorted_values, 95),
            "p99_ms": _percentile(sorted_values, 99),
            "min_ms": round(min(values), 2),
            "max_ms": round(max(values), 2),
        }
    return result


def reset() -> None:
    """Clear all recorded metrics (handy between demo runs)."""
    with _LOCK:
        _STORE.clear()
