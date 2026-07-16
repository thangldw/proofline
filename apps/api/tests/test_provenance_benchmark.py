import json
from pathlib import Path

import pytest
from proofline.provenance_benchmark import (
    benchmark_decision_evidence_package,
    benchmark_provenance_scale,
)


def test_provenance_benchmark_reports_each_requested_scale_without_overclaiming():
    report = benchmark_provenance_scale([10, 100])

    assert report["schema"] == "proofline-provenance-scale-benchmark-v1"
    assert [profile["document_count"] for profile in report["profiles"]] == [10, 100]
    assert [profile["chunk_count"] for profile in report["profiles"]] == [10, 100]
    for profile in report["profiles"]:
        assert profile["build_latency_ms"] > 0
        assert profile["verify_latency_ms"] > 0
        assert profile["peak_python_memory_bytes"] > 0
    assert "does not establish database, retrieval" in report["qualification"]


def test_provenance_scale_receipt_covers_1k_10k_and_100k_without_overclaiming():
    root = Path(__file__).resolve().parents[3]
    receipt = json.loads(
        (root / "evals/benchmarks/provenance-scale-v1.json").read_text(encoding="utf-8")
    )

    assert [profile["document_count"] for profile in receipt["profiles"]] == [
        1_000,
        10_000,
        100_000,
    ]
    assert all(
        profile["document_count"] == profile["chunk_count"] for profile in receipt["profiles"]
    )
    assert "does not establish database, retrieval" in receipt["qualification"]


def test_decision_evidence_package_benchmark_reports_requested_metrics():
    report = benchmark_decision_evidence_package(iterations=3)

    assert report["iterations"] == 3
    assert report["ingest_latency_ms"] > 0
    assert report["package_build_latency_ms"] > 0
    assert report["verify_latency_ms_median"] > 0
    assert report["package_json_bytes"] > 0
    assert report["package_zip_bytes"] > report["package_json_bytes"]
    assert report["peak_python_memory_bytes"] > 0


def test_committed_decision_evidence_package_benchmark_receipt_is_qualified():
    root = Path(__file__).resolve().parents[3]
    receipt = json.loads(
        (root / "evals/benchmarks/decision-evidence-package-v1.json").read_text(encoding="utf-8")
    )

    assert receipt["schema"] == "proofline-decision-evidence-package-benchmark-v1"
    assert receipt["iterations"] == 100
    assert receipt["ingest_latency_ms"] > 0
    assert receipt["verify_latency_ms_median"] > 0
    assert receipt["package_zip_bytes"] > receipt["package_json_bytes"]
    assert "does not establish production capacity" in receipt["qualification"]


@pytest.mark.parametrize("iterations", [0, -1, True])
def test_decision_evidence_package_benchmark_rejects_invalid_iterations(iterations):
    with pytest.raises(ValueError, match="iterations must be a positive integer"):
        benchmark_decision_evidence_package(iterations)
