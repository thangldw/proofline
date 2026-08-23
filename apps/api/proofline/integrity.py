from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime

from sqlalchemy import Connection, Engine, text

from .anchors import build_evidence_anchor
from .backup import REQUIRED_CORE_TABLES
from .decision_reviews import review_fingerprint
from .migrations import MIGRATIONS


class IntegrityVerificationError(RuntimeError):
    """A semantic-integrity failure identified only by a content-free code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise IntegrityVerificationError(code)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _verify_sqlite_structure(connection: Connection) -> None:
    quick = [row[0] for row in connection.exec_driver_sql("PRAGMA quick_check").fetchall()]
    if quick != ["ok"]:
        _fail("sqlite_quick_check_failed")
    integrity = [row[0] for row in connection.exec_driver_sql("PRAGMA integrity_check").fetchall()]
    if integrity != ["ok"]:
        _fail("sqlite_integrity_check_failed")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchone() is not None:
        _fail("foreign_key_check_failed")
    tables = {
        row[0]
        for row in connection.execute(
            text("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        )
    }
    if not REQUIRED_CORE_TABLES.issubset(tables):
        _fail("required_schema_missing")
    versions = {
        row[0]
        for row in connection.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        )
    }
    expected_versions = {version for version, _description, _migration in MIGRATIONS}
    if versions != expected_versions:
        _fail("migration_version_mismatch")


def _verify_sources_and_versions(connection: Connection) -> tuple[dict, dict]:
    sources = {
        row["id"]: row
        for row in connection.execute(
            text(
                "SELECT id, workspace_id, content, content_hash, current_version_id "
                "FROM sources ORDER BY id"
            )
        ).mappings()
    }
    versions = {
        row["id"]: row
        for row in connection.execute(
            text(
                "SELECT id, source_id, content_hash, content, version_number, content_length "
                "FROM source_versions ORDER BY source_id, version_number, id"
            )
        ).mappings()
    }
    numbers: dict[str, list[int]] = defaultdict(list)
    for version in versions.values():
        if version["source_id"] not in sources:
            _fail("source_version_source_missing")
        if version["content_hash"] != _hash(version["content"]):
            _fail("source_version_hash_mismatch")
        if version["content_length"] != len(version["content"]):
            _fail("source_version_length_mismatch")
        numbers[version["source_id"]].append(version["version_number"])
    for source_id, values in numbers.items():
        if values != list(range(1, len(values) + 1)):
            _fail("source_version_sequence_invalid")
        if len(values) != len(set(values)):
            _fail("source_version_sequence_invalid")
        if source_id not in sources:
            _fail("source_version_source_missing")
    for source in sources.values():
        if source["content_hash"] != _hash(f"source:{source['id']}"):
            _fail("source_identity_hash_mismatch")
        current = versions.get(source["current_version_id"])
        if current is None or current["source_id"] != source["id"]:
            _fail("source_current_version_invalid")
        if current["version_number"] != max(numbers[source["id"]], default=0):
            _fail("source_current_version_not_latest")
        if source["content"] != current["content"]:
            _fail("source_current_content_mismatch")
    return sources, versions


def _valid_span(content: str, row: dict) -> bool:
    start = row["start_offset"]
    end = row["end_offset"]
    return (
        isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start < end <= len(content)
        and row["start_line"] == _line_number(content, start)
        and row["end_line"] == _line_number(content, end - 1)
    )


def _verify_chunks(connection: Connection, versions: dict) -> dict:
    chunks = {
        row["id"]: row
        for row in connection.execute(
            text(
                "SELECT id, source_id, source_version_id, ordinal, content, start_offset, "
                "end_offset, start_line, end_line FROM chunks "
                "ORDER BY source_version_id, ordinal, id"
            )
        ).mappings()
    }
    ordinals: dict[str, list[int]] = defaultdict(list)
    for chunk in chunks.values():
        version = versions.get(chunk["source_version_id"])
        if version is None or version["source_id"] != chunk["source_id"]:
            _fail("chunk_ownership_invalid")
        if not _valid_span(version["content"], chunk):
            _fail("chunk_span_invalid")
        if version["content"][chunk["start_offset"] : chunk["end_offset"]] != chunk["content"]:
            _fail("chunk_content_mismatch")
        ordinals[chunk["source_version_id"]].append(chunk["ordinal"])
    for values in ordinals.values():
        if values != list(range(len(values))):
            _fail("chunk_ordinal_sequence_invalid")
    return chunks


def _verify_memories_and_evidence(
    connection: Connection, sources: dict, versions: dict
) -> tuple[dict, dict]:
    model_runs = {
        row["id"]: row["parent_run_id"]
        for row in connection.execute(
            text("SELECT id, parent_run_id FROM model_runs ORDER BY id")
        ).mappings()
    }
    for run_id in model_runs:
        visited: set[str] = set()
        cursor: str | None = run_id
        while cursor is not None:
            if cursor in visited or cursor not in model_runs:
                _fail("model_run_lineage_invalid")
            visited.add(cursor)
            cursor = model_runs[cursor]
    memories = {
        row["id"]: row
        for row in connection.execute(
            text(
                "SELECT id, source_id, source_version_id, extraction_method, model_run_id "
                "FROM decisions ORDER BY id"
            )
        ).mappings()
    }
    for memory in memories.values():
        version = versions.get(memory["source_version_id"])
        if (
            memory["source_id"] not in sources
            or version is None
            or version["source_id"] != memory["source_id"]
        ):
            _fail("memory_ownership_invalid")
        if memory["extraction_method"] == "model" and memory["model_run_id"] not in model_runs:
            _fail("memory_model_run_missing")

    evidence_counts: dict[str, int] = defaultdict(int)
    evidence_rows = {
        row["id"]: row
        for row in connection.execute(
            text(
                "SELECT id, decision_id, source_id, source_version_id, quote, quote_hash, "
                "start_offset, end_offset, start_line, end_line, anchor_version, "
                "section_path, prefix_sha256, suffix_sha256, binding_root_id, "
                "binding_state, superseded_at, superseded_by_id FROM evidence ORDER BY id"
            )
        ).mappings()
    }
    active_bindings: dict[tuple[str, str], int] = defaultdict(int)
    for evidence in evidence_rows.values():
        version = versions.get(evidence["source_version_id"])
        if evidence["decision_id"] not in memories:
            _fail("evidence_memory_missing")
        memory = memories[evidence["decision_id"]]
        if evidence["source_id"] != memory["source_id"]:
            _fail("evidence_memory_ownership_invalid")
        if (
            evidence["binding_state"] == "active"
            and evidence["source_version_id"] != memory["source_version_id"]
        ):
            _fail("evidence_memory_ownership_invalid")
        if (
            evidence["source_id"] not in sources
            or version is None
            or version["source_id"] != evidence["source_id"]
        ):
            _fail("evidence_ownership_invalid")
        if not _valid_span(version["content"], evidence):
            _fail("evidence_span_invalid")
        quote = evidence["quote"]
        if version["content"][evidence["start_offset"] : evidence["end_offset"]] != quote:
            _fail("evidence_quote_mismatch")
        if evidence["quote_hash"] != _hash(quote):
            _fail("evidence_quote_hash_mismatch")
        try:
            section_path = json.loads(evidence["section_path"])
        except (TypeError, json.JSONDecodeError):
            _fail("evidence_anchor_invalid")
        anchor = build_evidence_anchor(
            version["content"], evidence["start_offset"], evidence["end_offset"]
        )
        if (
            evidence["anchor_version"] != anchor.version
            or section_path != list(anchor.section_path)
            or evidence["prefix_sha256"] != anchor.prefix_sha256
            or evidence["suffix_sha256"] != anchor.suffix_sha256
        ):
            _fail("evidence_anchor_mismatch")
        root = evidence_rows.get(evidence["binding_root_id"])
        if root is None or root["decision_id"] != evidence["decision_id"]:
            _fail("evidence_binding_invalid")
        binding_key = (evidence["decision_id"], evidence["binding_root_id"])
        if evidence["binding_state"] == "active":
            if evidence["superseded_at"] is not None or evidence["superseded_by_id"] is not None:
                _fail("evidence_binding_invalid")
            active_bindings[binding_key] += 1
            evidence_counts[evidence["decision_id"]] += 1
        elif evidence["binding_state"] == "superseded":
            replacement = evidence_rows.get(evidence["superseded_by_id"])
            if (
                evidence["superseded_at"] is None
                or replacement is None
                or replacement["decision_id"] != evidence["decision_id"]
                or replacement["binding_root_id"] != evidence["binding_root_id"]
                or replacement["id"] == evidence["id"]
            ):
                _fail("evidence_binding_invalid")
        else:
            _fail("evidence_binding_invalid")
    roots = {
        (evidence["decision_id"], evidence["binding_root_id"])
        for evidence in evidence_rows.values()
    }
    if any(active_bindings[key] != 1 for key in roots):
        _fail("evidence_binding_invalid")
    for evidence_id in evidence_rows:
        visited: set[str] = set()
        cursor: str | None = evidence_id
        while cursor is not None:
            if cursor in visited:
                _fail("evidence_binding_cycle")
            visited.add(cursor)
            cursor = evidence_rows[cursor]["superseded_by_id"]
    if any(evidence_counts[memory_id] == 0 for memory_id in memories):
        _fail("memory_evidence_missing")
    return memories, evidence_rows


def _parse_database_datetime(value: str | None, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _fail("decision_review_datetime_invalid")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        _fail("decision_review_datetime_invalid")


def _verify_decision_reviews(
    connection: Connection,
    sources: dict,
    versions: dict,
    memories: dict,
    evidence_rows: dict,
) -> dict:
    reviews = {
        row["id"]: row
        for row in connection.execute(
            text(
                "SELECT id, workspace_id, decision_id, evidence_id, "
                "cited_source_version_id, current_source_version_id, finding_fingerprint, "
                "anchor_state, severity, policy_hash, candidate_start_offset, "
                "candidate_end_offset, candidate_start_line, candidate_end_line, state, "
                "resolution, actor, note, opened_at, updated_at, closed_at "
                "FROM decision_reviews ORDER BY id"
            )
        ).mappings()
    }
    fingerprints: set[str] = set()
    terminal_states = {"resolved", "waived", "superseded"}
    allowed_states = {"open", "acknowledged", *terminal_states}
    for review in reviews.values():
        memory = memories.get(review["decision_id"])
        evidence = evidence_rows.get(review["evidence_id"])
        cited = versions.get(review["cited_source_version_id"])
        current = versions.get(review["current_source_version_id"])
        if (
            memory is None
            or evidence is None
            or cited is None
            or current is None
            or sources[memory["source_id"]]["workspace_id"] != review["workspace_id"]
            or evidence["decision_id"] != memory["id"]
            or evidence["source_version_id"] != cited["id"]
            or cited["source_id"] != memory["source_id"]
            or current["source_id"] != memory["source_id"]
        ):
            _fail("decision_review_ownership_invalid")
        if (
            review["anchor_state"] not in {"moved", "ambiguous", "changed", "deleted"}
            or review["state"] not in allowed_states
            or review["severity"] not in {"warning", "error"}
        ):
            _fail("decision_review_state_invalid")
        expected = review_fingerprint(
            decision_id=review["decision_id"],
            evidence_id=review["evidence_id"],
            cited_source_version_id=review["cited_source_version_id"],
            current_source_version_id=review["current_source_version_id"],
            anchor_state=review["anchor_state"],
        )
        if review["finding_fingerprint"] != expected or expected in fingerprints:
            _fail("decision_review_fingerprint_invalid")
        fingerprints.add(expected)
        if (
            not isinstance(review["policy_hash"], str)
            or len(review["policy_hash"]) != 64
            or any(value not in "0123456789abcdef" for value in review["policy_hash"])
        ):
            _fail("decision_review_policy_invalid")
        opened = _parse_database_datetime(review["opened_at"])
        updated = _parse_database_datetime(review["updated_at"])
        closed = _parse_database_datetime(review["closed_at"], nullable=True)
        terminal = review["state"] in terminal_states
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
            _fail("decision_review_state_invalid")
        candidate = (
            review["candidate_start_offset"],
            review["candidate_end_offset"],
            review["candidate_start_line"],
            review["candidate_end_line"],
        )
        if any(value is None for value in candidate):
            if any(value is not None for value in candidate):
                _fail("decision_review_candidate_invalid")
        else:
            start, end, start_line, end_line = candidate
            content = current["content"]
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end <= start
                or end > len(content)
                or start_line != _line_number(content, start)
                or end_line != _line_number(content, end - 1)
            ):
                _fail("decision_review_candidate_invalid")
    return reviews


def _verify_audit_references(
    connection: Connection, sources: dict, memories: dict, reviews: dict
) -> None:
    proposals = {
        row["id"]: row["workspace_id"]
        for row in connection.execute(
            text("SELECT id, workspace_id FROM action_proposals ORDER BY id")
        ).mappings()
    }
    for event in connection.execute(
        text("SELECT workspace_id, object_type, object_id FROM audit_events ORDER BY id")
    ).mappings():
        if event["object_type"] == "source":
            target = sources.get(event["object_id"])
            workspace_id = target["workspace_id"] if target else None
        elif event["object_type"] in {"memory", "decision"}:
            memory = memories.get(event["object_id"])
            workspace_id = sources[memory["source_id"]]["workspace_id"] if memory else None
        elif event["object_type"] == "decision_review":
            review = reviews.get(event["object_id"])
            workspace_id = review["workspace_id"] if review else None
        elif event["object_type"] == "action_proposal":
            workspace_id = proposals.get(event["object_id"])
        else:
            _fail("audit_reference_invalid")
        if workspace_id != event["workspace_id"]:
            _fail("audit_reference_invalid")


def _verify_embeddings(connection: Connection, chunks: dict) -> tuple[int, int]:
    count = 0
    expected_buckets: dict[tuple[str, int], str] = {}
    rows = connection.execute(
        text(
            "SELECT id, chunk_id, source_id, source_version_id, dimensions, "
            "vector_json, content_hash "
            "FROM chunk_embeddings ORDER BY id"
        )
    ).mappings()
    for embedding in rows:
        count += 1
        chunk = chunks.get(embedding["chunk_id"])
        if (
            chunk is None
            or chunk["source_id"] != embedding["source_id"]
            or chunk["source_version_id"] != embedding["source_version_id"]
        ):
            _fail("embedding_ownership_invalid")
        if embedding["content_hash"] != _hash(chunk["content"]):
            _fail("embedding_content_hash_mismatch")
        try:
            vector = json.loads(embedding["vector_json"])
        except (TypeError, json.JSONDecodeError):
            _fail("embedding_vector_invalid")
        if (
            not isinstance(vector, list)
            or embedding["dimensions"] != len(vector)
            or not vector
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in vector
            )
        ):
            _fail("embedding_vector_invalid")
        bits = "".join("1" if float(value) >= 0 else "0" for value in vector[:64])
        for offset in range(0, len(bits), 16):
            expected_buckets[(embedding["id"], offset // 16)] = bits[offset : offset + 16]
    bucket_rows = list(
        connection.execute(
            text(
                "SELECT embedding_id, band_index, band_value FROM chunk_vector_buckets "
                "ORDER BY embedding_id, band_index"
            )
        ).mappings()
    )
    observed = {(row["embedding_id"], row["band_index"]): row["band_value"] for row in bucket_rows}
    if observed != expected_buckets or len(observed) != len(bucket_rows):
        _fail("vector_candidate_index_mismatch")
    return count, len(bucket_rows)


def _verify_fts(connection: Connection, chunks: dict) -> None:
    rows = list(
        connection.execute(
            text("SELECT chunk_id, source_id, content FROM chunk_search ORDER BY chunk_id")
        ).mappings()
    )
    if len(rows) != len(chunks) or len({row["chunk_id"] for row in rows}) != len(rows):
        _fail("fts_row_set_mismatch")
    for row in rows:
        chunk = chunks.get(row["chunk_id"])
        if chunk is None:
            _fail("fts_row_set_mismatch")
        if row["source_id"] != chunk["source_id"] or row["content"] != chunk["content"]:
            _fail("fts_content_mismatch")


def verify_live_database(engine: Engine) -> dict[str, int | bool]:
    """Verify SQLite structure and Proofline provenance without changing persistent state."""

    if engine.dialect.name != "sqlite":
        raise IntegrityVerificationError("sqlite_required")
    try:
        with engine.connect() as connection, connection.begin():
            _verify_sqlite_structure(connection)
            sources, versions = _verify_sources_and_versions(connection)
            chunks = _verify_chunks(connection, versions)
            memories, evidence_rows = _verify_memories_and_evidence(connection, sources, versions)
            decision_reviews = _verify_decision_reviews(
                connection, sources, versions, memories, evidence_rows
            )
            _verify_audit_references(connection, sources, memories, decision_reviews)
            embedding_count, vector_index_count = _verify_embeddings(connection, chunks)
            _verify_fts(connection, chunks)
            counts = {
                "sources": len(sources),
                "source_versions": len(versions),
                "chunks": len(chunks),
                "memories": connection.execute(text("SELECT count(*) FROM decisions")).scalar_one(),
                "evidence": connection.execute(text("SELECT count(*) FROM evidence")).scalar_one(),
                "decision_reviews": len(decision_reviews),
                "embeddings": embedding_count,
                "vector_index_rows": vector_index_count,
            }
    except IntegrityVerificationError:
        raise
    except Exception as exc:
        raise IntegrityVerificationError("database_validation_failed") from exc
    return {"valid": True, **counts}
