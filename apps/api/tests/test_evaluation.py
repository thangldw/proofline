import json
from pathlib import Path

import pytest
from proofline.cli import main
from proofline.evaluation import (
    benchmark_lexical_search,
    discounted_cumulative_gain,
    evaluate_dataset,
    evaluate_extraction_dataset,
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
    assert report.positive_query_count == 15
    assert report.expected_empty_query_count == 0
    assert report.expected_empty_accuracy == 1
    assert report.recall_at_k >= 0.8
    assert report.ndcg_at_k >= 0.8
    assert any(not query.retrieved_source_uris for query in report.queries)


def test_versioned_unicode_retrieval_v2_excludes_old_terms_without_diluting_mrr():
    root = Path(__file__).resolve().parents[3]
    dataset = root / "evals/retrieval/seed-v2.json"

    report = evaluate_dataset(dataset)

    assert report.dataset_version == "retrieval-seed-v2"
    assert report.dataset_provenance == "synthetic-versioned-unicode"
    assert report.query_count == 26
    assert report.positive_query_count == 16
    assert report.expected_empty_query_count == 10
    assert report.expected_empty_accuracy == 1
    assert report.recall_at_k == 1
    assert report.mrr == 1
    assert report.ndcg_at_k == 1
    old_queries = [query for query in report.queries if query.expected_empty]
    current_queries = [query for query in report.queries if not query.expected_empty]
    assert len(old_queries) == 10
    assert all(query.retrieved_source_uris == [] for query in old_queries)
    assert all(query.empty_result_correct is True for query in old_queries)
    assert all(query.reciprocal_rank == 0 for query in old_queries)
    assert all(query.retrieved_source_uris for query in current_queries)
    assert any("unicode/chinese" in query.retrieved_source_uris[0] for query in current_queries)
    assert any("unicode/vietnamese" in query.retrieved_source_uris[0] for query in current_queries)
    assert any("unicode/japanese" in query.retrieved_source_uris[0] for query in current_queries)


def test_expected_empty_metrics_are_separate_from_positive_ranking_metrics():
    correct = query_metrics("negative-correct", [], {}, 10, expected_empty=True)
    incorrect = query_metrics(
        "negative-incorrect",
        ["source://unexpected"],
        {},
        10,
        expected_empty=True,
    )

    assert correct.empty_result_correct is True
    assert incorrect.empty_result_correct is False
    assert correct.reciprocal_rank == incorrect.reciprocal_rank == 0
    assert correct.ndcg_at_k == incorrect.ndcg_at_k == 0


def test_v2_cli_fails_when_an_obsolete_term_resolves(tmp_path, capsys):
    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "evals/retrieval/seed-v2.json").read_text(encoding="utf-8"))
    negative = next(query for query in payload["queries"] if query.get("expected_empty"))
    negative["question"] = "alphanew"
    dataset = tmp_path / "negative-regression.json"
    dataset.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        main(
            [
                "eval",
                "--dataset",
                str(dataset),
                "--min-expected-empty-accuracy",
                "1.0",
            ]
        )

    assert raised.value.code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["expected_empty_accuracy"] == pytest.approx(0.9)
    failed = next(query for query in output["queries"] if query["query_id"] == negative["id"])
    assert failed["empty_result_correct"] is False


@pytest.mark.parametrize(
    "arguments",
    [
        ["--min-recall", "nan"],
        ["--min-recall", "-0.1"],
        ["--min-ndcg", "1.1"],
        ["--min-expected-empty-accuracy", "inf"],
    ],
)
def test_retrieval_cli_rejects_invalid_thresholds(arguments, capsys):
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "eval",
                "--dataset",
                "evals/retrieval/seed-v2.json",
                *arguments,
            ]
        )

    assert raised.value.code == 2
    assert "usage:" in capsys.readouterr().err


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


def test_extraction_seed_is_reproducible_exact_and_clearly_synthetic():
    root = Path(__file__).resolve().parents[3]
    dataset = root / "evals/extraction/seed-v1.json"

    first = evaluate_extraction_dataset(dataset)
    second = evaluate_extraction_dataset(dataset)

    assert first == second
    assert first.dataset_version == "extraction-seed-v1"
    assert first.dataset_provenance == "synthetic-marked-memory"
    assert first.source_count == 5
    assert first.negative_source_count == 1
    assert first.model_run_count == 0
    assert first.expected_count == first.extracted_count == first.matched_count == 12
    assert first.precision == first.recall == first.f1 == 1
    assert first.evidence_resolution == 1
    assert first.expected_evidence_accuracy == 1
    assert first.negative_source_accuracy == 1
    assert {item.kind for item in first.kinds} == {
        "decision",
        "assumption",
        "constraint",
        "alternative",
    }
    assert all(item.f1 == 1 for item in first.kinds)
    negative = next(item for item in first.sources if item.expected_count == 0)
    assert negative.extracted_count == 0


def modified_extraction_dataset(tmp_path: Path, *, evidence_only: bool) -> Path:
    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "evals/extraction/seed-v1.json").read_text(encoding="utf-8"))
    expected = payload["sources"][0]["expected_memories"][0]
    if evidence_only:
        expected["evidence_quote"] = "synthetic incorrect evidence expectation"
    else:
        expected["statement"] = "synthetic missing statement"
    path = tmp_path / ("evidence-only.json" if evidence_only else "object-mismatch.json")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_extraction_metrics_expose_object_and_evidence_regressions(tmp_path):
    object_report = evaluate_extraction_dataset(
        modified_extraction_dataset(tmp_path, evidence_only=False)
    )
    evidence_report = evaluate_extraction_dataset(
        modified_extraction_dataset(tmp_path, evidence_only=True)
    )

    assert object_report.matched_count == 11
    assert object_report.false_positive_count == 1
    assert object_report.false_negative_count == 1
    assert 0 < object_report.f1 < 1
    assert object_report.evidence_resolution == 1
    assert evidence_report.f1 == 1
    assert evidence_report.evidence_resolution == 1
    assert evidence_report.expected_evidence_accuracy == pytest.approx(11 / 12)


def test_extraction_cli_gate_passes_and_fails_thresholds(tmp_path, capsys):
    root = Path(__file__).resolve().parents[3]
    dataset = root / "evals/extraction/seed-v1.json"
    main(
        [
            "eval-extraction",
            "--dataset",
            str(dataset),
            "--min-f1",
            "1.0",
            "--min-evidence-resolution",
            "1.0",
        ]
    )
    assert json.loads(capsys.readouterr().out)["dataset_provenance"] == ("synthetic-marked-memory")

    with pytest.raises(SystemExit) as raised:
        main(
            [
                "eval-extraction",
                "--dataset",
                str(modified_extraction_dataset(tmp_path, evidence_only=True)),
                "--min-expected-evidence-accuracy",
                "1.0",
            ]
        )
    assert raised.value.code == 1
    assert json.loads(capsys.readouterr().out)["expected_evidence_accuracy"] < 1


def test_extraction_cli_rejects_invalid_threshold(capsys):
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "eval-extraction",
                "--dataset",
                "evals/extraction/seed-v1.json",
                "--min-f1",
                "nan",
            ]
        )

    assert raised.value.code == 2
    assert "usage:" in capsys.readouterr().err


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
