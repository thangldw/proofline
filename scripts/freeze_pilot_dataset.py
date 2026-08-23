#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

FILES = {
    "questions": "questions.jsonl",
    "attempts": "attempts.csv",
    "citations": "citations.csv",
    "weekly_usage": "weekly-usage.csv",
    "commercial_signals": "commercial-signals.csv",
}
VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
NON_REAL_VALUES = {"blank_template", "synthetic_example"}


class PilotFreezeError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _contains_non_real_marker(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_non_real_marker(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_non_real_marker(item) for item in value)
    if not isinstance(value, str):
        return False
    normalized = value.strip().casefold()
    return (
        normalized in NON_REAL_VALUES
        or normalized.startswith("synthetic-")
        or normalized.startswith("synthetic_")
    )


def _read_bytes(path: Path, name: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PilotFreezeError(f"pilot_file_missing_{name}")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise PilotFreezeError(f"pilot_file_unreadable_{name}") from exc
    if not content.strip():
        raise PilotFreezeError(f"pilot_file_empty_{name}")
    return content


def _validate_questions(content: bytes) -> None:
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise PilotFreezeError("pilot_questions_invalid") from exc
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PilotFreezeError("pilot_questions_invalid") from exc
        if not isinstance(record, dict):
            raise PilotFreezeError("pilot_questions_invalid")
        records.append(record)
    if not records:
        raise PilotFreezeError("pilot_file_empty_questions")
    if any(_contains_non_real_marker(record) for record in records):
        raise PilotFreezeError("pilot_non_real_marker_present")


def _validate_csv(content: bytes, name: str, dataset_version: str) -> None:
    try:
        text = content.decode("utf-8-sig")
        rows = list(csv.DictReader(text.splitlines()))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise PilotFreezeError(f"pilot_csv_invalid_{name}") from exc
    if not rows:
        raise PilotFreezeError(f"pilot_file_empty_{name}")
    if any(_contains_non_real_marker(row) for row in rows):
        raise PilotFreezeError("pilot_non_real_marker_present")
    if any(row.get("dataset_version") != dataset_version for row in rows):
        raise PilotFreezeError(f"pilot_dataset_version_mismatch_{name}")


def _atomic_write_manifest(path: Path, document: dict[str, Any], *, force: bool) -> None:
    data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise PilotFreezeError("pilot_manifest_exists") from exc
            temporary.unlink()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def freeze_pilot_dataset(
    directory: Path, dataset_version: str, *, force: bool = False
) -> dict[str, Any]:
    if not VERSION_PATTERN.fullmatch(dataset_version):
        raise PilotFreezeError("pilot_dataset_version_invalid")
    directory = directory.resolve()
    contents: dict[str, bytes] = {}
    for name, filename in FILES.items():
        contents[name] = _read_bytes(directory / filename, name)

    _validate_questions(contents["questions"])
    for name in ("attempts", "citations", "weekly_usage", "commercial_signals"):
        _validate_csv(contents[name], name, dataset_version)

    artifact_sha256 = {
        filename: hashlib.sha256(contents[name]).hexdigest() for name, filename in FILES.items()
    }
    for name, filename in FILES.items():
        if (
            hashlib.sha256(_read_bytes(directory / filename, name)).hexdigest()
            != artifact_sha256[filename]
        ):
            raise PilotFreezeError("pilot_dataset_changed_during_freeze")

    manifest = {
        "schema_version": "pilot-manifest-v1",
        "artifact_status": "frozen_private_dataset",
        "dataset_version": dataset_version,
        "artifact_sha256": artifact_sha256,
    }
    _atomic_write_manifest(directory / "manifest.json", manifest, force=force)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze a real private pilot dataset without printing its contents."
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        manifest = freeze_pilot_dataset(args.directory, args.dataset_version, force=args.force)
    except PilotFreezeError as exc:
        raise SystemExit(f"pilot freeze failed: {exc.code}") from exc
    print(
        json.dumps(
            {
                "valid": True,
                "artifact_status": manifest["artifact_status"],
                "dataset_version": manifest["dataset_version"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
