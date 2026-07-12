from pathlib import Path

import pytest
from proofline.evaluation import discounted_cumulative_gain, evaluate_dataset, query_metrics


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
