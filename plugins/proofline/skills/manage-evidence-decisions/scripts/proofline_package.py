#!/usr/bin/env python3
"""Dependency-free verifier for Proofline Decision Evidence Packages."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import stat
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "proofline-decision-evidence-package-v1"
REVIEW_RECEIPT_SCHEMA = "proofline-decision-review-receipt-v1"
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_PACKAGE_BYTES + 64 * 1024
MAX_REVIEW_RECEIPT_BYTES = 1024 * 1024
HASH_CHARS = frozenset("0123456789abcdef")
REVIEW_RECEIPT_KEYS = {
    "schema",
    "review_id",
    "workspace_id",
    "decision_id",
    "evidence_id",
    "finding_fingerprint",
    "cited_source_version_id",
    "cited_content_sha256",
    "current_source_version_id",
    "current_content_sha256",
    "anchor_state",
    "policy_sha256",
    "state",
    "resolution",
    "opened_at",
    "updated_at",
    "closed_at",
    "dep_root_hash",
    "receipt_hash",
}


class PackageError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def fail(code: str) -> None:
    raise PackageError(code)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def envelope(domain: str, value: Any) -> str:
    prefix = f"proofline/{domain}/v1\0".encode()
    return hashlib.sha256(prefix + canonical_bytes(value)).hexdigest()


def node_hash(kind: str, node: dict[str, Any]) -> str:
    return envelope(
        f"node/{kind}", {key: value for key, value in node.items() if key != "node_hash"}
    )


def require_object(value: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        fail(code)
    return value


def require_text(value: Any, code: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value:
        fail(code)


def require_hash(value: Any, code: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in HASH_CHARS for c in value):
        fail(code)


def require_datetime(value: Any, code: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str):
        fail(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        fail(code)
    if parsed.tzinfo is None:
        fail(code)


def verify_review(document: Any) -> dict[str, Any]:
    receipt = require_object(document, REVIEW_RECEIPT_KEYS, "receipt_shape_invalid")
    if receipt["schema"] != REVIEW_RECEIPT_SCHEMA:
        fail("schema_unsupported")
    for key, code in (
        ("review_id", "review_id_invalid"),
        ("workspace_id", "workspace_id_invalid"),
        ("decision_id", "decision_id_invalid"),
        ("evidence_id", "evidence_id_invalid"),
        ("cited_source_version_id", "source_version_id_invalid"),
        ("current_source_version_id", "source_version_id_invalid"),
    ):
        require_text(receipt[key], code)
        try:
            parsed = uuid.UUID(receipt[key])
        except ValueError:
            fail(code)
        if str(parsed) != receipt[key]:
            fail(code)
    for key, code in (
        ("finding_fingerprint", "fingerprint_invalid"),
        ("cited_content_sha256", "content_hash_invalid"),
        ("current_content_sha256", "content_hash_invalid"),
        ("policy_sha256", "policy_hash_invalid"),
        ("dep_root_hash", "dep_root_hash_invalid"),
        ("receipt_hash", "receipt_hash_invalid"),
    ):
        require_hash(receipt[key], code)
    if receipt["anchor_state"] not in {"moved", "ambiguous", "changed", "deleted"}:
        fail("anchor_state_invalid")
    state = receipt["state"]
    if state not in {"open", "acknowledged", "resolved", "waived", "superseded"}:
        fail("review_state_invalid")
    terminal = state in {"resolved", "waived", "superseded"}
    resolution = receipt["resolution"]
    if terminal:
        if not isinstance(resolution, str) or not resolution.strip():
            fail("resolution_invalid")
    elif resolution is not None:
        fail("resolution_invalid")
    for key in ("opened_at", "updated_at"):
        require_datetime(receipt[key], "timestamp_invalid")
    require_datetime(receipt["closed_at"], "timestamp_invalid", nullable=True)
    opened = datetime.fromisoformat(receipt["opened_at"])
    updated = datetime.fromisoformat(receipt["updated_at"])
    closed = (
        datetime.fromisoformat(receipt["closed_at"]) if receipt["closed_at"] is not None else None
    )
    if opened > updated or (terminal and (closed is None or opened > closed or closed > updated)):
        fail("timestamp_invalid")
    if not terminal and closed is not None:
        fail("timestamp_invalid")
    body = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    expected = hashlib.sha256(b"proofline/review-receipt/v1\0" + canonical_bytes(body)).hexdigest()
    if receipt["receipt_hash"] != expected:
        fail("receipt_hash_mismatch")
    return {
        "valid": True,
        "schema": REVIEW_RECEIPT_SCHEMA,
        "review_id": receipt["review_id"],
        "receipt_hash": receipt["receipt_hash"],
        "dep_root_hash": receipt["dep_root_hash"],
    }


def load_review(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        if len(data) > MAX_REVIEW_RECEIPT_BYTES:
            fail("receipt_too_large")
        document = json.loads(data, object_pairs_hook=unique_object)
    except PackageError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        fail("receipt_unreadable")
    verify_review(document)
    return document


def line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def verify(document: Any) -> dict[str, Any]:
    root = require_object(document, {"manifest", "payload"}, "package_shape_invalid")
    manifest = require_object(
        root["manifest"],
        {"schema", "created_at", "app_version", "root_hash"},
        "manifest_shape_invalid",
    )
    if manifest["schema"] != SCHEMA:
        fail("schema_unsupported")
    require_datetime(manifest["created_at"], "manifest_created_at_invalid")
    require_text(manifest["app_version"], "manifest_app_version_invalid")
    require_hash(manifest["root_hash"], "root_hash_invalid")
    payload = require_object(
        root["payload"],
        {"source_version", "chunks", "citations", "transformation", "artifact", "review"},
        "payload_shape_invalid",
    )

    source = require_object(
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
    for key in ("workspace_id", "source_id", "source_version_id", "parser_version"):
        require_text(source[key], "source_identity_invalid")
    require_hash(source["source_identity_sha256"], "source_identity_invalid")
    require_hash(source["content_sha256"], "source_content_hash_invalid")
    require_hash(source["node_hash"], "source_node_hash_invalid")
    if (
        source["source_identity_sha256"]
        != hashlib.sha256(f"source:{source['source_id']}".encode()).hexdigest()
    ):
        fail("source_identity_invalid")
    content = source["content"]
    if (
        not isinstance(content, str)
        or not isinstance(source["version_number"], int)
        or isinstance(source["version_number"], bool)
        or source["version_number"] < 1
        or not isinstance(source["content_length"], int)
        or isinstance(source["content_length"], bool)
        or source["content_length"] != len(content)
    ):
        fail("source_content_invalid")
    if hashlib.sha256(content.encode()).hexdigest() != source["content_sha256"]:
        fail("source_content_hash_mismatch")
    if node_hash("source-version", source) != source["node_hash"]:
        fail("source_node_hash_mismatch")

    chunks = payload["chunks"]
    if not isinstance(chunks, list) or not chunks:
        fail("chunks_invalid")
    chunk_hashes: list[str] = []
    chunk_ids: set[str] = set()
    ordinals: set[int] = set()
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
    for chunk in chunks:
        chunk = require_object(chunk, chunk_keys, "chunk_node_invalid")
        start, end, ordinal = chunk["start_offset"], chunk["end_offset"], chunk["ordinal"]
        require_text(chunk["id"], "chunk_identity_invalid")
        require_hash(chunk["content_sha256"], "chunk_content_hash_invalid")
        require_hash(chunk["node_hash"], "chunk_node_hash_invalid")
        if (
            chunk["id"] in chunk_ids
            or chunk["node_hash"] in chunk_hashes
            or ordinal in ordinals
            or chunk["source_node_hash"] != source["node_hash"]
            or chunk["source_id"] != source["source_id"]
            or chunk["source_version_id"] != source["source_version_id"]
            or not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal < 0
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 0 <= start < end <= len(content)
        ):
            fail("chunk_reference_invalid")
        exact = content[start:end]
        if (
            chunk["content"] != exact
            or chunk["content_sha256"] != hashlib.sha256(exact.encode()).hexdigest()
            or chunk["start_line"] != line_number(content, start)
            or chunk["end_line"] != line_number(content, end - 1)
        ):
            fail("chunk_span_invalid")
        if node_hash("chunk", chunk) != chunk["node_hash"]:
            fail("chunk_node_hash_mismatch")
        chunk_ids.add(chunk["id"])
        ordinals.add(ordinal)
        chunk_hashes.append(chunk["node_hash"])

    citations = payload["citations"]
    if not isinstance(citations, list) or not citations:
        fail("citations_invalid")
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
    for citation in citations:
        citation = require_object(citation, citation_keys, "citation_node_invalid")
        start, end = citation["start_offset"], citation["end_offset"]
        require_text(citation["id"], "citation_identity_invalid")
        require_hash(citation["quote_sha256"], "citation_quote_hash_invalid")
        require_hash(citation["node_hash"], "citation_node_hash_invalid")
        expected_chunks = [
            c["node_hash"] for c in chunks if c["start_offset"] < end and c["end_offset"] > start
        ]
        if (
            citation["id"] in citation_ids
            or citation["node_hash"] in citation_hashes
            or citation["source_node_hash"] != source["node_hash"]
            or citation["chunk_node_hashes"] != expected_chunks
            or not expected_chunks
            or citation["source_id"] != source["source_id"]
            or citation["source_version_id"] != source["source_version_id"]
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 0 <= start < end <= len(content)
        ):
            fail("citation_reference_invalid")
        exact = content[start:end]
        if (
            citation["quote"] != exact
            or citation["quote_sha256"] != hashlib.sha256(exact.encode()).hexdigest()
            or citation["start_line"] != line_number(content, start)
            or citation["end_line"] != line_number(content, end - 1)
        ):
            fail("citation_span_invalid")
        if node_hash("citation", citation) != citation["node_hash"]:
            fail("citation_node_hash_mismatch")
        citation_ids.add(citation["id"])
        citation_hashes.append(citation["node_hash"])

    transformation = require_object(
        payload["transformation"],
        {"method", "parser_version", "model_runs", "input_node_hashes", "node_hash"},
        "transformation_node_invalid",
    )
    if transformation["method"] not in {"deterministic", "model"}:
        fail("transformation_method_invalid")
    if transformation["parser_version"] != source["parser_version"]:
        fail("transformation_parser_invalid")
    expected_inputs = [source["node_hash"], *chunk_hashes, *citation_hashes]
    if transformation["input_node_hashes"] != expected_inputs:
        fail("transformation_inputs_invalid")
    if not isinstance(transformation["model_runs"], list) or (
        (transformation["method"] == "model") != bool(transformation["model_runs"])
    ):
        fail("model_run_lineage_invalid")
    require_hash(transformation["node_hash"], "transformation_node_hash_invalid")
    if node_hash("transformation", transformation) != transformation["node_hash"]:
        fail("transformation_node_hash_mismatch")

    artifact = require_object(
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
    if artifact["kind"] not in {"decision", "assumption", "constraint", "alternative"}:
        fail("artifact_content_invalid")
    for key in ("id", "title", "statement"):
        require_text(artifact[key], "artifact_content_invalid")
    require_text(artifact["rationale"], "artifact_content_invalid", nullable=True)
    confidence = artifact["confidence"]
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        fail("artifact_content_invalid")
    require_datetime(artifact["valid_from"], "artifact_datetime_invalid", nullable=True)
    require_datetime(artifact["valid_to"], "artifact_datetime_invalid", nullable=True)
    require_hash(artifact["node_hash"], "artifact_node_hash_invalid")
    if (
        artifact["transformation_node_hash"] != transformation["node_hash"]
        or artifact["citation_node_hashes"] != citation_hashes
    ):
        fail("artifact_parents_invalid")
    if node_hash("decision-artifact", artifact) != artifact["node_hash"]:
        fail("artifact_node_hash_mismatch")

    review = require_object(
        payload["review"],
        {"artifact_node_hash", "status", "created_at", "updated_at", "node_hash"},
        "review_node_invalid",
    )
    if review["status"] not in {"candidate", "active", "accepted", "rejected", "obsolete"}:
        fail("review_status_invalid")
    require_datetime(review["created_at"], "review_datetime_invalid")
    require_datetime(review["updated_at"], "review_datetime_invalid")
    require_hash(review["node_hash"], "review_node_hash_invalid")
    if review["artifact_node_hash"] != artifact["node_hash"]:
        fail("review_parent_invalid")
    if node_hash("review-state", review) != review["node_hash"]:
        fail("review_node_hash_mismatch")
    root_hash = envelope(
        "package-root",
        {"artifact_node_hash": artifact["node_hash"], "review_node_hash": review["node_hash"]},
    )
    if root_hash != manifest["root_hash"]:
        fail("root_hash_mismatch")
    return {
        "valid": True,
        "schema": SCHEMA,
        "root_hash": root_hash,
        "artifact_id": artifact["id"],
        "citation_count": len(citations),
    }


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail("duplicate_json_key")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        if len(data) > MAX_ARCHIVE_BYTES:
            fail("package_too_large")
        if data.startswith(b"PK"):
            with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
                entries = archive.infolist()
                if len(entries) != 1:
                    fail("archive_entry_count_invalid")
                entry = entries[0]
                if (
                    entry.filename != "evidence.json"
                    or entry.is_dir()
                    or "\\" in entry.filename
                    or stat.S_ISLNK(entry.external_attr >> 16)
                ):
                    fail("archive_entry_invalid")
                if entry.flag_bits & 1:
                    fail("archive_encrypted")
                if entry.compress_type != zipfile.ZIP_STORED:
                    fail("archive_compression_unsupported")
                if entry.file_size > MAX_PACKAGE_BYTES or entry.file_size != entry.compress_size:
                    fail("archive_entry_too_large")
                document = json.loads(archive.read(entry), object_pairs_hook=unique_object)
        else:
            if len(data) > MAX_PACKAGE_BYTES:
                fail("package_too_large")
            document = json.loads(data, object_pairs_hook=unique_object)
    except PackageError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile):
        fail("package_unreadable")
    verify(document)
    return document


def explanation(document: dict[str, Any]) -> dict[str, Any]:
    report = verify(document)
    payload = document["payload"]
    return {
        **report,
        "artifact": {
            key: payload["artifact"][key]
            for key in (
                "id",
                "kind",
                "title",
                "statement",
                "rationale",
                "confidence",
                "valid_from",
                "valid_to",
            )
        },
        "review": {key: payload["review"][key] for key in ("status", "created_at", "updated_at")},
        "source": {
            key: payload["source_version"][key]
            for key in (
                "source_id",
                "source_version_id",
                "version_number",
                "content_sha256",
                "node_hash",
            )
        },
        "citations": [
            {
                key: item[key]
                for key in (
                    "id",
                    "start_offset",
                    "end_offset",
                    "start_line",
                    "end_line",
                    "quote_sha256",
                    "node_hash",
                )
            }
            for item in payload["citations"]
        ],
    }


def changed_fields(before: dict[str, Any], after: dict[str, Any], excluded: set[str]) -> list[str]:
    return sorted(
        key
        for key in set(before) | set(after)
        if key not in excluded and before.get(key) != after.get(key)
    )


def difference(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    left, right = verify(before), verify(after)
    a, b = before["payload"], after["payload"]
    left_chunks = {x["node_hash"] for x in a["chunks"]}
    right_chunks = {x["node_hash"] for x in b["chunks"]}
    left_cites = {x["node_hash"] for x in a["citations"]}
    right_cites = {x["node_hash"] for x in b["citations"]}
    return {
        "schema": "proofline-decision-evidence-package-diff-v1",
        "same_root": left["root_hash"] == right["root_hash"],
        "before_root_hash": left["root_hash"],
        "after_root_hash": right["root_hash"],
        "same_artifact_id": left["artifact_id"] == right["artifact_id"],
        "before_artifact_id": left["artifact_id"],
        "after_artifact_id": right["artifact_id"],
        "source_changed_fields": changed_fields(
            a["source_version"], b["source_version"], {"content", "node_hash"}
        ),
        "chunks_added": sorted(right_chunks - left_chunks),
        "chunks_removed": sorted(left_chunks - right_chunks),
        "citations_added": sorted(right_cites - left_cites),
        "citations_removed": sorted(left_cites - right_cites),
        "transformation_changed": a["transformation"]["node_hash"]
        != b["transformation"]["node_hash"],
        "artifact_changed_fields": changed_fields(
            a["artifact"],
            b["artifact"],
            {"node_hash", "transformation_node_hash", "citation_node_hashes"},
        ),
        "review_changed_fields": changed_fields(
            a["review"],
            b["review"],
            {"node_hash", "artifact_node_hash", "created_at", "updated_at"},
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "explain", "verify-review"):
        item = commands.add_parser(name)
        item.add_argument("path", type=Path)
    item = commands.add_parser("diff")
    item.add_argument("before", type=Path)
    item.add_argument("after", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            result = verify(load(args.path))
        elif args.command == "explain":
            result = explanation(load(args.path))
        elif args.command == "verify-review":
            result = verify_review(load_review(args.path))
        else:
            result = difference(load(args.before), load(args.after))
    except PackageError as exc:
        print(json.dumps({"valid": False, "error": exc.code}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
