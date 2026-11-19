from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from .anchors import build_evidence_anchor
from .decision_reviews import review_fingerprint
from .portable_schema import (
    ITEM_KEYS,
    MANIFEST_KEYS,
    PAYLOAD_KEYS,
    PORTABLE_EXPORT_SCHEMA,
    TERMINAL_INGESTION_STATES,
    TERMINAL_REVIEW_STATES,
    PortabilityError,
    normalize_portable_export,
    payload_sha256,
)
from .portable_validation import (
    _by_id,
    _lookup,
    _require_array,
    _require_canonical_order,
    _require_integer,
    _require_mapping,
    _validate_scalar_fields,
)


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
    decision_reviews = _by_id(arrays["decision_reviews"], "invalid_decision_review_id")
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
    version_hashes: dict[str, set[Any]] = {source_id: set() for source_id in sources}
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
        current = _lookup(versions, source.get("current_version_id"))
        if not current or current.get("source_id") != source["id"]:
            raise PortabilityError("invalid_current_version")
        if current.get("version_number") != max(version_numbers[source["id"]], default=0):
            raise PortabilityError("current_version_not_latest")

    chunk_ordinals: set[tuple[str, int]] = set()
    for chunk in chunks.values():
        version = _lookup(versions, chunk.get("source_version_id"))
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
        version = _lookup(versions, memory.get("source_version_id"))
        if memory.get("source_id") not in sources or not version:
            raise PortabilityError("invalid_memory_reference")
        if version.get("source_id") != memory.get("source_id"):
            raise PortabilityError("invalid_memory_reference")
        model_run_id = memory.get("model_run_id")
        if model_run_id is not None and model_run_id not in model_runs:
            raise PortabilityError("invalid_memory_model_reference")

    for item in evidence.values():
        memory = _lookup(memories, item.get("memory_id"))
        version = _lookup(versions, item.get("source_version_id"))
        if not memory or not version or item.get("source_id") not in sources:
            raise PortabilityError("invalid_evidence_reference")
        if memory.get("source_id") != item.get("source_id") or version.get("source_id") != item.get(
            "source_id"
        ):
            raise PortabilityError("invalid_evidence_reference")
        if item["binding_state"] == "active" and memory.get("source_version_id") != item.get(
            "source_version_id"
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
        anchor = build_evidence_anchor(content, start, end)
        if (
            item["anchor_version"] != anchor.version
            or item["section_path"] != list(anchor.section_path)
            or item["prefix_sha256"] != anchor.prefix_sha256
            or item["suffix_sha256"] != anchor.suffix_sha256
        ):
            raise PortabilityError("evidence_anchor_mismatch")

    active_bindings: dict[tuple[str, str], int] = {}
    for item in evidence.values():
        root = _lookup(evidence, item["binding_root_id"])
        if root is None or root["memory_id"] != item["memory_id"]:
            raise PortabilityError("invalid_evidence_binding")
        key = (item["memory_id"], item["binding_root_id"])
        if item["binding_state"] == "active":
            if item["superseded_at"] is not None or item["superseded_by_id"] is not None:
                raise PortabilityError("invalid_evidence_binding")
            active_bindings[key] = active_bindings.get(key, 0) + 1
        else:
            replacement = evidence.get(item["superseded_by_id"])
            if (
                item["superseded_at"] is None
                or replacement is None
                or replacement["memory_id"] != item["memory_id"]
                or replacement["binding_root_id"] != item["binding_root_id"]
                or replacement["id"] == item["id"]
            ):
                raise PortabilityError("invalid_evidence_binding")
    roots = {(item["memory_id"], item["binding_root_id"]) for item in evidence.values()}
    if any(active_bindings.get(key) != 1 for key in roots):
        raise PortabilityError("invalid_evidence_binding")
    for evidence_id in evidence:
        evidence_visited: set[str] = set()
        evidence_cursor: str | None = evidence_id
        while evidence_cursor is not None:
            if evidence_cursor in evidence_visited:
                raise PortabilityError("invalid_evidence_binding")
            evidence_visited.add(evidence_cursor)
            evidence_cursor = evidence[evidence_cursor]["superseded_by_id"]

    evidence_counts = {memory_id: 0 for memory_id in memories}
    for item in evidence.values():
        if item["binding_state"] == "active":
            evidence_counts[item["memory_id"]] += 1
    for memory in memories.values():
        if evidence_counts[memory["id"]] < 1:
            raise PortabilityError("memory_without_evidence")
        if memory.get("extraction_method") == "model" and memory.get("model_run_id") is None:
            raise PortabilityError("invalid_memory_model_reference")

    fingerprints: set[str] = set()
    for review in decision_reviews.values():
        decision = memories.get(review["decision_id"])
        cited_evidence = evidence.get(review["evidence_id"])
        cited_version = versions.get(review["cited_source_version_id"])
        current_version = versions.get(review["current_source_version_id"])
        if (
            review["workspace_id"] not in workspaces
            or decision is None
            or cited_evidence is None
            or cited_version is None
            or current_version is None
            or sources[decision["source_id"]]["workspace_id"] != review["workspace_id"]
            or cited_evidence["memory_id"] != decision["id"]
            or cited_evidence["source_version_id"] != cited_version["id"]
            or cited_version["source_id"] != decision["source_id"]
            or current_version["source_id"] != decision["source_id"]
        ):
            raise PortabilityError("invalid_decision_review_reference")
        expected_fingerprint = review_fingerprint(
            decision_id=review["decision_id"],
            evidence_id=review["evidence_id"],
            cited_source_version_id=review["cited_source_version_id"],
            current_source_version_id=review["current_source_version_id"],
            anchor_state=review["anchor_state"],
        )
        if (
            review["finding_fingerprint"] != expected_fingerprint
            or expected_fingerprint in fingerprints
        ):
            raise PortabilityError("invalid_decision_review_fingerprint")
        fingerprints.add(expected_fingerprint)
        opened = datetime.fromisoformat(review["opened_at"])
        updated = datetime.fromisoformat(review["updated_at"])
        closed = (
            datetime.fromisoformat(review["closed_at"]) if review["closed_at"] is not None else None
        )
        terminal = review["state"] in TERMINAL_REVIEW_STATES
        if (
            opened > updated
            or (
                terminal
                and (
                    closed is None
                    or not review["resolution"]
                    or opened > closed
                    or closed > updated
                )
            )
            or (not terminal and (closed is not None or review["resolution"] is not None))
        ):
            raise PortabilityError("invalid_decision_review_state")
        candidate = (
            review["candidate_start_offset"],
            review["candidate_end_offset"],
            review["candidate_start_line"],
            review["candidate_end_line"],
        )
        if any(value is None for value in candidate):
            if any(value is not None for value in candidate):
                raise PortabilityError("invalid_decision_review_candidate")
        else:
            start, end, start_line, end_line = candidate
            content = current_version["content"]
            if (
                start < 0
                or end <= start
                or end > len(content)
                or start_line != content.count("\n", 0, start) + 1
                or end_line != content.count("\n", 0, end - 1) + 1
            ):
                raise PortabilityError("invalid_decision_review_candidate")

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
        elif object_type == "decision_review":
            valid = object_id in decision_reviews
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
            version = _lookup(versions, version_id)
            if not version or (source_id is not None and version.get("source_id") != source_id):
                raise PortabilityError("invalid_job_reference")

    for card in study_cards.values():
        version = _lookup(versions, card.get("source_version_id"))
        source = _lookup(sources, card.get("source_id"))
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
        proposal = _lookup(proposals, citation["proposal_id"])
        source = _lookup(sources, citation["source_id"])
        version = _lookup(versions, citation["source_version_id"])
        chunk = _lookup(chunks, citation["chunk_id"])
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
        source = _lookup(sources, artifact["source_id"])
        version = _lookup(versions, artifact["source_version_id"])
        if (
            artifact["workspace_id"] not in workspaces
            or source is None
            or version is None
            or source["workspace_id"] != artifact["workspace_id"]
            or version["source_id"] != source["id"]
        ):
            raise PortabilityError("invalid_studio_reference")
    for citation in studio_citations.values():
        artifact = _lookup(artifacts, citation["artifact_id"])
        version = _lookup(versions, citation["source_version_id"])
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
