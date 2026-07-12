from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__
from .models import AuditEvent, Decision, Evidence, IngestionJob, ModelRun, Source, SourceVersion

PORTABLE_EXPORT_SCHEMA = "proofline-portable-export-v1"
TERMINAL_INGESTION_STATES = {"succeeded", "failed", "dead_letter"}
PAYLOAD_KEYS = {
    "sources",
    "source_versions",
    "memories",
    "evidence",
    "model_runs",
    "audit_events",
    "ingestion_jobs",
}
MANIFEST_KEYS = {"schema", "created_at", "app_version", "payload_sha256", "counts"}
ITEM_KEYS = {
    "sources": {
        "id",
        "title",
        "kind",
        "uri",
        "identity_hash",
        "status",
        "created_at",
        "indexed_at",
        "current_version_id",
    },
    "source_versions": {
        "id",
        "source_id",
        "content_hash",
        "content",
        "version_number",
        "content_length",
        "status",
        "parser_version",
        "created_at",
    },
    "memories": {
        "id",
        "source_id",
        "source_version_id",
        "kind",
        "title",
        "statement",
        "rationale",
        "status",
        "confidence",
        "extraction_method",
        "model_run_id",
        "valid_from",
        "valid_to",
        "created_at",
        "updated_at",
    },
    "evidence": {
        "id",
        "memory_id",
        "source_id",
        "source_version_id",
        "quote",
        "quote_hash",
        "start_offset",
        "end_offset",
        "start_line",
        "end_line",
    },
    "model_runs": {
        "id",
        "provider_id",
        "model_id",
        "operation",
        "template_version",
        "input_hashes",
        "parent_run_id",
        "attempt_number",
        "repair_reason",
        "status",
        "validation_status",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "error_code",
        "created_at",
        "finished_at",
    },
    "audit_events": {
        "id",
        "actor",
        "action",
        "object_type",
        "object_id",
        "before",
        "after",
        "created_at",
    },
    "ingestion_jobs": {
        "id",
        "source_id",
        "source_version_id",
        "kind",
        "state",
        "stage",
        "attempts",
        "max_attempts",
        "error_code",
        "retryable",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
    },
}


class PortabilityError(ValueError):
    """A safe export error identified only by a non-content-bearing code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_portable_export(
    session: Session,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    sources = list(session.scalars(select(Source).order_by(Source.id)).all())
    versions = list(
        session.scalars(
            select(SourceVersion).order_by(
                SourceVersion.source_id,
                SourceVersion.version_number,
                SourceVersion.id,
            )
        ).all()
    )
    memories = list(session.scalars(select(Decision).order_by(Decision.id)).all())
    evidence = list(session.scalars(select(Evidence).order_by(Evidence.id)).all())
    model_runs = list(session.scalars(select(ModelRun).order_by(ModelRun.id)).all())
    known_source_ids = {source.id for source in sources}
    known_memory_ids = {memory.id for memory in memories}
    audit_events = [
        event
        for event in session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
        if (event.object_type == "source" and event.object_id in known_source_ids)
        or (event.object_type in {"memory", "decision"} and event.object_id in known_memory_ids)
    ]
    ingestion_jobs = list(
        session.scalars(
            select(IngestionJob)
            .where(IngestionJob.state.in_(TERMINAL_INGESTION_STATES))
            .order_by(IngestionJob.id)
        ).all()
    )
    payload: dict[str, Any] = {
        "sources": [
            {
                "id": item.id,
                "title": item.title,
                "kind": item.kind,
                "uri": item.uri,
                "identity_hash": item.content_hash,
                "status": item.status,
                "created_at": _iso(item.created_at),
                "indexed_at": _iso(item.indexed_at),
                "current_version_id": item.current_version_id,
            }
            for item in sources
        ],
        "source_versions": [
            {
                "id": item.id,
                "source_id": item.source_id,
                "content_hash": item.content_hash,
                "content": item.content,
                "version_number": item.version_number,
                "content_length": item.content_length,
                "status": item.status,
                "parser_version": item.parser_version,
                "created_at": _iso(item.created_at),
            }
            for item in versions
        ],
        "memories": [
            {
                "id": item.id,
                "source_id": item.source_id,
                "source_version_id": item.source_version_id,
                "kind": item.kind,
                "title": item.title,
                "statement": item.statement,
                "rationale": item.rationale,
                "status": item.status,
                "confidence": item.confidence,
                "extraction_method": item.extraction_method,
                "model_run_id": item.model_run_id,
                "valid_from": _iso(item.valid_from),
                "valid_to": _iso(item.valid_to),
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in memories
        ],
        "evidence": [
            {
                "id": item.id,
                "memory_id": item.decision_id,
                "source_id": item.source_id,
                "source_version_id": item.source_version_id,
                "quote": item.quote,
                "quote_hash": item.quote_hash,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
                "start_line": item.start_line,
                "end_line": item.end_line,
            }
            for item in evidence
        ],
        "model_runs": [
            {
                "id": item.id,
                "provider_id": item.provider_id,
                "model_id": item.model_id,
                "operation": item.operation,
                "template_version": item.template_version,
                "input_hashes": item.input_hashes,
                "parent_run_id": item.parent_run_id,
                "attempt_number": item.attempt_number,
                "repair_reason": item.repair_reason,
                "status": item.status,
                "validation_status": item.validation_status,
                "latency_ms": item.latency_ms,
                "prompt_tokens": item.prompt_tokens,
                "completion_tokens": item.completion_tokens,
                "error_code": item.error_code,
                "created_at": _iso(item.created_at),
                "finished_at": _iso(item.finished_at),
            }
            for item in model_runs
        ],
        "audit_events": [
            {
                "id": item.id,
                "actor": item.actor,
                "action": item.action,
                "object_type": item.object_type,
                "object_id": item.object_id,
                "before": item.before_json,
                "after": item.after_json,
                "created_at": _iso(item.created_at),
            }
            for item in audit_events
        ],
        "ingestion_jobs": [
            {
                "id": item.id,
                "source_id": item.source_id,
                "source_version_id": item.source_version_id,
                "kind": item.kind,
                "state": item.state,
                "stage": item.stage,
                "attempts": item.attempts,
                "max_attempts": item.max_attempts,
                "error_code": item.error_code,
                "retryable": item.retryable,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
                "started_at": _iso(item.started_at),
                "finished_at": _iso(item.finished_at),
            }
            for item in ingestion_jobs
        ],
    }
    generated_at = created_at or datetime.now(UTC)
    return {
        "manifest": {
            "schema": PORTABLE_EXPORT_SCHEMA,
            "created_at": _iso(generated_at),
            "app_version": __version__,
            "payload_sha256": payload_sha256(payload),
            "counts": {key: len(payload[key]) for key in sorted(PAYLOAD_KEYS)},
        },
        "payload": payload,
    }


def _require_mapping(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PortabilityError(code)
    return value


def _require_array(value: Any, code: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PortabilityError(code)
    return value


def _by_id(items: list[dict[str, Any]], code: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise PortabilityError(code)
        result[identifier] = item
    return result


def verify_portable_export(document: Any) -> dict[str, int]:
    root = _require_mapping(document, "invalid_structure")
    if set(root) != {"manifest", "payload"}:
        raise PortabilityError("invalid_structure")
    manifest = _require_mapping(root["manifest"], "invalid_manifest")
    payload = _require_mapping(root["payload"], "invalid_payload")
    if set(manifest) != MANIFEST_KEYS or set(payload) != PAYLOAD_KEYS:
        raise PortabilityError("unexpected_fields")
    if manifest.get("schema") != PORTABLE_EXPORT_SCHEMA:
        raise PortabilityError("unsupported_schema")
    if not isinstance(manifest.get("created_at"), str) or not isinstance(
        manifest.get("app_version"), str
    ):
        raise PortabilityError("invalid_manifest")
    expected_hash = manifest.get("payload_sha256")
    if not isinstance(expected_hash, str) or payload_sha256(payload) != expected_hash:
        raise PortabilityError("payload_hash_mismatch")

    arrays = {key: _require_array(payload[key], "invalid_payload") for key in PAYLOAD_KEYS}
    if any(set(item) != ITEM_KEYS[key] for key, items in arrays.items() for item in items):
        raise PortabilityError("unexpected_fields")
    counts = _require_mapping(manifest.get("counts"), "invalid_counts")
    expected_counts = {key: len(arrays[key]) for key in sorted(PAYLOAD_KEYS)}
    if counts != expected_counts:
        raise PortabilityError("count_mismatch")

    sources = _by_id(arrays["sources"], "invalid_source_id")
    versions = _by_id(arrays["source_versions"], "invalid_version_id")
    memories = _by_id(arrays["memories"], "invalid_memory_id")
    evidence = _by_id(arrays["evidence"], "invalid_evidence_id")
    model_runs = _by_id(arrays["model_runs"], "invalid_model_run_id")
    _by_id(arrays["audit_events"], "invalid_audit_id")
    _by_id(arrays["ingestion_jobs"], "invalid_job_id")

    version_numbers: dict[str, set[int]] = {source_id: set() for source_id in sources}
    for version in versions.values():
        source_id = version.get("source_id")
        content = version.get("content")
        if source_id not in sources or not isinstance(content, str):
            raise PortabilityError("invalid_version_reference")
        version_number = version.get("version_number")
        if (
            not isinstance(version_number, int)
            or isinstance(version_number, bool)
            or version_number < 1
            or version_number in version_numbers[source_id]
        ):
            raise PortabilityError("invalid_version_number")
        version_numbers[source_id].add(version_number)
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != version.get("content_hash"):
            raise PortabilityError("source_content_hash_mismatch")
        if version.get("content_length") != len(content):
            raise PortabilityError("source_content_length_mismatch")

    for source in sources.values():
        identity_hash = source.get("identity_hash")
        if (
            not isinstance(identity_hash, str)
            or len(identity_hash) != 64
            or any(value not in "0123456789abcdef" for value in identity_hash)
        ):
            raise PortabilityError("invalid_source_identity")
        current = versions.get(source.get("current_version_id"))
        if not current or current.get("source_id") != source["id"]:
            raise PortabilityError("invalid_current_version")
        if current.get("version_number") != max(version_numbers[source["id"]], default=0):
            raise PortabilityError("current_version_not_latest")

    for run in model_runs.values():
        parent_id = run.get("parent_run_id")
        if parent_id is not None and (parent_id not in model_runs or parent_id == run["id"]):
            raise PortabilityError("invalid_model_lineage")
        input_hashes = run.get("input_hashes")
        if not isinstance(input_hashes, list) or not all(
            isinstance(value, str) for value in input_hashes
        ):
            raise PortabilityError("invalid_model_metadata")
    for run_id in model_runs:
        visited: set[str] = set()
        cursor: str | None = run_id
        while cursor is not None:
            if cursor in visited:
                raise PortabilityError("invalid_model_lineage")
            visited.add(cursor)
            cursor = model_runs[cursor].get("parent_run_id")

    for memory in memories.values():
        version = versions.get(memory.get("source_version_id"))
        if memory.get("source_id") not in sources or not version:
            raise PortabilityError("invalid_memory_reference")
        if version.get("source_id") != memory.get("source_id"):
            raise PortabilityError("invalid_memory_reference")
        model_run_id = memory.get("model_run_id")
        if model_run_id is not None and model_run_id not in model_runs:
            raise PortabilityError("invalid_memory_model_reference")

    for item in evidence.values():
        memory = memories.get(item.get("memory_id"))
        version = versions.get(item.get("source_version_id"))
        if not memory or not version or item.get("source_id") not in sources:
            raise PortabilityError("invalid_evidence_reference")
        if (
            memory.get("source_id") != item.get("source_id")
            or memory.get("source_version_id") != item.get("source_version_id")
            or version.get("source_id") != item.get("source_id")
        ):
            raise PortabilityError("invalid_evidence_reference")
        start = item.get("start_offset")
        end = item.get("end_offset")
        quote = item.get("quote")
        content = version.get("content")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not isinstance(quote, str)
            or not isinstance(content, str)
            or start < 0
            or end <= start
            or end > len(content)
        ):
            raise PortabilityError("invalid_evidence_span")
        if content[start:end] != quote:
            raise PortabilityError("evidence_span_mismatch")
        if hashlib.sha256(quote.encode("utf-8")).hexdigest() != item.get("quote_hash"):
            raise PortabilityError("evidence_quote_hash_mismatch")
        expected_start_line = content.count("\n", 0, start) + 1
        expected_end_line = content.count("\n", 0, end - 1) + 1
        if (
            item.get("start_line") != expected_start_line
            or item.get("end_line") != expected_end_line
        ):
            raise PortabilityError("evidence_line_mismatch")

    evidence_counts = {memory_id: 0 for memory_id in memories}
    for item in evidence.values():
        evidence_counts[item["memory_id"]] += 1
    for memory in memories.values():
        if evidence_counts[memory["id"]] < 1:
            raise PortabilityError("memory_without_evidence")
        if memory.get("extraction_method") == "model" and memory.get("model_run_id") is None:
            raise PortabilityError("invalid_memory_model_reference")

    for event in arrays["audit_events"]:
        if not isinstance(event.get("before"), dict) or not isinstance(event.get("after"), dict):
            raise PortabilityError("invalid_audit_snapshot")
        object_type = event.get("object_type")
        object_id = event.get("object_id")
        if object_type == "source":
            valid = object_id in sources
        elif object_type in {"memory", "decision"}:
            valid = object_id in memories
        else:
            valid = False
        if not valid:
            raise PortabilityError("invalid_audit_reference")

    for job in arrays["ingestion_jobs"]:
        if job.get("state") not in TERMINAL_INGESTION_STATES:
            raise PortabilityError("invalid_ingestion_diagnostic")
        source_id = job.get("source_id")
        version_id = job.get("source_version_id")
        if source_id is not None and source_id not in sources:
            raise PortabilityError("invalid_job_reference")
        if version_id is not None:
            version = versions.get(version_id)
            if not version or (source_id is not None and version.get("source_id") != source_id):
                raise PortabilityError("invalid_job_reference")
    return expected_counts


def load_and_verify_export(path: Path) -> dict[str, int]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PortabilityError("export_unreadable") from exc
    return verify_portable_export(document)


def atomic_write_export(path: Path, document: dict[str, Any], *, force: bool = False) -> None:
    path = Path(os.path.abspath(path.expanduser()))
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(document) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise PortabilityError("output_exists") from exc
            temporary.unlink()
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
