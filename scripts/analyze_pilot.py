#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path


class PilotDataError(ValueError):
    pass


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise PilotDataError(f"questions_jsonl_invalid_line_{line_number}") from exc
    return records


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _true(value: str | bool | None) -> bool:
    return value is True or (isinstance(value, str) and value.casefold() == "true")


def _status(value: float | int | None, threshold: float | int) -> str:
    return "pass" if value is not None and value >= threshold else "fail"


def analyze_pilot(directory: Path) -> dict:
    paths = {
        "questions": directory / "questions.jsonl",
        "attempts": directory / "attempts.csv",
        "citations": directory / "citations.csv",
        "weekly_usage": directory / "weekly-usage.csv",
        "commercial_signals": directory / "commercial-signals.csv",
    }
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file() or any(not path.is_file() for path in paths.values()):
        raise PilotDataError("pilot_dataset_incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_status") != "frozen_private_dataset":
        raise PilotDataError("pilot_manifest_not_frozen")
    dataset_version = manifest.get("dataset_version")
    if not dataset_version:
        raise PilotDataError("pilot_dataset_version_missing")
    expected_hashes = manifest.get("artifact_sha256", {})
    for name, path in paths.items():
        if expected_hashes.get(path.name) != _sha256(path):
            raise PilotDataError(f"pilot_hash_mismatch_{name}")

    questions = _read_jsonl(paths["questions"])
    attempts = _read_csv(paths["attempts"])
    citations = _read_csv(paths["citations"])
    usage = _read_csv(paths["weekly_usage"])
    commercial = _read_csv(paths["commercial_signals"])
    if any(question.get("record_status") == "synthetic_example" for question in questions):
        raise PilotDataError("synthetic_question_present")
    if any(
        str(row.get("dataset_version")) != dataset_version
        for rows in [attempts, citations, usage, commercial]
        for row in rows
    ):
        raise PilotDataError("dataset_version_mismatch")

    eligible_records = [q for q in questions if q.get("record_status") == "eligible"]
    if any(not question.get("question_id") for question in eligible_records):
        raise PilotDataError("missing_question_id")
    eligible = {q["question_id"]: q for q in eligible_records}
    if len(eligible_records) != len(eligible):
        raise PilotDataError("duplicate_question_id")
    attempt_ids: set[str] = set()
    eligible_attempts: list[dict[str, str]] = []
    for attempt in attempts:
        attempt_id = attempt.get("attempt_id", "")
        if not attempt_id or attempt_id in attempt_ids:
            raise PilotDataError("duplicate_or_missing_attempt_id")
        attempt_ids.add(attempt_id)
        if attempt.get("question_id") not in eligible:
            if not attempt.get("exclusion_reason"):
                raise PilotDataError("attempt_question_not_eligible")
            continue
        eligible_attempts.append(attempt)

    citations_by_attempt: dict[str, list[dict[str, str]]] = {
        attempt_id: [] for attempt_id in attempt_ids
    }
    citation_ids: set[str] = set()
    for citation in citations:
        citation_id = citation.get("citation_judgment_id", "")
        attempt_id = citation.get("attempt_id", "")
        if not citation_id or citation_id in citation_ids:
            raise PilotDataError("duplicate_or_missing_citation_judgment_id")
        if attempt_id not in attempt_ids:
            raise PilotDataError("citation_attempt_missing")
        citation_ids.add(citation_id)
        citations_by_attempt[attempt_id].append(citation)

    supported = 0
    citation_complete = True
    for citation in citations:
        judgment = (
            citation.get("adjudicated_judgment")
            if citation.get("adjudication_status") == "adjudicated"
            else citation.get("citation_judgment")
        )
        valid = (
            judgment == "supported"
            and _true(citation.get("resolves_exact_span"))
            and _true(citation.get("authorized_source"))
        )
        supported += int(valid)
        citation_complete &= (
            judgment in {"supported", "unsupported"}
            and _true(citation.get("resolves_exact_span"))
            and _true(citation.get("authorized_source"))
        )
    citation_precision = supported / len(citations) if citations else None

    judged_attempts = []
    useful_count = 0
    paired_times: list[tuple[float, float]] = []
    for attempt in eligible_attempts:
        related = citations_by_attempt[attempt["attempt_id"]]
        citation_bad = any(
            (
                row.get("adjudicated_judgment")
                if row.get("adjudication_status") == "adjudicated"
                else row.get("citation_judgment")
            )
            != "supported"
            for row in related
        )
        if attempt.get("useful_adjudicated") in {"true", "false"}:
            judged_attempts.append(attempt)
            useful_count += int(_true(attempt["useful_adjudicated"]) and not citation_bad)
        if (
            attempt.get("baseline_completion_status") == "completed"
            and attempt.get("proofline_completion_status") == "completed"
        ):
            try:
                paired_times.append(
                    (float(attempt["baseline_seconds"]), float(attempt["proofline_seconds"]))
                )
            except (TypeError, ValueError) as exc:
                raise PilotDataError("paired_time_invalid") from exc
    useful_rate = useful_count / len(judged_attempts) if judged_attempts else None
    baseline_median = statistics.median(pair[0] for pair in paired_times) if paired_times else None
    proofline_median = statistics.median(pair[1] for pair in paired_times) if paired_times else None
    time_improvement = (
        1 - proofline_median / baseline_median
        if baseline_median and proofline_median is not None
        else None
    )

    weeks = sorted({row["iso_week"] for row in usage})
    final_weeks = set(weeks[-4:]) if len(weeks) >= 4 else set()
    qualifying_by_team: dict[str, set[str]] = {}
    for row in usage:
        if (
            row["iso_week"] in final_weeks
            and _true(row.get("non_demo_confirmed"))
            and int(row.get("qualifying_workflow_count") or 0) > 0
        ):
            qualifying_by_team.setdefault(row["team_id"], set()).add(row["iso_week"])
    weekly_active_teams = sum(len(team_weeks) >= 3 for team_weeks in qualifying_by_team.values())
    wtp_teams = {
        row["team_id"]
        for row in commercial
        if row.get("wtp_status") == "concrete"
        and row.get("defined_capability")
        and row.get("price_or_budget_range")
        and row.get("dated_next_step")
        and row.get("next_step_due_at")
        and _true(row.get("consent_to_use_aggregate"))
    }
    temporal_count = sum(_true(question.get("temporal_required")) for question in eligible.values())
    metrics = {
        "eligible_real_questions": {
            "value": len(eligible),
            "threshold": 25,
            "status": _status(len(eligible), 25),
        },
        "eligible_temporal_questions": {
            "value": temporal_count,
            "threshold": 10,
            "status": _status(temporal_count, 10),
        },
        "citation_precision": {
            "numerator": supported,
            "denominator": len(citations),
            "value": citation_precision,
            "threshold": 0.9,
            "status": _status(citation_precision, 0.9),
        },
        "useful_answer_rate": {
            "numerator": useful_count,
            "denominator": len(judged_attempts),
            "value": useful_rate,
            "threshold": 0.65,
            "status": _status(useful_rate, 0.65),
        },
        "median_time_improvement": {
            "baseline_median_seconds": baseline_median,
            "proofline_median_seconds": proofline_median,
            "value": time_improvement,
            "threshold": 0.5,
            "status": _status(time_improvement, 0.5),
        },
        "weekly_active_teams": {
            "value": weekly_active_teams,
            "threshold": 3,
            "status": _status(weekly_active_teams, 3) if final_weeks else "open",
        },
        "concrete_wtp_teams": {
            "value": len(wtp_teams),
            "threshold": 2,
            "status": _status(len(wtp_teams), 2),
        },
    }
    return {
        "schema_version": "pilot-gate-review-v1",
        "artifact_status": "aggregate_analysis_unsigned",
        "dataset_version": dataset_version,
        "artifact_sha256": {path.name: _sha256(path) for path in paths.values()},
        "calculated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "hard_gates": {
            "all_emitted_citations_judged_and_resolved": "pass"
            if citation_complete and citations
            else "fail",
            "declared_platform_matrix_has_successful_receipts": "open",
            "security_qualification": "not_run_by_request",
        },
        "decision": "awaiting_owner_signoff",
        "qualification": (
            "Aggregate calculation only; not pilot evidence until owners sign the frozen "
            "private dataset review."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_pilot(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
