import hashlib
import json
from pathlib import Path


def test_reranker_receipt_is_bound_to_dataset_and_not_overclaimed():
    root = Path(__file__).resolve().parents[3]
    dataset = root / "evals/reranking/seed-v1.json"
    receipt = json.loads(
        (root / "evals/benchmarks/reranker-token-overlap-v1.json").read_text(encoding="utf-8")
    )
    assert receipt["dataset_sha256"] == hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert receipt["query_count"] == 3
    assert receipt["mrr"] == 1.0
    assert "not real-model or pilot evidence" in receipt["qualification"]


def test_vector_index_receipt_covers_latency_memory_and_update_cost_without_scale_claim():
    root = Path(__file__).resolve().parents[3]
    receipt = json.loads(
        (root / "evals/benchmarks/vector-index-1000-v1.json").read_text(encoding="utf-8")
    )
    assert receipt["source_count"] == 1000
    assert receipt["indexed"] == 1000
    assert receipt["repeat_skipped"] == 1000
    assert receipt["candidate_result_count"] >= 1
    for field in (
        "index_latency_ms",
        "no_op_update_latency_ms",
        "search_latency_ms",
        "peak_python_memory_bytes",
        "database_bytes",
    ):
        assert receipt[field] > 0
    assert "not a 10,000-file or 1-GB scale claim" in receipt["qualification"]
