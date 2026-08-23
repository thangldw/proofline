import csv
import hashlib
import json
import runpy
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
namespace = runpy.run_path(ROOT / "scripts/freeze_pilot_dataset.py")
freeze_pilot_dataset = namespace["freeze_pilot_dataset"]
PilotFreezeError = namespace["PilotFreezeError"]

REQUIRED_FILES = (
    "questions.jsonl",
    "attempts.csv",
    "citations.csv",
    "weekly-usage.csv",
    "commercial-signals.csv",
)


def _csv(path: Path, row: dict[str, str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def _unfrozen_dataset(tmp_path: Path) -> Path:
    version = "private-pilot-v1"
    (tmp_path / "questions.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "pilot-question-v1",
                "record_status": "eligible",
                "question_id": "question-1",
                "temporal_required": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _csv(tmp_path / "attempts.csv", {"dataset_version": version, "attempt_id": "a-1"})
    _csv(
        tmp_path / "citations.csv",
        {"dataset_version": version, "citation_judgment_id": "c-1"},
    )
    _csv(
        tmp_path / "weekly-usage.csv",
        {"dataset_version": version, "team_id": "team-1", "iso_week": "2026-W34"},
    )
    _csv(
        tmp_path / "commercial-signals.csv",
        {"dataset_version": version, "team_id": "team-1", "signal_id": "signal-1"},
    )
    return tmp_path


def test_freezer_writes_deterministic_private_manifest(tmp_path):
    directory = _unfrozen_dataset(tmp_path)

    manifest = freeze_pilot_dataset(directory, "private-pilot-v1")

    assert manifest == {
        "schema_version": "pilot-manifest-v1",
        "artifact_status": "frozen_private_dataset",
        "dataset_version": "private-pilot-v1",
        "artifact_sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in REQUIRED_FILES
        },
    }
    manifest_path = directory / "manifest.json"
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    first_bytes = manifest_path.read_bytes()
    assert freeze_pilot_dataset(directory, "private-pilot-v1", force=True) == manifest
    assert manifest_path.read_bytes() == first_bytes


def test_freezer_rejects_missing_input(tmp_path):
    directory = _unfrozen_dataset(tmp_path)
    (directory / "citations.csv").unlink()

    with pytest.raises(PilotFreezeError, match="pilot_file_missing_citations"):
        freeze_pilot_dataset(directory, "private-pilot-v1")


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_freezer_rejects_empty_input(tmp_path, name):
    directory = _unfrozen_dataset(tmp_path)
    (directory / name).write_text("", encoding="utf-8")

    code = name.removesuffix(".jsonl").removesuffix(".csv").replace("-", "_")
    with pytest.raises(PilotFreezeError, match=f"pilot_file_empty_{code}"):
        freeze_pilot_dataset(directory, "private-pilot-v1")


@pytest.mark.parametrize(
    ("name", "content"),
    [
        (
            "questions.jsonl",
            '{"record_status":"synthetic_example","question_id":"synthetic-1"}\n',
        ),
        ("attempts.csv", "dataset_version,attempt_id\nprivate-pilot-v1,blank_template\n"),
    ],
)
def test_freezer_rejects_synthetic_or_template_markers(tmp_path, name, content):
    directory = _unfrozen_dataset(tmp_path)
    (directory / name).write_text(content, encoding="utf-8")

    with pytest.raises(PilotFreezeError, match="pilot_non_real_marker_present"):
        freeze_pilot_dataset(directory, "private-pilot-v1")


def test_freezer_refuses_manifest_overwrite_without_force(tmp_path):
    directory = _unfrozen_dataset(tmp_path)
    freeze_pilot_dataset(directory, "private-pilot-v1")

    with pytest.raises(PilotFreezeError, match="pilot_manifest_exists"):
        freeze_pilot_dataset(directory, "private-pilot-v1")
