from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from .portable_schema import (
    ANCHOR_STATES,
    BINDING_STATES,
    DECISION_REVIEW_STATES,
    EXTRACTION_METHODS,
    INGESTION_STAGES,
    MAX_CONTENT_LENGTH,
    MAX_COUNTER,
    MEMORY_KINDS,
    MEMORY_STATUSES,
    MODEL_OPERATIONS,
    MODEL_RUN_STATUSES,
    MODEL_VALIDATION_STATUSES,
    PAYLOAD_KEYS,
    PROPOSAL_STATUSES,
    SOURCE_KINDS,
    SOURCE_STATUSES,
    STUDIO_KINDS,
    STUDY_RATINGS,
    STUDY_STATES,
    TERMINAL_INGESTION_STATES,
    PortabilityError,
    _iso,
)


def _require_mapping(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PortabilityError(code)
    return value


def _require_array(value: Any, code: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PortabilityError(code)
    return value


def _lookup(items: dict[str, dict[str, Any]], key: Any) -> Any:
    return items.get(key) if isinstance(key, str) else None


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
        _require_string(item["anchor_version"], "invalid_evidence_anchor", max_length=40)
        if not isinstance(item["section_path"], list) or not all(
            isinstance(value, str) and len(value) <= 300 for value in item["section_path"]
        ):
            raise PortabilityError("invalid_evidence_anchor")
        _require_hash(item["prefix_sha256"], "invalid_evidence_anchor")
        _require_hash(item["suffix_sha256"], "invalid_evidence_anchor")
        _require_id(item["binding_root_id"], "invalid_evidence_binding")
        _require_enum(item["binding_state"], BINDING_STATES, "invalid_evidence_binding")
        _require_datetime(item["superseded_at"], "invalid_evidence_binding", nullable=True)
        _require_id(item["superseded_by_id"], "invalid_evidence_binding", nullable=True)

    for review in arrays["decision_reviews"]:
        for field in (
            "workspace_id",
            "decision_id",
            "evidence_id",
            "cited_source_version_id",
            "current_source_version_id",
        ):
            _require_id(review[field], "invalid_decision_review_reference")
        _require_hash(review["finding_fingerprint"], "invalid_decision_review_fingerprint")
        _require_enum(review["anchor_state"], ANCHOR_STATES, "invalid_decision_review_state")
        _require_enum(review["severity"], {"warning", "error"}, "invalid_decision_review_state")
        _require_hash(review["policy_hash"], "invalid_decision_review_policy")
        for field in ("candidate_start_offset", "candidate_end_offset"):
            _require_integer(
                review[field],
                "invalid_decision_review_candidate",
                maximum=MAX_CONTENT_LENGTH,
                nullable=True,
            )
        for field in ("candidate_start_line", "candidate_end_line"):
            _require_integer(
                review[field],
                "invalid_decision_review_candidate",
                minimum=1,
                nullable=True,
            )
        _require_enum(review["state"], DECISION_REVIEW_STATES, "invalid_decision_review_state")
        _require_string(
            review["resolution"],
            "invalid_decision_review_resolution",
            max_length=40,
            nullable=True,
        )
        _require_string(review["actor"], "invalid_decision_review_actor", max_length=100)
        _require_string(
            review["note"],
            "invalid_decision_review_note",
            max_length=2_000,
            nullable=True,
            allow_empty=True,
        )
        _require_datetime(review["opened_at"], "invalid_decision_review_datetime")
        _require_datetime(review["updated_at"], "invalid_decision_review_datetime")
        _require_datetime(review["closed_at"], "invalid_decision_review_datetime", nullable=True)

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
            {"source", "memory", "decision", "action_proposal", "decision_review"},
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
