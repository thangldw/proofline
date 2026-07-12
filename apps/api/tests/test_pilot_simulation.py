import json
from pathlib import Path

import pytest
from proofline.pilot_simulation import (
    SyntheticPilotDataset,
    run_synthetic_pilot_simulation,
    write_simulation_report,
)

DATASET = Path("evals/pilot-simulation/engineering-context-v1.json")


def test_synthetic_pilot_runs_production_path_and_labels_limits(tmp_path: Path) -> None:
    report = run_synthetic_pilot_simulation(DATASET, proofline_revision="test-revision")

    assert report.artifact_type == "synthetic_pilot_simulation"
    assert "not external pilot" in report.qualification.lower()
    assert report.proofline_revision == "test-revision"
    assert report.task_count == 7
    assert report.persona_count == 5
    assert report.temporal_task_count == 1
    assert report.completed_tasks == report.task_count
    assert report.task_completion_rate == 1
    assert report.citation_resolution == 1
    assert report.citation_precision == 1
    assert report.proofline_sources_inspected < report.naive_sources_inspected
    assert report.source_inspection_reduction > 0
    assert all(task.local_latency_ms >= 0 for task in report.tasks)
    abstention = next(
        task for task in report.tasks if task.expected_status == "insufficient_evidence"
    )
    assert abstention.model_run_count == 0

    output = tmp_path / "receipt.json"
    write_simulation_report(output, report)
    restored = json.loads(output.read_text(encoding="utf-8"))
    assert restored["dataset_sha256"] == report.dataset_sha256


def test_synthetic_pilot_rejects_non_simulation_provenance(tmp_path: Path) -> None:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    payload["provenance"] = "external-pilot"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="synthetic-simulation"):
        run_synthetic_pilot_simulation(path)


def test_dataset_contract_rejects_unknown_source() -> None:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    payload["tasks"][0]["expected_statements"][0]["supporting_source_uris"] = [
        "synthetic://unknown"
    ]

    with pytest.raises(ValueError, match="unknown sources"):
        SyntheticPilotDataset.model_validate(payload)
