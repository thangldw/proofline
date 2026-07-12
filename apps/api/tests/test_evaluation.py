import json
from pathlib import Path

import pytest
from proofline.cli import main
from proofline.evaluation import (
    benchmark_lexical_search,
    discounted_cumulative_gain,
    evaluate_dataset,
    evaluate_grounded_dataset,
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


def test_grounded_seed_is_reproducible_and_clearly_synthetic():
    root = Path(__file__).resolve().parents[3]
    dataset = root / "evals/grounded-qa/seed-v1.json"

    first = evaluate_grounded_dataset(dataset)
    second = evaluate_grounded_dataset(dataset)

    assert first == second
    assert first.dataset_version == "grounded-seed-v1"
    assert first.dataset_provenance == "synthetic-scripted"
    assert first.query_count == 7
    assert first.citation_resolution == 1
    assert first.citation_precision == 1
    assert first.grounded_success == 1
    assert first.expected_status_accuracy == 1
    assert {kind for query in first.queries for kind in query.actual_statement_kinds} == {
        "direct",
        "synthesis",
        "inference",
    }
    insufficient = next(query for query in first.queries if query.query_id == "gq07-insufficient")
    assert insufficient.actual_status == "insufficient_evidence"
    assert insufficient.model_run_count == 0
    assert insufficient.emitted_citations == 0


def invalid_grounded_dataset(tmp_path: Path) -> Path:
    path = tmp_path / "invalid-grounded.json"
    path.write_text(
        json.dumps(
            {
                "version": "invalid-test-v1",
                "provenance": "synthetic-test",
                "description": "A test-only fixture whose expected source is not retrieved.",
                "sources": [
                    {
                        "title": "Retrieved source",
                        "uri": "test://retrieved",
                        "content": "Decision: Use SQLite for local metadata.",
                    },
                    {
                        "title": "Unretrieved expected source",
                        "uri": "test://expected",
                        "content": "Decision: Use NATS for messaging.",
                    },
                ],
                "queries": [
                    {
                        "id": "invalid-citation",
                        "question": "SQLite local metadata",
                        "expected_status": "grounded",
                        "expected_statements": [
                            {
                                "text": "This statement intentionally expects another source.",
                                "kind": "direct",
                                "supporting_source_uris": ["test://expected"],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_unresolved_scripted_citation_fails_closed_without_inflating_metrics(tmp_path):
    report = evaluate_grounded_dataset(invalid_grounded_dataset(tmp_path))

    query = report.queries[0]
    assert query.actual_status == "validation_failed"
    assert query.error_code == "grounding_unknown_evidence"
    assert query.model_run_count == 2
    assert query.emitted_citations == 1
    assert query.resolved_citations == 0
    assert query.relevant_citations == 0
    assert report.citation_resolution == 0
    assert report.citation_precision == 0
    assert report.grounded_success == 0
    assert report.expected_status_accuracy == 0


def test_grounded_cli_exits_when_a_threshold_is_missed(tmp_path, capsys):
    dataset = invalid_grounded_dataset(tmp_path)

    with pytest.raises(SystemExit) as raised:
        main(
            [
                "eval-grounded",
                "--dataset",
                str(dataset),
                "--min-citation-resolution",
                "1.0",
            ]
        )

    assert raised.value.code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["dataset_provenance"] == "synthetic-test"
    assert output["citation_resolution"] == 0


@pytest.mark.parametrize(
    "arguments",
    [
        ["--limit", "0"],
        ["--limit", "13"],
        ["--min-citation-resolution", "-0.1"],
        ["--min-citation-precision", "1.1"],
        ["--min-grounded-success", "nan"],
    ],
)
def test_grounded_cli_rejects_invalid_bounds(arguments, capsys):
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "eval-grounded",
                "--dataset",
                "evals/grounded-qa/seed-v1.json",
                *arguments,
            ]
        )

    assert raised.value.code == 2
    assert "usage:" in capsys.readouterr().err
