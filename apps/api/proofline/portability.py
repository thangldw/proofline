from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__
from .models import (
    ActionProposal,
    AuditEvent,
    Chunk,
    Decision,
    DecisionReview,
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
from .portable_schema import (  # noqa: F401  (re-exported public API)
    ANCHOR_STATES,
    BINDING_STATES,
    DECISION_REVIEW_STATES,
    EXTRACTION_METHODS,
    INGESTION_STAGES,
    ITEM_KEYS,
    LEGACY_ITEM_KEYS,
    LEGACY_PAYLOAD_KEYS,
    LEGACY_PORTABLE_EXPORT_SCHEMA,
    MANIFEST_KEYS,
    MAX_CONTENT_LENGTH,
    MAX_COUNTER,
    MAX_EXPORT_BYTES,
    MEMORY_KINDS,
    MEMORY_STATUSES,
    MODEL_OPERATIONS,
    MODEL_RUN_STATUSES,
    MODEL_VALIDATION_STATUSES,
    PAYLOAD_KEYS,
    PORTABLE_EXPORT_SCHEMA,
    PORTABLE_EXPORT_V2_SCHEMA,
    PROPOSAL_STATUSES,
    SOURCE_KINDS,
    SOURCE_STATUSES,
    STUDIO_KINDS,
    STUDY_RATINGS,
    STUDY_STATES,
    TERMINAL_INGESTION_STATES,
    TERMINAL_REVIEW_STATES,
    V2_ITEM_KEYS,
    V2_PAYLOAD_KEYS,
    PortabilityError,
    _iso,
    canonical_json_bytes,
    normalize_portable_export,
    payload_sha256,
)
from .portable_verify import verify_portable_export


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
    decision_reviews = list(
        session.scalars(select(DecisionReview).order_by(DecisionReview.id)).all()
    )
    model_runs = list(session.scalars(select(ModelRun).order_by(ModelRun.id)).all())
    known_source_ids = {source.id for source in sources}
    known_memory_ids = {memory.id for memory in memories}
    known_proposal_ids = set(session.scalars(select(ActionProposal.id)).all())
    known_review_ids = {review.id for review in decision_reviews}
    audit_events = [
        event
        for event in session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
        if (event.object_type == "source" and event.object_id in known_source_ids)
        or (event.object_type in {"memory", "decision"} and event.object_id in known_memory_ids)
        or (event.object_type == "action_proposal" and event.object_id in known_proposal_ids)
        or (event.object_type == "decision_review" and event.object_id in known_review_ids)
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
                "anchor_version": item.anchor_version,
                "section_path": item.section_path,
                "prefix_sha256": item.prefix_sha256,
                "suffix_sha256": item.suffix_sha256,
                "binding_root_id": item.binding_root_id,
                "binding_state": item.binding_state,
                "superseded_at": _iso(item.superseded_at),
                "superseded_by_id": item.superseded_by_id,
            }
            for item in evidence
        ],
        "decision_reviews": [
            {
                "id": item.id,
                "workspace_id": item.workspace_id,
                "decision_id": item.decision_id,
                "evidence_id": item.evidence_id,
                "cited_source_version_id": item.cited_source_version_id,
                "current_source_version_id": item.current_source_version_id,
                "finding_fingerprint": item.finding_fingerprint,
                "anchor_state": item.anchor_state,
                "severity": item.severity,
                "policy_hash": item.policy_hash,
                "candidate_start_offset": item.candidate_start_offset,
                "candidate_end_offset": item.candidate_end_offset,
                "candidate_start_line": item.candidate_start_line,
                "candidate_end_line": item.candidate_end_line,
                "state": item.state,
                "resolution": item.resolution,
                "actor": item.actor,
                "note": item.note,
                "opened_at": _iso(item.opened_at),
                "updated_at": _iso(item.updated_at),
                "closed_at": _iso(item.closed_at),
            }
            for item in decision_reviews
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
                raise PortabilityError("output_exists") from exc
            temporary.unlink()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
