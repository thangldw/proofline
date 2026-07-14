from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import (
    ActionProposal,
    AuditEvent,
    Chunk,
    ChunkEmbedding,
    Decision,
    Evidence,
    ImportReceipt,
    IngestionJob,
    IngestionJobInput,
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
from .portability import (
    PortabilityError,
    build_portable_export,
    load_verified_export_document,
    normalize_portable_export,
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
    StudyCard,
    StudyReview,
    ActionProposal,
    ProposalCitation,
    StudioArtifact,
    StudioCitation,
    IngestionJobInput,
    ImportReceipt,
)

ID_COLLECTIONS = {
    "workspaces": "workspace",
    "sources": "source",
    "source_versions": "source_version",
    "chunks": "chunk",
    "memories": "memory",
    "evidence": "evidence",
    "model_runs": "model_run",
    "audit_events": "audit_event",
    "ingestion_jobs": "ingestion_job",
    "study_cards": "study_card",
    "study_reviews": "study_review",
    "action_proposals": "action_proposal",
    "proposal_citations": "proposal_citation",
    "studio_artifacts": "studio_artifact",
    "studio_citations": "studio_citation",
}


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


def _insert_chunks(session: Session, items: list[dict[str, Any]]) -> None:
    for item in items:
        session.add(
            Chunk(
                id=item["id"],
                source_id=item["source_id"],
                source_version_id=item["source_version_id"],
                ordinal=item["ordinal"],
                content=item["content"],
                start_offset=item["start_offset"],
                end_offset=item["end_offset"],
                start_line=item["start_line"],
                end_line=item["end_line"],
            )
        )
        session.execute(
            text(
                "INSERT INTO chunk_search(chunk_id, source_id, content) "
                "VALUES (:chunk, :source, :content)"
            ),
            {"chunk": item["id"], "source": item["source_id"], "content": item["content"]},
        )
    session.flush()


def _merge_id(payload_hash: str, kind: str, value: str) -> str:
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, f"proofline:{payload_hash}")
    return str(uuid.uuid5(namespace, f"{kind}:{value}"))


def preview_portable_merge(session: Session, document: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, content-free remap plan without mutating the target."""
    document = normalize_portable_export(document)
    counts = verify_portable_export(document)
    payload_hash = document["manifest"]["payload_sha256"]
    remap = {
        kind: {
            item["id"]: _merge_id(payload_hash, kind, item["id"])
            for item in document["payload"][collection]
        }
        for collection, kind in ID_COLLECTIONS.items()
    }
    for item in document["payload"]["workspaces"]:
        existing_workspace = session.get(Workspace, item["id"])
        if (
            existing_workspace is not None
            and existing_workspace.slug == item["slug"]
            and existing_workspace.title == item["title"]
        ):
            remap["workspace"][item["id"]] = item["id"]
    existing = {
        model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
        for model in DOMAIN_MODELS
        if model is not ImportReceipt
    }
    plan_body = {
        "schema": document["manifest"]["schema"],
        "payload_sha256": payload_hash,
        "counts": counts,
        "target_counts": existing,
        "strategy": "remap_all_ids_no_overwrite",
        "remap": remap,
    }
    plan_body["preview_sha256"] = hashlib.sha256(
        json.dumps(plan_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return plan_body


def _remap_document(document: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    remapped = copy.deepcopy(document)
    payload = remapped["payload"]
    maps = plan["remap"]

    for item in payload["workspaces"]:
        old_id = item["id"]
        item["id"] = maps["workspace"][old_id]
        if item["id"] != old_id:
            item["slug"] = f"{item['slug'][:67]}-{item['id'][:12]}"
    for collection, kind in ID_COLLECTIONS.items():
        if collection == "workspaces":
            continue
        for item in payload[collection]:
            item["id"] = maps[kind][item["id"]]
    for item in payload["sources"]:
        item["identity_hash"] = hashlib.sha256(f"source:{item['id']}".encode()).hexdigest()
        item["workspace_id"] = maps["workspace"][item["workspace_id"]]
        item["current_version_id"] = maps["source_version"][item["current_version_id"]]
    for item in payload["source_versions"]:
        item["source_id"] = maps["source"][item["source_id"]]
    for item in payload["memories"]:
        item["source_id"] = maps["source"][item["source_id"]]
        item["source_version_id"] = maps["source_version"][item["source_version_id"]]
        if item["model_run_id"] is not None:
            item["model_run_id"] = maps["model_run"][item["model_run_id"]]
    for item in payload["evidence"]:
        item["memory_id"] = maps["memory"][item["memory_id"]]
        item["source_id"] = maps["source"][item["source_id"]]
        item["source_version_id"] = maps["source_version"][item["source_version_id"]]
    for item in payload["chunks"]:
        item["source_id"] = maps["source"][item["source_id"]]
        item["source_version_id"] = maps["source_version"][item["source_version_id"]]
    for item in payload["model_runs"]:
        if item["parent_run_id"] is not None:
            item["parent_run_id"] = maps["model_run"][item["parent_run_id"]]
    for item in payload["audit_events"]:
        item["workspace_id"] = maps["workspace"][item["workspace_id"]]
        object_kind = "memory" if item["object_type"] == "decision" else item["object_type"]
        object_map = maps.get(object_kind)
        if object_map and item["object_id"] in object_map:
            item["object_id"] = object_map[item["object_id"]]
    for item in payload["ingestion_jobs"]:
        if item["source_id"] is not None:
            item["source_id"] = maps["source"][item["source_id"]]
        if item["source_version_id"] is not None:
            item["source_version_id"] = maps["source_version"][item["source_version_id"]]
    for item in payload["study_cards"]:
        item["workspace_id"] = maps["workspace"][item["workspace_id"]]
        item["source_id"] = maps["source"][item["source_id"]]
        item["source_version_id"] = maps["source_version"][item["source_version_id"]]
    for item in payload["study_reviews"]:
        item["card_id"] = maps["study_card"][item["card_id"]]
    for item in payload["action_proposals"]:
        item["workspace_id"] = maps["workspace"][item["workspace_id"]]
        item["model_run_id"] = maps["model_run"][item["model_run_id"]]
    for item in payload["proposal_citations"]:
        item["proposal_id"] = maps["action_proposal"][item["proposal_id"]]
        item["source_id"] = maps["source"][item["source_id"]]
        item["source_version_id"] = maps["source_version"][item["source_version_id"]]
        item["chunk_id"] = maps["chunk"][item["chunk_id"]]
    for item in payload["studio_artifacts"]:
        item["workspace_id"] = maps["workspace"][item["workspace_id"]]
        item["source_id"] = maps["source"][item["source_id"]]
        item["source_version_id"] = maps["source_version"][item["source_version_id"]]
    for item in payload["studio_citations"]:
        item["artifact_id"] = maps["studio_artifact"][item["artifact_id"]]
        item["source_id"] = maps["source"][item["source_id"]]
        item["source_version_id"] = maps["source_version"][item["source_version_id"]]
    return remapped


def _import_verified(
    session: Session,
    document: dict[str, Any],
    counts: dict[str, int],
    *,
    verify_payload_equivalence: bool = True,
    receipt_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = document["manifest"]
    payload = document["payload"]
    versions_by_id = {item["id"]: item for item in payload["source_versions"]}

    try:
        for item in payload["workspaces"]:
            existing = session.get(Workspace, item["id"])
            if existing is None:
                session.add(
                    Workspace(
                        id=item["id"],
                        slug=item["slug"],
                        title=item["title"],
                        created_at=_datetime(item["created_at"]),
                    )
                )
            elif existing.slug != item["slug"] or existing.title != item["title"]:
                raise PortabilityError("workspace_conflict")
            else:
                existing.created_at = _datetime(item["created_at"])
        session.flush()

        _insert_model_runs(session, payload["model_runs"])

        sources: dict[str, Source] = {}
        for item in payload["sources"]:
            current = versions_by_id[item["current_version_id"]]
            source = Source(
                id=item["id"],
                workspace_id=item["workspace_id"],
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

        _insert_chunks(session, payload["chunks"])

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

        for item in payload["study_cards"]:
            session.add(
                StudyCard(
                    id=item["id"],
                    workspace_id=item["workspace_id"],
                    source_id=item["source_id"],
                    source_version_id=item["source_version_id"],
                    question=item["question"],
                    answer=item["answer"],
                    quote_hash=item["quote_hash"],
                    start_offset=item["start_offset"],
                    end_offset=item["end_offset"],
                    start_line=item["start_line"],
                    end_line=item["end_line"],
                    state=item["state"],
                    interval_days=item["interval_days"],
                    due_at=_datetime(item["due_at"]),
                    created_at=_datetime(item["created_at"]),
                    updated_at=_datetime(item["updated_at"]),
                )
            )
        session.flush()
        for item in payload["study_reviews"]:
            session.add(
                StudyReview(
                    id=item["id"],
                    card_id=item["card_id"],
                    rating=item["rating"],
                    previous_interval_days=item["previous_interval_days"],
                    next_interval_days=item["next_interval_days"],
                    reviewed_at=_datetime(item["reviewed_at"]),
                )
            )

        for item in payload["action_proposals"]:
            session.add(
                ActionProposal(
                    id=item["id"],
                    workspace_id=item["workspace_id"],
                    goal=item["goal"],
                    body=item["body"],
                    status=item["status"],
                    model_run_id=item["model_run_id"],
                    created_at=_datetime(item["created_at"]),
                    updated_at=_datetime(item["updated_at"]),
                )
            )
        session.flush()
        for item in payload["proposal_citations"]:
            session.add(
                ProposalCitation(
                    id=item["id"],
                    proposal_id=item["proposal_id"],
                    source_id=item["source_id"],
                    source_version_id=item["source_version_id"],
                    chunk_id=item["chunk_id"],
                    source_title=item["source_title"],
                    quote=item["quote"],
                    quote_hash=item["quote_hash"],
                    start_offset=item["start_offset"],
                    end_offset=item["end_offset"],
                    start_line=item["start_line"],
                    end_line=item["end_line"],
                )
            )

        for item in payload["studio_artifacts"]:
            session.add(
                StudioArtifact(
                    id=item["id"],
                    workspace_id=item["workspace_id"],
                    source_id=item["source_id"],
                    source_version_id=item["source_version_id"],
                    kind=item["kind"],
                    title=item["title"],
                    content_json=item["content"],
                    status=item["status"],
                    generation_method=item["generation_method"],
                    created_at=_datetime(item["created_at"]),
                    updated_at=_datetime(item["updated_at"]),
                )
            )
        session.flush()
        for item in payload["studio_citations"]:
            session.add(
                StudioCitation(
                    id=item["id"],
                    artifact_id=item["artifact_id"],
                    source_id=item["source_id"],
                    source_version_id=item["source_version_id"],
                    ordinal=item["ordinal"],
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
                    workspace_id=item["workspace_id"],
                    actor=item["actor"],
                    action=item["action"],
                    object_type=item["object_type"],
                    object_id=item["object_id"],
                    before_json=item["before"],
                    after_json=item["after"],
                    created_at=_datetime(item["created_at"]),
                )
            )
        session.flush()

        receipt = receipt_manifest or manifest
        session.add(
            ImportReceipt(
                schema=receipt["schema"],
                payload_sha256=receipt["payload_sha256"],
                export_app_version=receipt["app_version"],
                export_created_at=_datetime(receipt["created_at"]),
                counts_json=counts,
            )
        )
        session.flush()

        rebuilt = build_portable_export(session) if verify_payload_equivalence else None
        if rebuilt and payload_sha256(rebuilt["payload"]) != manifest["payload_sha256"]:
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
    document = normalize_portable_export(document)
    counts = verify_portable_export(document)
    if not _target_is_empty(session):
        raise PortabilityError("target_not_empty")
    with session.begin_nested():
        return _import_verified(session, document, counts)


def merge_portable_export(
    session: Session,
    document: dict[str, Any],
    *,
    expected_preview_sha256: str,
) -> dict[str, Any]:
    """Apply an explicitly acknowledged no-overwrite merge in one savepoint."""
    document = normalize_portable_export(document)
    plan = preview_portable_merge(session, document)
    if plan["preview_sha256"] != expected_preview_sha256:
        raise PortabilityError("merge_preview_changed")
    receipt = session.scalar(
        select(ImportReceipt).where(
            ImportReceipt.payload_sha256 == document["manifest"]["payload_sha256"]
        )
    )
    if receipt:
        raise PortabilityError("payload_already_imported")
    remapped = _remap_document(document, plan)
    counts = document["manifest"]["counts"]
    with session.begin_nested():
        report = _import_verified(
            session,
            remapped,
            counts,
            verify_payload_equivalence=False,
            receipt_manifest=document["manifest"],
        )
    return {
        **report,
        "merge": True,
        "preview_sha256": plan["preview_sha256"],
        "remap": plan["remap"],
    }
