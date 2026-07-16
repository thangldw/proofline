from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__
from .models import Chunk, Decision, ModelRun, Source, SourceVersion
from .portability import PortabilityError, atomic_write_export, canonical_json_bytes

DECISION_PACKAGE_SCHEMA = "proofline-decision-evidence-package-v1"
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_PACKAGE_BYTES + 64 * 1024
PACKAGE_ARCHIVE_ENTRY = "evidence.json"
ARTIFACT_KINDS = {"decision", "assumption", "constraint", "alternative"}
REVIEW_STATUSES = {"candidate", "active", "accepted", "rejected", "obsolete"}


class EvidencePackageError(RuntimeError):
    """A package failure identified only by a non-content-bearing code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _hash_envelope(domain: str, value: Any) -> str:
    prefix = f"proofline/{domain}/v1\0".encode()
    return hashlib.sha256(prefix + canonical_json_bytes(value)).hexdigest()


def _node_hash(kind: str, node: dict[str, Any]) -> str:
    body = {key: value for key, value in node.items() if key != "node_hash"}
    return _hash_envelope(f"node/{kind}", body)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidencePackageError("duplicate_json_key")
        result[key] = value
    return result


def _with_hash(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "node_hash": _node_hash(kind, body)}


def _model_lineage(
    session: Session, run_id: str | None, *, workspace_id: str
) -> list[dict[str, Any]]:
    if run_id is None:
        return []
    lineage: list[ModelRun] = []
    visited: set[str] = set()
    cursor = run_id
    while cursor is not None:
        if cursor in visited:
            raise EvidencePackageError("model_run_lineage_invalid")
        visited.add(cursor)
        run = session.get(ModelRun, cursor)
        if run is None or run.workspace_id != workspace_id:
            raise EvidencePackageError("model_run_lineage_invalid")
        lineage.append(run)
        cursor = run.parent_run_id
    lineage.reverse()
    return [
        {
            "id": run.id,
            "workspace_id": run.workspace_id,
            "provider_id": run.provider_id,
            "model_id": run.model_id,
            "operation": run.operation,
            "template_version": run.template_version,
            "input_hashes": run.input_hashes,
            "parent_run_id": run.parent_run_id,
            "attempt_number": run.attempt_number,
            "repair_reason": run.repair_reason,
            "status": run.status,
            "validation_status": run.validation_status,
        }
        for run in lineage
    ]


def build_decision_package(
    session: Session,
    artifact_id: str,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    decision = session.get(Decision, artifact_id)
    if decision is None:
        raise EvidencePackageError("artifact_not_found")
    source = session.get(Source, decision.source_id)
    version = session.get(SourceVersion, decision.source_version_id)
    if source is None or version is None or version.source_id != source.id:
        raise EvidencePackageError("artifact_provenance_invalid")
    if source.content_hash != hashlib.sha256(f"source:{source.id}".encode()).hexdigest():
        raise EvidencePackageError("source_identity_invalid")
    if hashlib.sha256(version.content.encode()).hexdigest() != version.content_hash:
        raise EvidencePackageError("source_version_hash_mismatch")

    source_node = _with_hash(
        "source-version",
        {
            "workspace_id": source.workspace_id,
            "source_id": source.id,
            "source_identity_sha256": source.content_hash,
            "source_version_id": version.id,
            "version_number": version.version_number,
            "content": version.content,
            "content_sha256": version.content_hash,
            "content_length": version.content_length,
            "parser_version": version.parser_version,
        },
    )
    ordered_evidence = sorted(decision.evidence, key=lambda item: (item.start_offset, item.id))
    stored_chunks = session.scalars(
        select(Chunk).where(Chunk.source_version_id == version.id).order_by(Chunk.ordinal, Chunk.id)
    ).all()
    relevant_chunks = [
        chunk
        for chunk in stored_chunks
        if any(
            chunk.start_offset < evidence.end_offset and chunk.end_offset > evidence.start_offset
            for evidence in ordered_evidence
        )
    ]
    chunks: list[dict[str, Any]] = []
    for chunk in relevant_chunks:
        exact = version.content[chunk.start_offset : chunk.end_offset]
        if (
            chunk.source_id != source.id
            or not 0 <= chunk.start_offset < chunk.end_offset <= len(version.content)
            or exact != chunk.content
        ):
            raise EvidencePackageError("chunk_provenance_invalid")
        chunks.append(
            _with_hash(
                "chunk",
                {
                    "id": chunk.id,
                    "source_node_hash": source_node["node_hash"],
                    "source_id": source.id,
                    "source_version_id": version.id,
                    "ordinal": chunk.ordinal,
                    "start_offset": chunk.start_offset,
                    "end_offset": chunk.end_offset,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content,
                    "content_sha256": hashlib.sha256(chunk.content.encode()).hexdigest(),
                },
            )
        )
    if not chunks:
        raise EvidencePackageError("artifact_chunks_missing")

    citations: list[dict[str, Any]] = []
    for evidence in ordered_evidence:
        if evidence.source_id != source.id or evidence.source_version_id != version.id:
            raise EvidencePackageError("citation_ownership_invalid")
        exact = version.content[evidence.start_offset : evidence.end_offset]
        if (
            not 0 <= evidence.start_offset < evidence.end_offset <= len(version.content)
            or exact != evidence.quote
            or hashlib.sha256(exact.encode()).hexdigest() != evidence.quote_hash
        ):
            raise EvidencePackageError("citation_span_invalid")
        citations.append(
            _with_hash(
                "citation",
                {
                    "id": evidence.id,
                    "source_node_hash": source_node["node_hash"],
                    "chunk_node_hashes": [
                        chunk["node_hash"]
                        for chunk in chunks
                        if chunk["start_offset"] < evidence.end_offset
                        and chunk["end_offset"] > evidence.start_offset
                    ],
                    "source_id": source.id,
                    "source_version_id": version.id,
                    "start_offset": evidence.start_offset,
                    "end_offset": evidence.end_offset,
                    "start_line": evidence.start_line,
                    "end_line": evidence.end_line,
                    "quote": evidence.quote,
                    "quote_sha256": evidence.quote_hash,
                },
            )
        )
    if not citations:
        raise EvidencePackageError("artifact_evidence_missing")

    transformation = _with_hash(
        "transformation",
        {
            "method": decision.extraction_method,
            "parser_version": version.parser_version,
            "model_runs": _model_lineage(
                session, decision.model_run_id, workspace_id=source.workspace_id
            ),
            "input_node_hashes": [source_node["node_hash"]]
            + [chunk["node_hash"] for chunk in chunks]
            + [citation["node_hash"] for citation in citations],
        },
    )
    artifact = _with_hash(
        "decision-artifact",
        {
            "id": decision.id,
            "kind": decision.kind,
            "title": decision.title,
            "statement": decision.statement,
            "rationale": decision.rationale,
            "confidence": decision.confidence,
            "valid_from": _iso(decision.valid_from),
            "valid_to": _iso(decision.valid_to),
            "transformation_node_hash": transformation["node_hash"],
            "citation_node_hashes": [citation["node_hash"] for citation in citations],
        },
    )
    review = _with_hash(
        "review-state",
        {
            "artifact_node_hash": artifact["node_hash"],
            "status": decision.status,
            "created_at": _iso(decision.created_at),
            "updated_at": _iso(decision.updated_at),
        },
    )
    root_hash = _hash_envelope(
        "package-root",
        {
            "artifact_node_hash": artifact["node_hash"],
            "review_node_hash": review["node_hash"],
        },
    )
    document = {
        "manifest": {
            "schema": DECISION_PACKAGE_SCHEMA,
            "created_at": _iso(created_at or datetime.now(UTC)),
            "app_version": __version__,
            "root_hash": root_hash,
        },
        "payload": {
            "source_version": source_node,
            "chunks": chunks,
            "citations": citations,
            "transformation": transformation,
            "artifact": artifact,
            "review": review,
        },
    }
    verify_decision_package(document)
    return document


def _require_keys(value: Any, expected: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise EvidencePackageError(code)
    return value


def _require_hash(value: Any, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EvidencePackageError(code)
    return value


def _require_string(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        raise EvidencePackageError(code)
    return value


def _require_datetime(value: Any, code: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise EvidencePackageError(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidencePackageError(code) from exc
    if parsed.tzinfo is None:
        raise EvidencePackageError(code)


def _verify_decision_package(document: Any) -> dict[str, Any]:
    root = _require_keys(document, {"manifest", "payload"}, "package_shape_invalid")
    manifest = _require_keys(
        root["manifest"],
        {"schema", "created_at", "app_version", "root_hash"},
        "manifest_shape_invalid",
    )
    if manifest["schema"] != DECISION_PACKAGE_SCHEMA:
        raise EvidencePackageError("schema_unsupported")
    _require_datetime(manifest["created_at"], "manifest_created_at_invalid")
    _require_string(manifest["app_version"], "manifest_app_version_invalid")
    _require_hash(manifest["root_hash"], "root_hash_invalid")
    payload = _require_keys(
        root["payload"],
        {"source_version", "chunks", "citations", "transformation", "artifact", "review"},
        "payload_shape_invalid",
    )
    source = _require_keys(
        payload["source_version"],
        {
            "workspace_id",
            "source_id",
            "source_identity_sha256",
            "source_version_id",
            "version_number",
            "content",
            "content_sha256",
            "content_length",
            "parser_version",
            "node_hash",
        },
        "source_node_invalid",
    )
    _require_string(source["workspace_id"], "source_identity_invalid")
    _require_string(source["source_id"], "source_identity_invalid")
    _require_string(source["source_version_id"], "source_identity_invalid")
    _require_hash(source["source_identity_sha256"], "source_identity_invalid")
    if (
        source["source_identity_sha256"]
        != hashlib.sha256(f"source:{source['source_id']}".encode()).hexdigest()
    ):
        raise EvidencePackageError("source_identity_invalid")
    _require_string(source["parser_version"], "source_parser_invalid")
    _require_hash(source["content_sha256"], "source_content_hash_invalid")
    _require_hash(source["node_hash"], "source_node_hash_invalid")
    if (
        not isinstance(source["version_number"], int)
        or isinstance(source["version_number"], bool)
        or source["version_number"] < 1
        or not isinstance(source["content_length"], int)
        or isinstance(source["content_length"], bool)
        or not isinstance(source["content"], str)
        or source["content_length"] != len(source["content"])
    ):
        raise EvidencePackageError("source_content_invalid")
    if hashlib.sha256(source["content"].encode()).hexdigest() != source["content_sha256"]:
        raise EvidencePackageError("source_content_hash_mismatch")
    if _node_hash("source-version", source) != source["node_hash"]:
        raise EvidencePackageError("source_node_hash_mismatch")

    chunks = payload["chunks"]
    if not isinstance(chunks, list) or not chunks:
        raise EvidencePackageError("chunks_invalid")
    chunk_hashes: list[str] = []
    chunk_ids: set[str] = set()
    chunk_ordinals: set[int] = set()
    chunk_keys = {
        "id",
        "source_node_hash",
        "source_id",
        "source_version_id",
        "ordinal",
        "start_offset",
        "end_offset",
        "start_line",
        "end_line",
        "content",
        "content_sha256",
        "node_hash",
    }
    for raw_chunk in chunks:
        chunk = _require_keys(raw_chunk, chunk_keys, "chunk_node_invalid")
        _require_string(chunk["id"], "chunk_identity_invalid")
        _require_hash(chunk["source_node_hash"], "chunk_reference_invalid")
        _require_hash(chunk["content_sha256"], "chunk_content_hash_invalid")
        _require_hash(chunk["node_hash"], "chunk_node_hash_invalid")
        start, end, ordinal = chunk["start_offset"], chunk["end_offset"], chunk["ordinal"]
        if (
            chunk["id"] in chunk_ids
            or chunk["node_hash"] in chunk_hashes
            or ordinal in chunk_ordinals
        ):
            raise EvidencePackageError("duplicate_chunk")
        if (
            chunk["source_node_hash"] != source["node_hash"]
            or chunk["source_id"] != source["source_id"]
            or chunk["source_version_id"] != source["source_version_id"]
            or not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal < 0
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not isinstance(chunk["start_line"], int)
            or isinstance(chunk["start_line"], bool)
            or not isinstance(chunk["end_line"], int)
            or isinstance(chunk["end_line"], bool)
            or not 0 <= start < end <= len(source["content"])
        ):
            raise EvidencePackageError("chunk_reference_invalid")
        exact = source["content"][start:end]
        if (
            chunk["content"] != exact
            or chunk["content_sha256"] != hashlib.sha256(exact.encode()).hexdigest()
            or chunk["start_line"] != _line_number(source["content"], start)
            or chunk["end_line"] != _line_number(source["content"], end - 1)
        ):
            raise EvidencePackageError("chunk_span_invalid")
        if _node_hash("chunk", chunk) != chunk["node_hash"]:
            raise EvidencePackageError("chunk_node_hash_mismatch")
        chunk_ids.add(chunk["id"])
        chunk_ordinals.add(ordinal)
        chunk_hashes.append(chunk["node_hash"])

    citations = payload["citations"]
    if not isinstance(citations, list) or not citations:
        raise EvidencePackageError("citations_invalid")
    citation_hashes: list[str] = []
    citation_ids: set[str] = set()
    citation_keys = {
        "id",
        "source_node_hash",
        "chunk_node_hashes",
        "source_id",
        "source_version_id",
        "start_offset",
        "end_offset",
        "start_line",
        "end_line",
        "quote",
        "quote_sha256",
        "node_hash",
    }
    for raw_citation in citations:
        citation = _require_keys(raw_citation, citation_keys, "citation_node_invalid")
        _require_string(citation["id"], "citation_identity_invalid")
        if citation["id"] in citation_ids or citation["node_hash"] in citation_hashes:
            raise EvidencePackageError("duplicate_citation")
        citation_ids.add(citation["id"])
        _require_hash(citation["source_node_hash"], "citation_reference_invalid")
        _require_hash(citation["quote_sha256"], "citation_quote_hash_invalid")
        _require_hash(citation["node_hash"], "citation_node_hash_invalid")
        start, end = citation["start_offset"], citation["end_offset"]
        expected_chunk_hashes = [
            chunk["node_hash"]
            for chunk in chunks
            if chunk["start_offset"] < end and chunk["end_offset"] > start
        ]
        if (
            citation["source_node_hash"] != source["node_hash"]
            or citation["chunk_node_hashes"] != expected_chunk_hashes
            or not expected_chunk_hashes
            or citation["source_id"] != source["source_id"]
            or citation["source_version_id"] != source["source_version_id"]
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not isinstance(citation["start_line"], int)
            or isinstance(citation["start_line"], bool)
            or not isinstance(citation["end_line"], int)
            or isinstance(citation["end_line"], bool)
            or not 0 <= start < end <= len(source["content"])
        ):
            raise EvidencePackageError("citation_reference_invalid")
        exact = source["content"][start:end]
        if (
            citation["quote"] != exact
            or citation["quote_sha256"] != hashlib.sha256(exact.encode()).hexdigest()
            or citation["start_line"] != _line_number(source["content"], start)
            or citation["end_line"] != _line_number(source["content"], end - 1)
        ):
            raise EvidencePackageError("citation_span_invalid")
        if _node_hash("citation", citation) != citation["node_hash"]:
            raise EvidencePackageError("citation_node_hash_mismatch")
        citation_hashes.append(citation["node_hash"])

    transformation = _require_keys(
        payload["transformation"],
        {"method", "parser_version", "model_runs", "input_node_hashes", "node_hash"},
        "transformation_node_invalid",
    )
    if transformation["method"] not in {"deterministic", "model"}:
        raise EvidencePackageError("transformation_method_invalid")
    if transformation["parser_version"] != source["parser_version"]:
        raise EvidencePackageError("transformation_parser_invalid")
    _require_hash(transformation["node_hash"], "transformation_node_hash_invalid")
    if transformation["input_node_hashes"] != [
        source["node_hash"],
        *chunk_hashes,
        *citation_hashes,
    ]:
        raise EvidencePackageError("transformation_inputs_invalid")
    if not isinstance(transformation["model_runs"], list):
        raise EvidencePackageError("model_run_lineage_invalid")
    if (transformation["method"] == "model") != bool(transformation["model_runs"]):
        raise EvidencePackageError("model_run_lineage_invalid")
    previous_id = None
    run_ids: set[str] = set()
    run_keys = {
        "id",
        "workspace_id",
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
    }
    for run in transformation["model_runs"]:
        run = _require_keys(run, run_keys, "model_run_lineage_invalid")
        for field in ("id", "workspace_id", "provider_id", "model_id", "template_version"):
            _require_string(run[field], "model_run_lineage_invalid")
        _require_string(run["repair_reason"], "model_run_lineage_invalid", nullable=True)
        _require_string(run["validation_status"], "model_run_lineage_invalid", nullable=True)
        if (
            run["workspace_id"] != source["workspace_id"]
            or run.get("parent_run_id") != previous_id
            or run["id"] in run_ids
            or run["operation"] != "generate"
            or run["status"] not in {"running", "succeeded", "failed"}
            or not isinstance(run["input_hashes"], list)
            or any(
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in run["input_hashes"]
            )
            or not isinstance(run["attempt_number"], int)
            or isinstance(run["attempt_number"], bool)
            or run["attempt_number"] < 1
        ):
            raise EvidencePackageError("model_run_lineage_invalid")
        run_ids.add(run["id"])
        previous_id = run.get("id")
    if _node_hash("transformation", transformation) != transformation["node_hash"]:
        raise EvidencePackageError("transformation_node_hash_mismatch")

    artifact = _require_keys(
        payload["artifact"],
        {
            "id",
            "kind",
            "title",
            "statement",
            "rationale",
            "confidence",
            "valid_from",
            "valid_to",
            "transformation_node_hash",
            "citation_node_hashes",
            "node_hash",
        },
        "artifact_node_invalid",
    )
    if (
        artifact["kind"] not in ARTIFACT_KINDS
        or not isinstance(artifact["confidence"], (int, float))
        or isinstance(artifact["confidence"], bool)
        or not 0 <= artifact["confidence"] <= 1
    ):
        raise EvidencePackageError("artifact_content_invalid")
    _require_string(artifact["id"], "artifact_content_invalid")
    _require_string(artifact["title"], "artifact_content_invalid")
    _require_string(artifact["statement"], "artifact_content_invalid")
    _require_string(artifact["rationale"], "artifact_content_invalid", nullable=True)
    _require_datetime(artifact["valid_from"], "artifact_datetime_invalid", nullable=True)
    _require_datetime(artifact["valid_to"], "artifact_datetime_invalid", nullable=True)
    _require_hash(artifact["node_hash"], "artifact_node_hash_invalid")
    if (
        artifact["transformation_node_hash"] != transformation["node_hash"]
        or artifact["citation_node_hashes"] != citation_hashes
    ):
        raise EvidencePackageError("artifact_parents_invalid")
    if _node_hash("decision-artifact", artifact) != artifact["node_hash"]:
        raise EvidencePackageError("artifact_node_hash_mismatch")

    review = _require_keys(
        payload["review"],
        {"artifact_node_hash", "status", "created_at", "updated_at", "node_hash"},
        "review_node_invalid",
    )
    if review["status"] not in REVIEW_STATUSES:
        raise EvidencePackageError("review_status_invalid")
    _require_datetime(review["created_at"], "review_datetime_invalid")
    _require_datetime(review["updated_at"], "review_datetime_invalid")
    _require_hash(review["node_hash"], "review_node_hash_invalid")
    if review["artifact_node_hash"] != artifact["node_hash"]:
        raise EvidencePackageError("review_parent_invalid")
    if _node_hash("review-state", review) != review["node_hash"]:
        raise EvidencePackageError("review_node_hash_mismatch")
    root_hash = _hash_envelope(
        "package-root",
        {
            "artifact_node_hash": artifact["node_hash"],
            "review_node_hash": review["node_hash"],
        },
    )
    if root_hash != manifest["root_hash"]:
        raise EvidencePackageError("root_hash_mismatch")
    return {
        "valid": True,
        "schema": manifest["schema"],
        "root_hash": root_hash,
        "artifact_id": artifact["id"],
        "citation_count": len(citations),
    }


def verify_decision_package(document: Any) -> dict[str, Any]:
    try:
        return _verify_decision_package(document)
    except EvidencePackageError:
        raise
    except Exception as exc:
        raise EvidencePackageError("package_validation_failed") from exc


def _load_zip_document(data: bytes) -> Any:
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            entries = archive.infolist()
            if len(entries) != 1:
                raise EvidencePackageError("archive_entry_count_invalid")
            entry = entries[0]
            if (
                entry.filename != PACKAGE_ARCHIVE_ENTRY
                or entry.is_dir()
                or "\\" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16)
            ):
                raise EvidencePackageError("archive_entry_invalid")
            if entry.flag_bits & 0x1:
                raise EvidencePackageError("archive_encrypted")
            if entry.compress_type != zipfile.ZIP_STORED:
                raise EvidencePackageError("archive_compression_unsupported")
            if (
                entry.file_size > MAX_PACKAGE_BYTES
                or entry.compress_size > MAX_PACKAGE_BYTES
                or entry.file_size != entry.compress_size
            ):
                raise EvidencePackageError("archive_entry_too_large")
            return json.loads(archive.read(entry), object_pairs_hook=_unique_json_object)
    except EvidencePackageError:
        raise
    except (
        OSError,
        RuntimeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        raise EvidencePackageError("archive_invalid") from exc


def load_and_verify_package(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise EvidencePackageError("package_too_large")
        if data.startswith(b"PK"):
            document = _load_zip_document(data)
        else:
            if len(data) > MAX_PACKAGE_BYTES:
                raise EvidencePackageError("package_too_large")
            document = json.loads(data, object_pairs_hook=_unique_json_object)
    except EvidencePackageError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidencePackageError("package_unreadable") from exc
    return document, verify_decision_package(document)


def _zip_package_bytes(document: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    entry = zipfile.ZipInfo(PACKAGE_ARCHIVE_ENTRY, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_STORED
    entry.create_system = 3
    entry.external_attr = 0o600 << 16
    with zipfile.ZipFile(buffer, "w", allowZip64=False) as archive:
        archive.writestr(entry, canonical_json_bytes(document) + b"\n")
    return buffer.getvalue()


def _atomic_write_bytes(path: Path, data: bytes, *, force: bool) -> None:
    path = Path(os.path.abspath(path.expanduser()))
    path.parent.mkdir(parents=True, exist_ok=True)
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
                raise EvidencePackageError("output_exists") from exc
            temporary.unlink()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def atomic_write_package(path: Path, document: dict[str, Any], *, force: bool = False) -> None:
    try:
        if path.suffix.lower() == ".zip":
            _atomic_write_bytes(path, _zip_package_bytes(document), force=force)
        else:
            atomic_write_export(path, document, force=force)
    except PortabilityError as exc:
        raise EvidencePackageError(exc.code) from exc
    except OSError as exc:
        raise EvidencePackageError("package_publish_failed") from exc


def explain_decision_package(document: dict[str, Any]) -> dict[str, Any]:
    report = verify_decision_package(document)
    payload = document["payload"]
    source = payload["source_version"]
    return {
        **report,
        "artifact": payload["artifact"],
        "review": payload["review"],
        "transformation": payload["transformation"],
        "source": {
            "workspace_id": source["workspace_id"],
            "source_id": source["source_id"],
            "source_identity_sha256": source["source_identity_sha256"],
            "source_version_id": source["source_version_id"],
            "version_number": source["version_number"],
            "content_sha256": source["content_sha256"],
            "node_hash": source["node_hash"],
        },
        "chunks": [
            {key: value for key, value in chunk.items() if key != "content"}
            for chunk in payload["chunks"]
        ],
        "citations": payload["citations"],
    }


def _changed_fields(
    before: dict[str, Any], after: dict[str, Any], *, excluded: set[str] | None = None
) -> list[str]:
    excluded = excluded or set()
    return sorted(
        key
        for key in set(before) | set(after)
        if key not in excluded and before.get(key) != after.get(key)
    )


def diff_decision_packages(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_report = verify_decision_package(before)
    after_report = verify_decision_package(after)
    before_payload = before["payload"]
    after_payload = after["payload"]
    before_citations = {citation["node_hash"] for citation in before_payload["citations"]}
    after_citations = {citation["node_hash"] for citation in after_payload["citations"]}
    before_chunks = {chunk["node_hash"] for chunk in before_payload["chunks"]}
    after_chunks = {chunk["node_hash"] for chunk in after_payload["chunks"]}
    source_excluded = {"content", "node_hash"}
    artifact_excluded = {
        "node_hash",
        "transformation_node_hash",
        "citation_node_hashes",
    }
    review_excluded = {"node_hash", "artifact_node_hash", "created_at", "updated_at"}
    return {
        "schema": "proofline-decision-evidence-package-diff-v1",
        "same_root": before_report["root_hash"] == after_report["root_hash"],
        "before_root_hash": before_report["root_hash"],
        "after_root_hash": after_report["root_hash"],
        "same_artifact_id": before_report["artifact_id"] == after_report["artifact_id"],
        "before_artifact_id": before_report["artifact_id"],
        "after_artifact_id": after_report["artifact_id"],
        "source_changed_fields": _changed_fields(
            before_payload["source_version"],
            after_payload["source_version"],
            excluded=source_excluded,
        ),
        "chunks_added": sorted(after_chunks - before_chunks),
        "chunks_removed": sorted(before_chunks - after_chunks),
        "citations_added": sorted(after_citations - before_citations),
        "citations_removed": sorted(before_citations - after_citations),
        "transformation_changed": (
            before_payload["transformation"]["node_hash"]
            != after_payload["transformation"]["node_hash"]
        ),
        "artifact_changed_fields": _changed_fields(
            before_payload["artifact"],
            after_payload["artifact"],
            excluded=artifact_excluded,
        ),
        "review_changed_fields": _changed_fields(
            before_payload["review"],
            after_payload["review"],
            excluded=review_excluded,
        ),
    }
