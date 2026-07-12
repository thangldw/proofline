from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .ingestion import index_source_version_chunks
from .models import (
    AuditEvent,
    Chunk,
    ChunkEmbedding,
    Decision,
    Evidence,
    ImportReceipt,
    IngestionJob,
    IngestionJobInput,
    ModelRun,
    Source,
    SourceVersion,
)
from .portability import (
    PortabilityError,
    build_portable_export,
    load_verified_export_document,
    payload_sha256,
    verify_portable_export,
)

DOMAIN_MODELS = (
    Source,
    SourceVersion,
    Chunk,
    ChunkEmbedding,
    Decision,
    Evidence,
    ModelRun,
    AuditEvent,
    IngestionJob,
    IngestionJobInput,
    ImportReceipt,
)


def load_verified_import(path: Path) -> dict[str, Any]:
    return load_verified_export_document(path)


def _datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PortabilityError("invalid_datetime")
    return parsed.astimezone(UTC)


def _target_is_empty(session: Session) -> bool:
    for model in DOMAIN_MODELS:
        if session.scalar(select(func.count()).select_from(model)):
            return False
    return session.scalar(text("SELECT count(*) FROM chunk_search")) == 0


def _insert_model_runs(session: Session, items: list[dict[str, Any]]) -> None:
    pending = {item["id"]: item for item in items}
    inserted: set[str] = set()
    while pending:
        ready = [
            item
            for item in pending.values()
            if item["parent_run_id"] is None or item["parent_run_id"] in inserted
        ]
        if not ready:
            raise PortabilityError("invalid_model_lineage")
        for item in sorted(ready, key=lambda value: value["id"]):
            session.add(
                ModelRun(
                    id=item["id"],
                    provider_id=item["provider_id"],
                    model_id=item["model_id"],
                    operation=item["operation"],
                    template_version=item["template_version"],
                    input_hashes=item["input_hashes"],
                    parent_run_id=item["parent_run_id"],
                    attempt_number=item["attempt_number"],
                    repair_reason=item["repair_reason"],
                    status=item["status"],
                    validation_status=item["validation_status"],
                    latency_ms=item["latency_ms"],
                    prompt_tokens=item["prompt_tokens"],
                    completion_tokens=item["completion_tokens"],
                    error_code=item["error_code"],
                    created_at=_datetime(item["created_at"]),
                    finished_at=_datetime(item["finished_at"]),
                )
            )
            inserted.add(item["id"])
            del pending[item["id"]]
        session.flush()


def _import_verified(
    session: Session, document: dict[str, Any], counts: dict[str, int]
) -> dict[str, Any]:
    manifest = document["manifest"]
    payload = document["payload"]
    versions_by_id = {item["id"]: item for item in payload["source_versions"]}

    try:
        _insert_model_runs(session, payload["model_runs"])

        sources: dict[str, Source] = {}
        for item in payload["sources"]:
            current = versions_by_id[item["current_version_id"]]
            source = Source(
                id=item["id"],
                title=item["title"],
                kind=item["kind"],
                uri=item["uri"],
                content=current["content"],
                content_hash=item["identity_hash"],
                status=item["status"],
                created_at=_datetime(item["created_at"]),
                indexed_at=_datetime(item["indexed_at"]),
                current_version_id=item["current_version_id"],
            )
            session.add(source)
            sources[source.id] = source
        session.flush()

        versions: dict[str, SourceVersion] = {}
        for item in payload["source_versions"]:
            version = SourceVersion(
                id=item["id"],
                source_id=item["source_id"],
                content_hash=item["content_hash"],
                content=item["content"],
                version_number=item["version_number"],
                content_length=item["content_length"],
                status=item["status"],
                parser_version=item["parser_version"],
                created_at=_datetime(item["created_at"]),
            )
            session.add(version)
            versions[version.id] = version
        session.flush()

        for item in payload["memories"]:
            session.add(
                Decision(
                    id=item["id"],
                    source_id=item["source_id"],
                    source_version_id=item["source_version_id"],
                    kind=item["kind"],
                    title=item["title"],
                    statement=item["statement"],
                    rationale=item["rationale"],
                    status=item["status"],
                    confidence=item["confidence"],
                    extraction_method=item["extraction_method"],
                    model_run_id=item["model_run_id"],
                    valid_from=_datetime(item["valid_from"]),
                    valid_to=_datetime(item["valid_to"]),
                    created_at=_datetime(item["created_at"]),
                    updated_at=_datetime(item["updated_at"]),
                )
            )
        session.flush()

        for item in payload["evidence"]:
            session.add(
                Evidence(
                    id=item["id"],
                    decision_id=item["memory_id"],
                    source_id=item["source_id"],
                    source_version_id=item["source_version_id"],
                    quote=item["quote"],
                    quote_hash=item["quote_hash"],
                    start_offset=item["start_offset"],
                    end_offset=item["end_offset"],
                    start_line=item["start_line"],
                    end_line=item["end_line"],
                )
            )

        for item in payload["audit_events"]:
            session.add(
                AuditEvent(
                    id=item["id"],
                    actor=item["actor"],
                    action=item["action"],
                    object_type=item["object_type"],
                    object_id=item["object_id"],
                    before_json=item["before"],
                    after_json=item["after"],
                    created_at=_datetime(item["created_at"]),
                )
            )

        for item in payload["ingestion_jobs"]:
            session.add(
                IngestionJob(
                    id=item["id"],
                    source_id=item["source_id"],
                    source_version_id=item["source_version_id"],
                    kind=item["kind"],
                    state=item["state"],
                    stage=item["stage"],
                    attempts=item["attempts"],
                    max_attempts=item["max_attempts"],
                    error_code=item["error_code"],
                    error_detail=None,
                    retryable=item["retryable"],
                    request_hash=None,
                    idempotency_key=None,
                    created_at=_datetime(item["created_at"]),
                    updated_at=_datetime(item["updated_at"]),
                    started_at=_datetime(item["started_at"]),
                    finished_at=_datetime(item["finished_at"]),
                )
            )
        session.flush()

        for item in payload["source_versions"]:
            index_source_version_chunks(
                session,
                sources[item["source_id"]],
                versions[item["id"]],
                item["content"],
            )

        session.add(
            ImportReceipt(
                schema=manifest["schema"],
                payload_sha256=manifest["payload_sha256"],
                export_app_version=manifest["app_version"],
                export_created_at=_datetime(manifest["created_at"]),
                counts_json=counts,
            )
        )
        session.flush()

        rebuilt = build_portable_export(session)
        if payload_sha256(rebuilt["payload"]) != manifest["payload_sha256"]:
            raise PortabilityError("import_verification_failed")
    except PortabilityError:
        raise
    except Exception as exc:
        raise PortabilityError("import_failed") from exc

    return {
        "schema": manifest["schema"],
        "payload_sha256": manifest["payload_sha256"],
        "counts": counts,
        "embeddings_rebuilt": False,
    }


def import_portable_export(session: Session, document: dict[str, Any]) -> dict[str, Any]:
    """Restore one verified export into an empty database without committing the transaction."""
    counts = verify_portable_export(document)
    if not _target_is_empty(session):
        raise PortabilityError("target_not_empty")
    with session.begin_nested():
        return _import_verified(session, document, counts)
