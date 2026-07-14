import csv
import hashlib
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
namespace = runpy.run_path(ROOT / "scripts/analyze_pilot.py")
analyze_pilot = namespace["analyze_pilot"]
PilotDataError = namespace["PilotDataError"]


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _dataset(tmp_path: Path) -> Path:
    version = "private-pilot-v1"
    questions = [
        {
            "schema_version": "pilot-question-v1",
            "record_status": "eligible",
            "question_id": f"question-{index}",
            "temporal_required": index < 10,
        }
        for index in range(25)
    ]
    (tmp_path / "questions.jsonl").write_text(
        "".join(json.dumps(question) + "\n" for question in questions), encoding="utf-8"
    )
    _csv(
        tmp_path / "attempts.csv",
        [
            {
                "dataset_version": version,
                "attempt_id": f"attempt-{index}",
                "question_id": f"question-{index}",
                "team_id": f"team-{index % 3}",
                "baseline_completion_status": "completed",
                "proofline_completion_status": "completed",
                "baseline_seconds": 120,
                "proofline_seconds": 48,
                "useful_adjudicated": "true",
                "exclusion_reason": "",
            }
            for index in range(25)
        ],
    )
    _csv(
        tmp_path / "citations.csv",
        [
            {
                "dataset_version": version,
                "citation_judgment_id": f"judgment-{index}",
                "attempt_id": f"attempt-{index}",
                "citation_judgment": "supported",
                "adjudication_status": "not_needed",
                "adjudicated_judgment": "",
                "resolves_exact_span": "true",
                "authorized_source": "true",
            }
            for index in range(25)
        ],
    )
    _csv(
        tmp_path / "weekly-usage.csv",
        [
            {
                "dataset_version": version,
                "team_id": f"team-{team}",
                "iso_week": f"2026-W{week:02d}",
                "qualifying_workflow_count": 1,
                "non_demo_confirmed": "true",
            }
            for team in range(3)
            for week in range(20, 24)
        ],
    )
    _csv(
        tmp_path / "commercial-signals.csv",
        [
            {
                "dataset_version": version,
                "team_id": f"team-{team}",
                "wtp_status": "concrete",
                "defined_capability": "managed evidence memory",
                "price_or_budget_range": "100-200",
                "dated_next_step": "procurement review",
                "next_step_due_at": "2026-08-01",
                "consent_to_use_aggregate": "true",
            }
            for team in range(2)
        ],
    )
    names = [
        "questions.jsonl",
        "attempts.csv",
        "citations.csv",
        "weekly-usage.csv",
        "commercial-signals.csv",
    ]
    manifest = {
        "artifact_status": "frozen_private_dataset",
        "dataset_version": version,
        "artifact_sha256": {
            name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() for name in names
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_pilot_analysis_calculates_only_aggregate_frozen_gates(tmp_path):
    report = analyze_pilot(_dataset(tmp_path))

    assert report["metrics"]["eligible_real_questions"]["status"] == "pass"
    assert report["metrics"]["eligible_temporal_questions"]["status"] == "pass"
    assert report["metrics"]["citation_precision"]["value"] == 1
    assert report["metrics"]["useful_answer_rate"]["value"] == 1
    assert report["metrics"]["median_time_improvement"]["value"] == pytest.approx(0.6)
    assert report["metrics"]["weekly_active_teams"]["value"] == 3
    assert report["metrics"]["concrete_wtp_teams"]["value"] == 2
    assert report["hard_gates"]["security_qualification"] == "not_run_by_request"
    assert "question_text" not in json.dumps(report)


def test_pilot_analysis_rejects_tampered_frozen_artifact(tmp_path):
    directory = _dataset(tmp_path)
    (directory / "attempts.csv").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(PilotDataError, match="pilot_hash_mismatch_attempts"):
        analyze_pilot(directory)


def test_pilot_analysis_rejects_duplicate_eligible_question_ids(tmp_path):
    directory = _dataset(tmp_path)
    questions_path = directory / "questions.jsonl"
    first_question = questions_path.read_text(encoding="utf-8").splitlines()[0]
    questions_path.write_text(
        questions_path.read_text(encoding="utf-8") + first_question + "\n", encoding="utf-8"
    )
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_sha256"]["questions.jsonl"] = hashlib.sha256(
        questions_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PilotDataError, match="duplicate_question_id"):
        analyze_pilot(directory)
