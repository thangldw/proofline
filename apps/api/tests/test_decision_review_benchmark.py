import json
from pathlib import Path

import pytest
from proofline.provenance_benchmark import benchmark_decision_review_refresh


def test_decision_review_refresh_benchmark_uses_real_ledger_and_integrity_paths():
    report = benchmark_decision_review_refresh(decision_count=25)

    assert report["schema"] == "proofline-decision-review-refresh-benchmark-v1"
    assert report["decision_count"] == 25
    assert report["review_count"] == 25
    assert report["refresh_latency_ms"] > 0
    assert report["verify_latency_ms"] > 0
    assert report["database_bytes"] > 0
    assert report["peak_python_memory_bytes"] > 0
    qualification = report["qualification"].lower()
    for excluded in ("connectors", "auth", "hosted sync", "network", "team production"):
        assert excluded in qualification


@pytest.mark.parametrize("count", [0, -1, True])
def test_decision_review_refresh_benchmark_rejects_invalid_counts(count):
    with pytest.raises(ValueError, match="decision_count must be a positive integer"):
        benchmark_decision_review_refresh(decision_count=count)


def test_committed_10k_decision_review_benchmark_is_explicitly_synthetic():
    root = Path(__file__).resolve().parents[3]
    receipt = json.loads(
        (root / "evals/benchmarks/decision-review-refresh-10000-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert receipt["schema"] == "proofline-decision-review-refresh-benchmark-v1"
    assert receipt["decision_count"] == receipt["review_count"] == 10_000
    assert receipt["fixture"] == "synthetic-generated-local-sqlite"
    assert "team production" in receipt["qualification"].lower()
    assert receipt["environment"]["python"]
