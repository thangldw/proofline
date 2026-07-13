from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict

from sqlalchemy import Connection, Engine, text

from .backup import REQUIRED_CORE_TABLES
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
            text("SELECT id, content, content_hash, current_version_id FROM sources ORDER BY id")
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


def _verify_memories_and_evidence(connection: Connection, sources: dict, versions: dict) -> None:
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
    evidence_rows = connection.execute(
        text(
            "SELECT id, decision_id, source_id, source_version_id, quote, quote_hash, "
            "start_offset, end_offset, start_line, end_line FROM evidence ORDER BY id"
        )
    ).mappings()
    for evidence in evidence_rows:
        version = versions.get(evidence["source_version_id"])
        if evidence["decision_id"] not in memories:
            _fail("evidence_memory_missing")
        memory = memories[evidence["decision_id"]]
        if (
            evidence["source_id"] != memory["source_id"]
            or evidence["source_version_id"] != memory["source_version_id"]
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
        evidence_counts[evidence["decision_id"]] += 1
    if any(evidence_counts[memory_id] == 0 for memory_id in memories):
        _fail("memory_evidence_missing")


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
            _verify_memories_and_evidence(connection, sources, versions)
            embedding_count, vector_index_count = _verify_embeddings(connection, chunks)
            _verify_fts(connection, chunks)
            counts = {
                "sources": len(sources),
                "source_versions": len(versions),
                "chunks": len(chunks),
                "memories": connection.execute(text("SELECT count(*) FROM decisions")).scalar_one(),
                "evidence": connection.execute(text("SELECT count(*) FROM evidence")).scalar_one(),
                "embeddings": embedding_count,
                "vector_index_rows": vector_index_count,
            }
    except IntegrityVerificationError:
        raise
    except Exception as exc:
        raise IntegrityVerificationError("database_validation_failed") from exc
    return {"valid": True, **counts}
