from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__
from .ingestion import chunk_markdown
from .models import (
    DEFAULT_WORKSPACE_ID,
    ActionProposal,
    AuditEvent,
    Chunk,
    Decision,
    Evidence,
    IngestionJob,
    ModelRun,
    ProposalCitation,
    Source,
    SourceVersion,
    StudioArtifact,
    StudioCitation,
    StudyCard,
    StudyReview,
    Workspace,
)

PORTABLE_EXPORT_SCHEMA = "proofline-portable-export-v2"
LEGACY_PORTABLE_EXPORT_SCHEMA = "proofline-portable-export-v1"
TERMINAL_INGESTION_STATES = {"succeeded", "failed", "dead_letter"}
SOURCE_KINDS = {"markdown", "text", "note", "git_file", "git_commit"}
SOURCE_STATUSES = {"indexed"}
MEMORY_KINDS = {"decision", "assumption", "constraint", "alternative"}
MEMORY_STATUSES = {"candidate", "active", "accepted", "rejected", "obsolete"}
EXTRACTION_METHODS = {"deterministic", "model"}
MODEL_OPERATIONS = {"generate", "embed"}
MODEL_RUN_STATUSES = {"running", "succeeded", "failed"}
MODEL_VALIDATION_STATUSES = {
    "not_requested",
    "valid",
    "invalid",
    "grounding_invalid",
}
STUDY_STATES = {"new", "learning", "review", "superseded"}
STUDY_RATINGS = {"again", "hard", "good", "easy"}
PROPOSAL_STATUSES = {"candidate", "accepted", "rejected"}
STUDIO_KINDS = {
    "audio_overview",
    "presentation",
    "video_overview",
    "mind_map",
    "report",
    "flashcards",
    "quiz",
    "infographic",
    "data_table",
}
INGESTION_STAGES = {"accepted", "indexing", "ready", "parse", "failed"}
MAX_CONTENT_LENGTH = 5_000_000
MAX_COUNTER = 2**63 - 1
MAX_EXPORT_BYTES = 256 * 1024 * 1024
PAYLOAD_KEYS = {
    "workspaces",
    "sources",
    "source_versions",
    "chunks",
    "memories",
    "evidence",
    "model_runs",
    "audit_events",
    "ingestion_jobs",
    "study_cards",
    "study_reviews",
    "action_proposals",
    "proposal_citations",
    "studio_artifacts",
    "studio_citations",
}
MANIFEST_KEYS = {"schema", "created_at", "app_version", "payload_sha256", "counts"}
LEGACY_PAYLOAD_KEYS = {
    "sources",
    "source_versions",
    "memories",
    "evidence",
    "model_runs",
    "audit_events",
    "ingestion_jobs",
}
ITEM_KEYS = {
    "workspaces": {"id", "slug", "title", "created_at"},
    "sources": {
        "id",
        "workspace_id",
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
    "chunks": {
        "id",
        "source_id",
        "source_version_id",
        "ordinal",
        "content",
        "start_offset",
        "end_offset",
        "start_line",
        "end_line",
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
        "workspace_id",
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
    "study_cards": {
        "id",
        "workspace_id",
        "source_id",
        "source_version_id",
        "question",
        "answer",
        "quote_hash",
        "start_offset",
        "end_offset",
        "start_line",
        "end_line",
        "state",
        "interval_days",
        "due_at",
        "created_at",
        "updated_at",
    },
    "study_reviews": {
        "id",
        "card_id",
        "rating",
        "previous_interval_days",
        "next_interval_days",
        "reviewed_at",
    },
    "action_proposals": {
        "id",
        "workspace_id",
        "goal",
        "body",
        "status",
        "model_run_id",
        "created_at",
        "updated_at",
    },
    "proposal_citations": {
        "id",
        "proposal_id",
        "source_id",
        "source_version_id",
        "chunk_id",
        "source_title",
        "quote",
        "quote_hash",
        "start_offset",
        "end_offset",
        "start_line",
        "end_line",
    },
    "studio_artifacts": {
        "id",
        "workspace_id",
        "source_id",
        "source_version_id",
        "kind",
        "title",
        "content",
        "status",
        "generation_method",
        "created_at",
        "updated_at",
    },
    "studio_citations": {
        "id",
        "artifact_id",
        "source_id",
        "source_version_id",
        "ordinal",
        "quote",
        "quote_hash",
        "start_offset",
        "end_offset",
        "start_line",
        "end_line",
    },
}
LEGACY_ITEM_KEYS = {key: set(ITEM_KEYS[key]) for key in LEGACY_PAYLOAD_KEYS}
LEGACY_ITEM_KEYS["sources"].remove("workspace_id")
LEGACY_ITEM_KEYS["audit_events"].remove("workspace_id")


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


def normalize_portable_export(document: Any) -> Any:
    """Upgrade a verified v1 shape in memory without mutating the caller's document."""
    if not isinstance(document, dict):
        return document
    manifest = document.get("manifest")
    payload = document.get("payload")
    if not isinstance(manifest, dict) or manifest.get("schema") != LEGACY_PORTABLE_EXPORT_SCHEMA:
        return document
    if (
        set(document) != {"manifest", "payload"}
        or set(manifest) != MANIFEST_KEYS
        or not isinstance(payload, dict)
        or set(payload) != LEGACY_PAYLOAD_KEYS
    ):
        raise PortabilityError("unexpected_fields")
    expected_hash = manifest.get("payload_sha256")
    if not isinstance(expected_hash, str) or payload_sha256(payload) != expected_hash:
        raise PortabilityError("payload_hash_mismatch")
    if any(
        not isinstance(items, list)
        or any(not isinstance(item, dict) or set(item) != LEGACY_ITEM_KEYS[key] for item in items)
        for key, items in payload.items()
    ):
        raise PortabilityError("unexpected_fields")

    upgraded = copy.deepcopy(document)
    upgraded_payload = upgraded["payload"]
    upgraded_payload["workspaces"] = [
        {
            "id": DEFAULT_WORKSPACE_ID,
            "slug": "local",
            "title": "Local workspace",
            "created_at": manifest["created_at"],
        }
    ]
    for source in upgraded_payload["sources"]:
        source["workspace_id"] = DEFAULT_WORKSPACE_ID
    for event in upgraded_payload["audit_events"]:
        event["workspace_id"] = DEFAULT_WORKSPACE_ID

    chunks: list[dict[str, Any]] = []
    for version in upgraded_payload["source_versions"]:
        for ordinal, span in enumerate(chunk_markdown(version["content"])):
            chunk_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"proofline:portable-v1-chunk:{version['id']}:{ordinal}",
                )
            )
            chunks.append(
                {
                    "id": chunk_id,
                    "source_id": version["source_id"],
                    "source_version_id": version["id"],
                    "ordinal": ordinal,
                    "content": span.text,
                    "start_offset": span.start_offset,
                    "end_offset": span.end_offset,
                    "start_line": span.start_line,
                    "end_line": span.end_line,
                }
            )
    upgraded_payload["chunks"] = sorted(chunks, key=lambda item: item["id"])
    for key in PAYLOAD_KEYS - LEGACY_PAYLOAD_KEYS - {"workspaces", "chunks"}:
        upgraded_payload[key] = []
    upgraded["manifest"]["schema"] = PORTABLE_EXPORT_SCHEMA
    upgraded["manifest"]["payload_sha256"] = payload_sha256(upgraded_payload)
    upgraded["manifest"]["counts"] = {
        key: len(upgraded_payload[key]) for key in sorted(PAYLOAD_KEYS)
    }
    return upgraded


def build_portable_export(
    session: Session,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    workspaces = list(session.scalars(select(Workspace).order_by(Workspace.id)).all())
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
    chunks = list(session.scalars(select(Chunk).order_by(Chunk.id)).all())
    memories = list(session.scalars(select(Decision).order_by(Decision.id)).all())
    evidence = list(session.scalars(select(Evidence).order_by(Evidence.id)).all())
    model_runs = list(session.scalars(select(ModelRun).order_by(ModelRun.id)).all())
    known_source_ids = {source.id for source in sources}
    known_memory_ids = {memory.id for memory in memories}
    known_proposal_ids = set(session.scalars(select(ActionProposal.id)).all())
    audit_events = [
        event
        for event in session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
        if (event.object_type == "source" and event.object_id in known_source_ids)
        or (event.object_type in {"memory", "decision"} and event.object_id in known_memory_ids)
        or (event.object_type == "action_proposal" and event.object_id in known_proposal_ids)
    ]
    ingestion_jobs = list(
        session.scalars(
            select(IngestionJob)
            .where(IngestionJob.state.in_(TERMINAL_INGESTION_STATES))
            .order_by(IngestionJob.id)
        ).all()
    )
    study_cards = list(session.scalars(select(StudyCard).order_by(StudyCard.id)).all())
    study_reviews = list(session.scalars(select(StudyReview).order_by(StudyReview.id)).all())
    action_proposals = list(
        session.scalars(select(ActionProposal).order_by(ActionProposal.id)).all()
    )
    proposal_citations = list(
        session.scalars(select(ProposalCitation).order_by(ProposalCitation.id)).all()
    )
    studio_artifacts = list(
        session.scalars(select(StudioArtifact).order_by(StudioArtifact.id)).all()
    )
    studio_citations = list(
        session.scalars(select(StudioCitation).order_by(StudioCitation.id)).all()
    )
    payload: dict[str, Any] = {
        "workspaces": [
            {
                "id": item.id,
                "slug": item.slug,
                "title": item.title,
                "created_at": _iso(item.created_at),
            }
            for item in workspaces
        ],
        "sources": [
            {
                "id": item.id,
                "workspace_id": item.workspace_id,
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
        "chunks": [
            {
                "id": item.id,
                "source_id": item.source_id,
                "source_version_id": item.source_version_id,
                "ordinal": item.ordinal,
                "content": item.content,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
                "start_line": item.start_line,
                "end_line": item.end_line,
            }
            for item in chunks
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
                "workspace_id": item.workspace_id,
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
        "study_cards": [
            {
                "id": item.id,
                "workspace_id": item.workspace_id,
                "source_id": item.source_id,
                "source_version_id": item.source_version_id,
                "question": item.question,
                "answer": item.answer,
                "quote_hash": item.quote_hash,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "state": item.state,
                "interval_days": item.interval_days,
                "due_at": _iso(item.due_at),
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in study_cards
        ],
        "study_reviews": [
            {
                "id": item.id,
                "card_id": item.card_id,
                "rating": item.rating,
                "previous_interval_days": item.previous_interval_days,
                "next_interval_days": item.next_interval_days,
                "reviewed_at": _iso(item.reviewed_at),
            }
            for item in study_reviews
        ],
        "action_proposals": [
            {
                "id": item.id,
                "workspace_id": item.workspace_id,
                "goal": item.goal,
                "body": item.body,
                "status": item.status,
                "model_run_id": item.model_run_id,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in action_proposals
        ],
        "proposal_citations": [
            {
                "id": item.id,
                "proposal_id": item.proposal_id,
                "source_id": item.source_id,
                "source_version_id": item.source_version_id,
                "chunk_id": item.chunk_id,
                "source_title": item.source_title,
                "quote": item.quote,
                "quote_hash": item.quote_hash,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
                "start_line": item.start_line,
                "end_line": item.end_line,
            }
            for item in proposal_citations
        ],
        "studio_artifacts": [
            {
                "id": item.id,
                "workspace_id": item.workspace_id,
                "source_id": item.source_id,
                "source_version_id": item.source_version_id,
                "kind": item.kind,
                "title": item.title,
                "content": item.content_json,
                "status": item.status,
                "generation_method": item.generation_method,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in studio_artifacts
        ],
        "studio_citations": [
            {
                "id": item.id,
                "artifact_id": item.artifact_id,
                "source_id": item.source_id,
                "source_version_id": item.source_version_id,
                "ordinal": item.ordinal,
                "quote": item.quote,
                "quote_hash": item.quote_hash,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
                "start_line": item.start_line,
                "end_line": item.end_line,
            }
            for item in studio_citations
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
        if (
            not isinstance(identifier, str)
            or not identifier
            or len(identifier) > 36
            or identifier in result
        ):
            raise PortabilityError(code)
        result[identifier] = item
    return result


def _require_string(
    value: Any,
    code: str,
    *,
    max_length: int,
    nullable: bool = False,
    allow_empty: bool = False,
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or (not allow_empty and not value) or len(value) > max_length:
        raise PortabilityError(code)
    return value


def _require_enum(value: Any, allowed: set[str], code: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or value not in allowed:
        raise PortabilityError(code)


def _require_integer(
    value: Any,
    code: str,
    *,
    minimum: int = 0,
    maximum: int = MAX_COUNTER,
    nullable: bool = False,
) -> int | None:
    if value is None and nullable:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum or value > maximum:
        raise PortabilityError(code)
    return value


def _require_number(
    value: Any,
    code: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if (
        not isinstance(value, float)
        or not math.isfinite(value)
        or value < minimum
        or value > maximum
        or (value == 0 and math.copysign(1, value) < 0)
    ):
        raise PortabilityError(code)
    return float(value)


def _require_datetime(value: Any, code: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or len(value) > 64:
        raise PortabilityError(code)
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, OverflowError) as exc:
        raise PortabilityError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PortabilityError(code)
    if _iso(parsed) != value:
        raise PortabilityError(code)
    return parsed


def _require_canonical_order(arrays: dict[str, list[dict[str, Any]]]) -> None:
    expected = {
        "sources": sorted(arrays["sources"], key=lambda item: item["id"]),
        "source_versions": sorted(
            arrays["source_versions"],
            key=lambda item: (item["source_id"], item["version_number"], item["id"]),
        ),
    }
    for key in PAYLOAD_KEYS - {"sources", "source_versions"}:
        expected[key] = sorted(arrays[key], key=lambda item: item["id"])
    if any(arrays[key] != expected[key] for key in PAYLOAD_KEYS):
        raise PortabilityError("noncanonical_order")


def _require_hash(value: Any, code: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PortabilityError(code)


def _require_id(value: Any, code: str, *, nullable: bool = False) -> None:
    _require_string(value, code, max_length=36, nullable=nullable)


def _require_json_value(value: Any, code: str, *, depth: int = 0) -> None:
    if depth > 20:
        raise PortabilityError(code)
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if abs(value) > MAX_COUNTER:
            raise PortabilityError(code)
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PortabilityError(code)
        return
    if isinstance(value, list):
        if len(value) > 10_000:
            raise PortabilityError(code)
        for item in value:
            _require_json_value(item, code, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 10_000 or not all(isinstance(key, str) for key in value):
            raise PortabilityError(code)
        for item in value.values():
            _require_json_value(item, code, depth=depth + 1)
        return
    raise PortabilityError(code)


def _validate_scalar_fields(
    manifest: dict[str, Any], arrays: dict[str, list[dict[str, Any]]]
) -> None:
    _require_datetime(manifest["created_at"], "invalid_manifest_datetime")
    _require_string(manifest["app_version"], "invalid_manifest", max_length=50)
    _require_hash(manifest["payload_sha256"], "invalid_manifest_hash")

    for workspace in arrays["workspaces"]:
        _require_string(workspace["slug"], "invalid_workspace_field", max_length=80)
        _require_string(workspace["title"], "invalid_workspace_field", max_length=200)
        _require_datetime(workspace["created_at"], "invalid_workspace_datetime")

    for source in arrays["sources"]:
        _require_id(source["workspace_id"], "invalid_source_workspace")
        _require_string(source["title"], "invalid_source_field", max_length=300)
        _require_enum(source["kind"], SOURCE_KINDS, "invalid_source_kind")
        _require_string(
            source["uri"],
            "invalid_source_field",
            # Schema v1 predates the 4 KiB write-boundary limit; keep old exports restorable.
            max_length=MAX_CONTENT_LENGTH,
            nullable=True,
            allow_empty=True,
        )
        _require_hash(source["identity_hash"], "invalid_source_identity")
        _require_enum(source["status"], SOURCE_STATUSES, "invalid_source_status")
        _require_datetime(source["created_at"], "invalid_source_datetime")
        _require_datetime(source["indexed_at"], "invalid_source_datetime")
        _require_id(source["current_version_id"], "invalid_current_version")

    for version in arrays["source_versions"]:
        _require_id(version["source_id"], "invalid_version_reference")
        _require_hash(version["content_hash"], "invalid_version_hash")
        _require_string(
            version["content"],
            "invalid_version_content",
            max_length=MAX_CONTENT_LENGTH,
            allow_empty=True,
        )
        _require_integer(version["version_number"], "invalid_version_number", minimum=1)
        _require_integer(
            version["content_length"],
            "invalid_version_content_length",
            maximum=MAX_CONTENT_LENGTH,
        )
        _require_enum(version["status"], SOURCE_STATUSES, "invalid_version_status")
        _require_string(version["parser_version"], "invalid_version_field", max_length=30)
        _require_datetime(version["created_at"], "invalid_version_datetime")

    for chunk in arrays["chunks"]:
        _require_id(chunk["source_id"], "invalid_chunk_reference")
        _require_id(chunk["source_version_id"], "invalid_chunk_reference")
        _require_integer(chunk["ordinal"], "invalid_chunk_span")
        _require_string(chunk["content"], "invalid_chunk_span", max_length=MAX_CONTENT_LENGTH)
        for field in ("start_offset", "end_offset"):
            _require_integer(chunk[field], "invalid_chunk_span", maximum=MAX_CONTENT_LENGTH)
        for field in ("start_line", "end_line"):
            _require_integer(chunk[field], "invalid_chunk_line", minimum=1)

    for memory in arrays["memories"]:
        _require_id(memory["source_id"], "invalid_memory_reference")
        _require_id(memory["source_version_id"], "invalid_memory_reference")
        _require_enum(memory["kind"], MEMORY_KINDS, "invalid_memory_kind")
        _require_string(memory["title"], "invalid_memory_field", max_length=300)
        _require_string(memory["statement"], "invalid_memory_field", max_length=MAX_CONTENT_LENGTH)
        _require_string(
            memory["rationale"],
            "invalid_memory_field",
            max_length=MAX_CONTENT_LENGTH,
            nullable=True,
            allow_empty=True,
        )
        _require_enum(memory["status"], MEMORY_STATUSES, "invalid_memory_status")
        _require_number(memory["confidence"], "invalid_memory_confidence", minimum=0, maximum=1)
        _require_enum(memory["extraction_method"], EXTRACTION_METHODS, "invalid_extraction_method")
        _require_id(memory["model_run_id"], "invalid_memory_model_reference", nullable=True)
        valid_from = _require_datetime(
            memory["valid_from"], "invalid_memory_datetime", nullable=True
        )
        valid_to = _require_datetime(memory["valid_to"], "invalid_memory_datetime", nullable=True)
        if valid_from is not None and valid_to is not None and valid_from > valid_to:
            raise PortabilityError("invalid_memory_validity_range")
        _require_datetime(memory["created_at"], "invalid_memory_datetime")
        _require_datetime(memory["updated_at"], "invalid_memory_datetime")

    for item in arrays["evidence"]:
        for field in ("memory_id", "source_id", "source_version_id"):
            _require_id(item[field], "invalid_evidence_reference")
        _require_string(item["quote"], "invalid_evidence_span", max_length=MAX_CONTENT_LENGTH)
        _require_hash(item["quote_hash"], "invalid_evidence_quote_hash")
        for field in ("start_offset", "end_offset"):
            _require_integer(item[field], "invalid_evidence_span", maximum=MAX_CONTENT_LENGTH)
        for field in ("start_line", "end_line"):
            _require_integer(item[field], "invalid_evidence_line", minimum=1)

    for run in arrays["model_runs"]:
        _require_string(run["provider_id"], "invalid_model_metadata", max_length=100)
        _require_string(run["model_id"], "invalid_model_metadata", max_length=200)
        _require_enum(run["operation"], MODEL_OPERATIONS, "invalid_model_operation")
        _require_string(run["template_version"], "invalid_model_metadata", max_length=80)
        if not isinstance(run["input_hashes"], list) or len(run["input_hashes"]) > 10_000:
            raise PortabilityError("invalid_model_metadata")
        for input_hash in run["input_hashes"]:
            _require_hash(input_hash, "invalid_model_metadata")
        _require_id(run["parent_run_id"], "invalid_model_lineage", nullable=True)
        _require_integer(run["attempt_number"], "invalid_model_attempt", minimum=1)
        _require_string(
            run["repair_reason"], "invalid_model_metadata", max_length=80, nullable=True
        )
        _require_enum(run["status"], MODEL_RUN_STATUSES, "invalid_model_status")
        _require_enum(
            run["validation_status"],
            MODEL_VALIDATION_STATUSES,
            "invalid_model_validation_status",
            nullable=True,
        )
        for field in ("latency_ms", "prompt_tokens", "completion_tokens"):
            _require_integer(run[field], "invalid_model_counter", nullable=True)
        _require_string(run["error_code"], "invalid_model_metadata", max_length=80, nullable=True)
        _require_datetime(run["created_at"], "invalid_model_datetime")
        _require_datetime(run["finished_at"], "invalid_model_datetime", nullable=True)

    for event in arrays["audit_events"]:
        _require_id(event["workspace_id"], "invalid_audit_workspace")
        _require_string(event["actor"], "invalid_audit_field", max_length=100)
        _require_string(event["action"], "invalid_audit_field", max_length=80)
        _require_enum(
            event["object_type"],
            {"source", "memory", "decision", "action_proposal"},
            "invalid_audit_reference",
        )
        _require_id(event["object_id"], "invalid_audit_reference")
        if not isinstance(event["before"], dict) or not isinstance(event["after"], dict):
            raise PortabilityError("invalid_audit_snapshot")
        _require_json_value(event["before"], "invalid_audit_snapshot")
        _require_json_value(event["after"], "invalid_audit_snapshot")
        _require_datetime(event["created_at"], "invalid_audit_datetime")

    for job in arrays["ingestion_jobs"]:
        _require_id(job["source_id"], "invalid_job_reference", nullable=True)
        _require_id(job["source_version_id"], "invalid_job_reference", nullable=True)
        _require_enum(job["kind"], {"source_ingestion"}, "invalid_ingestion_diagnostic")
        _require_enum(job["state"], TERMINAL_INGESTION_STATES, "invalid_ingestion_diagnostic")
        _require_enum(job["stage"], INGESTION_STAGES, "invalid_ingestion_diagnostic")
        attempts = _require_integer(job["attempts"], "invalid_ingestion_attempts", minimum=1)
        max_attempts = _require_integer(
            job["max_attempts"], "invalid_ingestion_attempts", minimum=1
        )
        if attempts is not None and max_attempts is not None and attempts > max_attempts:
            raise PortabilityError("invalid_ingestion_attempts")
        _require_string(
            job["error_code"], "invalid_ingestion_diagnostic", max_length=80, nullable=True
        )
        if not isinstance(job["retryable"], bool):
            raise PortabilityError("invalid_ingestion_diagnostic")
        for field in ("created_at", "updated_at"):
            _require_datetime(job[field], "invalid_ingestion_datetime")
        for field in ("started_at", "finished_at"):
            _require_datetime(job[field], "invalid_ingestion_datetime", nullable=True)

    for card in arrays["study_cards"]:
        for field in ("workspace_id", "source_id", "source_version_id"):
            _require_id(card[field], "invalid_study_reference")
        _require_string(card["question"], "invalid_study_field", max_length=MAX_CONTENT_LENGTH)
        _require_string(card["answer"], "invalid_study_field", max_length=MAX_CONTENT_LENGTH)
        _require_hash(card["quote_hash"], "invalid_study_quote_hash")
        for field in ("start_offset", "end_offset"):
            _require_integer(card[field], "invalid_study_span", maximum=MAX_CONTENT_LENGTH)
        for field in ("start_line", "end_line"):
            _require_integer(card[field], "invalid_study_line", minimum=1)
        _require_enum(card["state"], STUDY_STATES, "invalid_study_state")
        _require_integer(card["interval_days"], "invalid_study_interval")
        for field in ("due_at", "created_at", "updated_at"):
            _require_datetime(card[field], "invalid_study_datetime")

    for review in arrays["study_reviews"]:
        _require_id(review["card_id"], "invalid_study_review_reference")
        _require_enum(review["rating"], STUDY_RATINGS, "invalid_study_rating")
        _require_integer(review["previous_interval_days"], "invalid_study_interval")
        _require_integer(review["next_interval_days"], "invalid_study_interval")
        _require_datetime(review["reviewed_at"], "invalid_study_datetime")

    for proposal in arrays["action_proposals"]:
        _require_id(proposal["workspace_id"], "invalid_proposal_reference")
        _require_string(proposal["goal"], "invalid_proposal_field", max_length=MAX_CONTENT_LENGTH)
        _require_string(proposal["body"], "invalid_proposal_field", max_length=MAX_CONTENT_LENGTH)
        _require_enum(proposal["status"], PROPOSAL_STATUSES, "invalid_proposal_status")
        _require_id(proposal["model_run_id"], "invalid_proposal_model_reference")
        for field in ("created_at", "updated_at"):
            _require_datetime(proposal[field], "invalid_proposal_datetime")

    for citation in arrays["proposal_citations"]:
        for field in ("proposal_id", "source_id", "source_version_id", "chunk_id"):
            _require_id(citation[field], "invalid_proposal_citation_reference")
        _require_string(citation["source_title"], "invalid_proposal_citation_field", max_length=300)
        _require_string(
            citation["quote"], "invalid_proposal_citation_span", max_length=MAX_CONTENT_LENGTH
        )
        _require_hash(citation["quote_hash"], "invalid_proposal_citation_quote_hash")
        for field in ("start_offset", "end_offset"):
            _require_integer(
                citation[field], "invalid_proposal_citation_span", maximum=MAX_CONTENT_LENGTH
            )
        for field in ("start_line", "end_line"):
            _require_integer(citation[field], "invalid_proposal_citation_line", minimum=1)

    for artifact in arrays["studio_artifacts"]:
        for field in ("workspace_id", "source_id", "source_version_id"):
            _require_id(artifact[field], "invalid_studio_reference")
        _require_enum(artifact["kind"], STUDIO_KINDS, "invalid_studio_kind")
        _require_string(artifact["title"], "invalid_studio_field", max_length=400)
        _require_json_value(artifact["content"], "invalid_studio_content")
        _require_enum(artifact["status"], {"ready"}, "invalid_studio_status")
        _require_string(artifact["generation_method"], "invalid_studio_field", max_length=40)
        for field in ("created_at", "updated_at"):
            _require_datetime(artifact[field], "invalid_studio_datetime")

    for citation in arrays["studio_citations"]:
        for field in ("artifact_id", "source_id", "source_version_id"):
            _require_id(citation[field], "invalid_studio_citation_reference")
        _require_integer(citation["ordinal"], "invalid_studio_citation_ordinal")
        _require_string(
            citation["quote"], "invalid_studio_citation_span", max_length=MAX_CONTENT_LENGTH
        )
        _require_hash(citation["quote_hash"], "invalid_studio_citation_quote_hash")
        for field in ("start_offset", "end_offset"):
            _require_integer(
                citation[field], "invalid_studio_citation_span", maximum=MAX_CONTENT_LENGTH
            )
        for field in ("start_line", "end_line"):
            _require_integer(citation[field], "invalid_studio_citation_line", minimum=1)


def verify_portable_export(document: Any) -> dict[str, int]:
    document = normalize_portable_export(document)
    root = _require_mapping(document, "invalid_structure")
    if set(root) != {"manifest", "payload"}:
        raise PortabilityError("invalid_structure")
    manifest = _require_mapping(root["manifest"], "invalid_manifest")
    payload = _require_mapping(root["payload"], "invalid_payload")
    if set(manifest) != MANIFEST_KEYS or set(payload) != PAYLOAD_KEYS:
        raise PortabilityError("unexpected_fields")
    if manifest.get("schema") != PORTABLE_EXPORT_SCHEMA:
        raise PortabilityError("unsupported_schema")
    expected_hash = manifest.get("payload_sha256")
    if not isinstance(expected_hash, str):
        raise PortabilityError("payload_hash_mismatch")
    try:
        actual_hash = payload_sha256(payload)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise PortabilityError("invalid_payload") from exc
    if actual_hash != expected_hash:
        raise PortabilityError("payload_hash_mismatch")

    arrays = {key: _require_array(payload[key], "invalid_payload") for key in PAYLOAD_KEYS}
    if any(set(item) != ITEM_KEYS[key] for key, items in arrays.items() for item in items):
        raise PortabilityError("unexpected_fields")
    counts = _require_mapping(manifest.get("counts"), "invalid_counts")
    expected_counts = {key: len(arrays[key]) for key in sorted(PAYLOAD_KEYS)}
    if set(counts) != PAYLOAD_KEYS or any(
        _require_integer(counts[key], "invalid_counts") != expected_counts[key]
        for key in PAYLOAD_KEYS
    ):
        raise PortabilityError("count_mismatch")

    _validate_scalar_fields(manifest, arrays)

    workspaces = _by_id(arrays["workspaces"], "invalid_workspace_id")
    sources = _by_id(arrays["sources"], "invalid_source_id")
    versions = _by_id(arrays["source_versions"], "invalid_version_id")
    chunks = _by_id(arrays["chunks"], "invalid_chunk_id")
    memories = _by_id(arrays["memories"], "invalid_memory_id")
    evidence = _by_id(arrays["evidence"], "invalid_evidence_id")
    model_runs = _by_id(arrays["model_runs"], "invalid_model_run_id")
    _by_id(arrays["audit_events"], "invalid_audit_id")
    _by_id(arrays["ingestion_jobs"], "invalid_job_id")
    study_cards = _by_id(arrays["study_cards"], "invalid_study_card_id")
    _by_id(arrays["study_reviews"], "invalid_study_review_id")
    proposals = _by_id(arrays["action_proposals"], "invalid_proposal_id")
    proposal_citations = _by_id(arrays["proposal_citations"], "invalid_proposal_citation_id")
    artifacts = _by_id(arrays["studio_artifacts"], "invalid_studio_artifact_id")
    studio_citations = _by_id(arrays["studio_citations"], "invalid_studio_citation_id")
    _require_canonical_order(arrays)

    workspace_slugs: set[str] = set()
    for workspace in workspaces.values():
        if workspace["slug"] in workspace_slugs:
            raise PortabilityError("duplicate_workspace_slug")
        workspace_slugs.add(workspace["slug"])

    version_numbers: dict[str, set[int]] = {source_id: set() for source_id in sources}
    version_hashes: dict[str, set[str]] = {source_id: set() for source_id in sources}
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
        content_hash = version.get("content_hash")
        if content_hash in version_hashes[source_id]:
            raise PortabilityError("duplicate_source_version")
        version_hashes[source_id].add(content_hash)
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != version.get("content_hash"):
            raise PortabilityError("source_content_hash_mismatch")
        if version.get("content_length") != len(content):
            raise PortabilityError("source_content_length_mismatch")

    for source in sources.values():
        if source.get("workspace_id") not in workspaces:
            raise PortabilityError("invalid_source_workspace")
        identity_hash = source.get("identity_hash")
        if (
            not isinstance(identity_hash, str)
            or len(identity_hash) != 64
            or any(value not in "0123456789abcdef" for value in identity_hash)
        ):
            raise PortabilityError("invalid_source_identity")
        expected_identity = hashlib.sha256(f"source:{source['id']}".encode()).hexdigest()
        if identity_hash != expected_identity:
            raise PortabilityError("invalid_source_identity")
        current = versions.get(source.get("current_version_id"))
        if not current or current.get("source_id") != source["id"]:
            raise PortabilityError("invalid_current_version")
        if current.get("version_number") != max(version_numbers[source["id"]], default=0):
            raise PortabilityError("current_version_not_latest")

    chunk_ordinals: set[tuple[str, int]] = set()
    for chunk in chunks.values():
        version = versions.get(chunk.get("source_version_id"))
        source_id = chunk.get("source_id")
        if source_id not in sources or not version or version.get("source_id") != source_id:
            raise PortabilityError("invalid_chunk_reference")
        ordinal_key = (version["id"], chunk["ordinal"])
        if ordinal_key in chunk_ordinals:
            raise PortabilityError("duplicate_chunk_ordinal")
        chunk_ordinals.add(ordinal_key)
        content = version["content"]
        start, end = chunk["start_offset"], chunk["end_offset"]
        if (
            start < 0
            or end <= start
            or end > len(content)
            or content[start:end] != chunk["content"]
        ):
            raise PortabilityError("invalid_chunk_span")
        if chunk["start_line"] != content.count("\n", 0, start) + 1:
            raise PortabilityError("invalid_chunk_line")
        if chunk["end_line"] != content.count("\n", 0, end - 1) + 1:
            raise PortabilityError("invalid_chunk_line")

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
        if event.get("workspace_id") not in workspaces:
            raise PortabilityError("invalid_audit_workspace")
        if object_type == "source":
            valid = object_id in sources
        elif object_type in {"memory", "decision"}:
            valid = object_id in memories
        elif object_type == "action_proposal":
            valid = object_id in proposals
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

    for card in study_cards.values():
        version = versions.get(card.get("source_version_id"))
        source = sources.get(card.get("source_id"))
        if (
            card.get("workspace_id") not in workspaces
            or source is None
            or version is None
            or source["workspace_id"] != card["workspace_id"]
            or version["source_id"] != source["id"]
        ):
            raise PortabilityError("invalid_study_reference")
        content = version["content"]
        start, end = card["start_offset"], card["end_offset"]
        if start < 0 or end <= start or end > len(content) or content[start:end] != card["answer"]:
            raise PortabilityError("invalid_study_span")
        if hashlib.sha256(card["answer"].encode()).hexdigest() != card["quote_hash"]:
            raise PortabilityError("invalid_study_quote_hash")
        if card["start_line"] != content.count("\n", 0, start) + 1:
            raise PortabilityError("invalid_study_line")
        if card["end_line"] != content.count("\n", 0, end - 1) + 1:
            raise PortabilityError("invalid_study_line")

    reviews_by_card: dict[str, list[dict[str, Any]]] = {}
    for review in arrays["study_reviews"]:
        if review["card_id"] not in study_cards:
            raise PortabilityError("invalid_study_review_reference")
        reviews_by_card.setdefault(review["card_id"], []).append(review)
    for card_id, reviews in reviews_by_card.items():
        ordered = sorted(reviews, key=lambda item: (item["reviewed_at"], item["id"]))
        previous = 0
        for review in ordered:
            if review["previous_interval_days"] != previous:
                raise PortabilityError("invalid_study_review_history")
            previous = review["next_interval_days"]
        if study_cards[card_id]["interval_days"] != previous:
            raise PortabilityError("invalid_study_review_history")

    for proposal in proposals.values():
        if proposal["workspace_id"] not in workspaces:
            raise PortabilityError("invalid_proposal_reference")
        if proposal["model_run_id"] not in model_runs:
            raise PortabilityError("invalid_proposal_model_reference")
    proposal_citation_counts = {proposal_id: 0 for proposal_id in proposals}
    for citation in proposal_citations.values():
        proposal = proposals.get(citation["proposal_id"])
        source = sources.get(citation["source_id"])
        version = versions.get(citation["source_version_id"])
        chunk = chunks.get(citation["chunk_id"])
        if (
            proposal is None
            or source is None
            or version is None
            or chunk is None
            or source["workspace_id"] != proposal["workspace_id"]
            or version["source_id"] != source["id"]
            or chunk["source_version_id"] != version["id"]
        ):
            raise PortabilityError("invalid_proposal_citation_reference")
        if source["title"] != citation["source_title"]:
            raise PortabilityError("invalid_proposal_citation_field")
        if chunk["content"] != citation["quote"]:
            raise PortabilityError("invalid_proposal_citation_span")
        if hashlib.sha256(citation["quote"].encode()).hexdigest() != citation["quote_hash"]:
            raise PortabilityError("invalid_proposal_citation_quote_hash")
        proposal_citation_counts[proposal["id"]] += 1
    if any(count < 1 for count in proposal_citation_counts.values()):
        raise PortabilityError("proposal_without_citation")

    artifact_citation_counts = {artifact_id: 0 for artifact_id in artifacts}
    artifact_ordinals: set[tuple[str, int]] = set()
    for artifact in artifacts.values():
        source = sources.get(artifact["source_id"])
        version = versions.get(artifact["source_version_id"])
        if (
            artifact["workspace_id"] not in workspaces
            or source is None
            or version is None
            or source["workspace_id"] != artifact["workspace_id"]
            or version["source_id"] != source["id"]
        ):
            raise PortabilityError("invalid_studio_reference")
    for citation in studio_citations.values():
        artifact = artifacts.get(citation["artifact_id"])
        version = versions.get(citation["source_version_id"])
        if (
            artifact is None
            or version is None
            or citation["source_id"] != artifact["source_id"]
            or citation["source_version_id"] != artifact["source_version_id"]
        ):
            raise PortabilityError("invalid_studio_citation_reference")
        ordinal_key = (artifact["id"], citation["ordinal"])
        if ordinal_key in artifact_ordinals:
            raise PortabilityError("duplicate_studio_citation_ordinal")
        artifact_ordinals.add(ordinal_key)
        content = version["content"]
        start, end = citation["start_offset"], citation["end_offset"]
        if (
            start < 0
            or end <= start
            or end > len(content)
            or content[start:end] != citation["quote"]
        ):
            raise PortabilityError("invalid_studio_citation_span")
        if hashlib.sha256(citation["quote"].encode()).hexdigest() != citation["quote_hash"]:
            raise PortabilityError("invalid_studio_citation_quote_hash")
        artifact_citation_counts[artifact["id"]] += 1
    if any(count < 1 for count in artifact_citation_counts.values()):
        raise PortabilityError("studio_artifact_without_citation")
    return expected_counts


def load_verified_export_document(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            encoded = handle.read(MAX_EXPORT_BYTES + 1)
        if len(encoded) > MAX_EXPORT_BYTES:
            raise PortabilityError("export_too_large")
        document = json.loads(encoded.decode("utf-8"))
    except PortabilityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PortabilityError("export_unreadable") from exc
    normalized = normalize_portable_export(document)
    verify_portable_export(normalized)
    return normalized


def load_and_verify_export(path: Path) -> dict[str, int]:
    document = load_verified_export_document(path)
    return document["manifest"]["counts"]


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
