from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .anchors import build_evidence_anchor
from .ingestion import chunk_markdown
from .models import (
    DEFAULT_WORKSPACE_ID,
)

PORTABLE_EXPORT_SCHEMA = "proofline-portable-export-v3"
PORTABLE_EXPORT_V2_SCHEMA = "proofline-portable-export-v2"
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
ANCHOR_STATES = {"moved", "ambiguous", "changed", "deleted"}
BINDING_STATES = {"active", "superseded"}
DECISION_REVIEW_STATES = {"open", "acknowledged", "resolved", "waived", "superseded"}
TERMINAL_REVIEW_STATES = {"resolved", "waived", "superseded"}
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
V2_PAYLOAD_KEYS = set(PAYLOAD_KEYS)
V2_ITEM_KEYS = {key: set(value) for key, value in ITEM_KEYS.items()}
PAYLOAD_KEYS.add("decision_reviews")
ITEM_KEYS["evidence"].update(
    {
        "anchor_version",
        "section_path",
        "prefix_sha256",
        "suffix_sha256",
        "binding_root_id",
        "binding_state",
        "superseded_at",
        "superseded_by_id",
    }
)
ITEM_KEYS["decision_reviews"] = {
    "id",
    "workspace_id",
    "decision_id",
    "evidence_id",
    "cited_source_version_id",
    "current_source_version_id",
    "finding_fingerprint",
    "anchor_state",
    "severity",
    "policy_hash",
    "candidate_start_offset",
    "candidate_end_offset",
    "candidate_start_line",
    "candidate_end_line",
    "state",
    "resolution",
    "actor",
    "note",
    "opened_at",
    "updated_at",
    "closed_at",
}
LEGACY_ITEM_KEYS = {key: set(V2_ITEM_KEYS[key]) for key in LEGACY_PAYLOAD_KEYS}
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
    """Upgrade verified v1/v2 shapes in memory without mutating caller data."""
    if not isinstance(document, dict):
        return document
    manifest = document.get("manifest")
    payload = document.get("payload")
    if not isinstance(manifest, dict):
        return document
    schema = manifest.get("schema")
    if schema == PORTABLE_EXPORT_SCHEMA:
        return document
    if schema not in {LEGACY_PORTABLE_EXPORT_SCHEMA, PORTABLE_EXPORT_V2_SCHEMA}:
        return document
    expected_keys = (
        LEGACY_PAYLOAD_KEYS if schema == LEGACY_PORTABLE_EXPORT_SCHEMA else V2_PAYLOAD_KEYS
    )
    expected_items = LEGACY_ITEM_KEYS if schema == LEGACY_PORTABLE_EXPORT_SCHEMA else V2_ITEM_KEYS
    if (
        set(document) != {"manifest", "payload"}
        or set(manifest) != MANIFEST_KEYS
        or not isinstance(payload, dict)
        or set(payload) != expected_keys
    ):
        raise PortabilityError("unexpected_fields")
    expected_hash = manifest.get("payload_sha256")
    if not isinstance(expected_hash, str) or payload_sha256(payload) != expected_hash:
        raise PortabilityError("payload_hash_mismatch")
    if any(
        not isinstance(items, list)
        or any(not isinstance(item, dict) or set(item) != expected_items[key] for item in items)
        for key, items in payload.items()
    ):
        raise PortabilityError("unexpected_fields")
    original_counts = manifest.get("counts")
    if not isinstance(original_counts, dict) or original_counts != {
        key: len(payload[key]) for key in sorted(expected_keys)
    }:
        raise PortabilityError("count_mismatch")

    upgraded = copy.deepcopy(document)
    upgraded_payload = upgraded["payload"]
    if schema == LEGACY_PORTABLE_EXPORT_SCHEMA:
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
                chunks.append(
                    {
                        "id": str(
                            uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"proofline:portable-v1-chunk:{version['id']}:{ordinal}",
                            )
                        ),
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
        for key in V2_PAYLOAD_KEYS - LEGACY_PAYLOAD_KEYS - {"workspaces", "chunks"}:
            upgraded_payload[key] = []

    versions = {item["id"]: item for item in upgraded_payload["source_versions"]}
    for item in upgraded_payload["evidence"]:
        version = versions.get(item["source_version_id"])
        if version is None:
            raise PortabilityError("invalid_evidence_reference")
        anchor = build_evidence_anchor(version["content"], item["start_offset"], item["end_offset"])
        item.update(
            {
                "anchor_version": anchor.version,
                "section_path": list(anchor.section_path),
                "prefix_sha256": anchor.prefix_sha256,
                "suffix_sha256": anchor.suffix_sha256,
                "binding_root_id": item["id"],
                "binding_state": "active",
                "superseded_at": None,
                "superseded_by_id": None,
            }
        )
    upgraded_payload["decision_reviews"] = []
    upgraded["manifest"]["schema"] = PORTABLE_EXPORT_SCHEMA
    upgraded["manifest"]["payload_sha256"] = payload_sha256(upgraded_payload)
    upgraded["manifest"]["counts"] = {
        key: len(upgraded_payload[key]) for key in sorted(PAYLOAD_KEYS)
    }
    return upgraded
