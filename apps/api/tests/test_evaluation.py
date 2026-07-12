from pathlib import Path

import pytest
from proofline.evaluation import (
    benchmark_lexical_search,
    discounted_cumulative_gain,
    evaluate_dataset,
    percentile,
    query_metrics,
)


def test_retrieval_metric_formulas():
    metrics = query_metrics(
        "formula",
        ["source://irrelevant", "source://best", "source://partial"],
        {"source://best": 3, "source://partial": 1},
        3,
    )

    assert metrics.recall_at_k == 1
    assert metrics.precision_at_k == pytest.approx(2 / 3)
    assert metrics.reciprocal_rank == 0.5
    assert 0 < metrics.ndcg_at_k < 1
    assert discounted_cumulative_gain([3, 1]) > discounted_cumulative_gain([1, 3])


def test_seed_dataset_is_reproducible_and_clearly_synthetic():
    root = Path(__file__).resolve().parents[3]
    report = evaluate_dataset(root / "evals/retrieval/seed-v1.json")

    assert report.dataset_version == "seed-v1"
    assert report.dataset_provenance == "synthetic"
    assert report.query_count == 15
    assert report.recall_at_k >= 0.8
    assert report.ndcg_at_k >= 0.8
    assert any(not query.retrieved_source_uris for query in report.queries)


def test_percentile_uses_linear_interpolation():
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([0, 10], 95) == pytest.approx(9.5)
    assert percentile([7], 95) == 7
    with pytest.raises(ValueError):
        percentile([], 95)


def test_small_lexical_benchmark_reports_fixture_and_latency_schema():
    report = benchmark_lexical_search(source_count=12, query_count=20, result_limit=3)

    assert report.fixture_version == "lexical-generated-v1"
    assert report.fixture_provenance == "synthetic-generated"
    assert report.source_count == 12
    assert report.chunk_count == 12
    assert report.query_count == 20
    assert report.matched_query_count == 20
    assert report.result_limit == 3
    assert report.latency_unit == "milliseconds"
    assert 0 <= report.latency.p50 <= report.latency.p95 <= report.latency.max
