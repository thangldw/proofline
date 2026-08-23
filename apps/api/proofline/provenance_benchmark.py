from __future__ import annotations

import hashlib
import os
import statistics
import tempfile
import time
import tracemalloc
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from .anchors import build_evidence_anchor
from .database import initialize_database, make_engine
from .decision_reviews import refresh_decision_reviews
from .evidence_packages import (
    atomic_write_package,
    build_decision_package,
    verify_decision_package,
)
from .ingestion import chunk_markdown, ingest_source, line_number
from .integrity import verify_live_database
from .models import DEFAULT_WORKSPACE_ID, Chunk, Decision, Evidence, Source, SourceVersion
from .portability import canonical_json_bytes
from .schemas import SourceCreate


def benchmark_provenance_scale(counts: list[int]) -> dict[str, Any]:
    if not counts or any(isinstance(count, bool) or count < 1 for count in counts):
        raise ValueError("counts must contain positive integers")
    profiles: list[dict[str, int | float]] = []
    for count in counts:
        tracemalloc.start()
        build_started = time.perf_counter()
        records: list[tuple[str, str, int, int, int, int]] = []
        for index in range(count):
            content = (
                f"Decision: retain provenance record {index:06d}.\n"
                f"Reason: synthetic scale bucket {index % 997:03d}."
            )
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            spans = chunk_markdown(content)
            if len(spans) != 1:
                raise RuntimeError("synthetic_fixture_chunk_count_invalid")
            span = spans[0]
            records.append(
                (
                    content,
                    content_hash,
                    span.start_offset,
                    span.end_offset,
                    span.start_line,
                    span.end_line,
                )
            )
        build_ms = (time.perf_counter() - build_started) * 1000

        verify_started = time.perf_counter()
        for content, expected_hash, start, end, start_line, end_line in records:
            if hashlib.sha256(content.encode()).hexdigest() != expected_hash:
                raise RuntimeError("synthetic_content_hash_mismatch")
            exact = content[start:end]
            if (
                exact != content
                or start_line != line_number(content, start)
                or end_line != line_number(content, end - 1)
            ):
                raise RuntimeError("synthetic_span_verification_failed")
        verify_ms = (time.perf_counter() - verify_started) * 1000
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        profiles.append(
            {
                "document_count": count,
                "chunk_count": len(records),
                "build_latency_ms": build_ms,
                "verify_latency_ms": verify_ms,
                "peak_python_memory_bytes": peak,
            }
        )
    return {
        "schema": "proofline-provenance-scale-benchmark-v1",
        "fixture": "synthetic-generated-no-source-content",
        "profiles": profiles,
        "qualification": (
            "deterministic parser, SHA-256, and exact-span benchmark only; does not establish "
            "database, retrieval, model, connector, or production scale"
        ),
    }


def benchmark_decision_evidence_package(iterations: int = 100) -> dict[str, Any]:
    """Measure the credential-free Decision Evidence Package vertical slice."""

    if isinstance(iterations, bool) or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    engine = make_engine("sqlite:///:memory:")
    initialize_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    content = (
        "# Queue requirement\n\n"
        "The desktop app must run without a network service.\n\n"
        "Decision: Use SQLite for the durable local queue.\n"
        "Reason: acknowledged writes must survive restart and process failure."
    )
    tracemalloc.start()
    try:
        with factory() as session:
            started = time.perf_counter()
            source, _created = ingest_source(
                session,
                SourceCreate(
                    title="benchmark-requirement.md",
                    uri="file:///benchmark/requirement.md",
                    content=content,
                ),
            )
            ingest_latency_ms = (time.perf_counter() - started) * 1000
            decision = session.scalar(
                select(Decision).where(Decision.source_version_id == source.current_version_id)
            )
            if decision is None:
                raise RuntimeError("benchmark_decision_missing")

            started = time.perf_counter()
            package = build_decision_package(session, decision.id)
            package_build_latency_ms = (time.perf_counter() - started) * 1000
            json_bytes = len(canonical_json_bytes(package)) + 1
            with tempfile.TemporaryDirectory(prefix="proofline-benchmark-") as directory:
                zip_path = Path(directory) / "evidence.zip"
                atomic_write_package(zip_path, package)
                zip_bytes = zip_path.stat().st_size

            verify_samples: list[float] = []
            for _index in range(iterations):
                started = time.perf_counter()
                verify_decision_package(package)
                verify_samples.append((time.perf_counter() - started) * 1000)
            _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        engine.dispose()
    return {
        "schema": "proofline-decision-evidence-package-benchmark-v1",
        "fixture": "synthetic-local-adr-with-exact-citation",
        "iterations": iterations,
        "ingest_latency_ms": ingest_latency_ms,
        "package_build_latency_ms": package_build_latency_ms,
        "verify_latency_ms_median": statistics.median(verify_samples),
        "package_json_bytes": json_bytes,
        "package_zip_bytes": zip_bytes,
        "peak_python_memory_bytes": peak,
        "qualification": (
            "synthetic credential-free local benchmark; excludes migration time and does not "
            "establish production capacity"
        ),
    }


def _benchmark_id(kind: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"proofline:review-benchmark:{kind}:{index}"))


def _insert_batches(session, model, rows: list[dict[str, Any]], batch_size: int = 500) -> None:
    for offset in range(0, len(rows), batch_size):
        session.execute(model.__table__.insert(), rows[offset : offset + batch_size])


def _seed_decision_review_benchmark(session, decision_count: int) -> None:
    created_at = datetime(2026, 8, 23, tzinfo=UTC)
    sources: list[dict[str, Any]] = []
    versions: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    search_rows: list[dict[str, str]] = []

    for index in range(decision_count):
        source_id = _benchmark_id("source", index)
        cited_version_id = _benchmark_id("cited-version", index)
        current_version_id = _benchmark_id("current-version", index)
        decision_id = _benchmark_id("decision", index)
        evidence_id = _benchmark_id("evidence", index)
        cited = f"Decision: retain SQLite for local queue {index:05d}."
        current = f"Decision: require PostgreSQL for shared queue {index:05d}."
        cited_hash = hashlib.sha256(cited.encode()).hexdigest()
        current_hash = hashlib.sha256(current.encode()).hexdigest()
        sources.append(
            {
                "id": source_id,
                "workspace_id": DEFAULT_WORKSPACE_ID,
                "title": f"synthetic-requirement-{index:05d}.md",
                "kind": "markdown",
                "uri": f"file:///synthetic/requirement-{index:05d}.md",
                "content": current,
                "content_hash": hashlib.sha256(f"source:{source_id}".encode()).hexdigest(),
                "status": "indexed",
                "created_at": created_at,
                "indexed_at": created_at,
                "current_version_id": current_version_id,
                "git_repository_id": None,
                "git_commit_sha": None,
                "git_path": None,
            }
        )
        for version_id, version_number, content, content_hash in (
            (cited_version_id, 1, cited, cited_hash),
            (current_version_id, 2, current, current_hash),
        ):
            versions.append(
                {
                    "id": version_id,
                    "source_id": source_id,
                    "content_hash": content_hash,
                    "content": content,
                    "version_number": version_number,
                    "content_length": len(content),
                    "status": "indexed",
                    "parser_version": "deterministic-v2",
                    "created_at": created_at,
                }
            )
            chunk_id = _benchmark_id(f"chunk-{version_number}", index)
            chunks.append(
                {
                    "id": chunk_id,
                    "source_id": source_id,
                    "source_version_id": version_id,
                    "ordinal": 0,
                    "content": content,
                    "start_offset": 0,
                    "end_offset": len(content),
                    "start_line": 1,
                    "end_line": 1,
                }
            )
            search_rows.append({"chunk_id": chunk_id, "source_id": source_id, "content": content})
        decisions.append(
            {
                "id": decision_id,
                "source_id": source_id,
                "source_version_id": cited_version_id,
                "kind": "decision",
                "title": f"Synthetic decision {index:05d}",
                "statement": cited.removeprefix("Decision: "),
                "rationale": "Synthetic review-refresh fixture.",
                "status": "accepted",
                "confidence": 1.0,
                "extraction_method": "deterministic",
                "model_run_id": None,
                "valid_from": None,
                "valid_to": None,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        anchor = build_evidence_anchor(cited, 0, len(cited))
        evidence_rows.append(
            {
                "id": evidence_id,
                "decision_id": decision_id,
                "source_id": source_id,
                "source_version_id": cited_version_id,
                "quote": cited,
                "quote_hash": cited_hash,
                "start_offset": 0,
                "end_offset": len(cited),
                "start_line": 1,
                "end_line": 1,
                "anchor_version": anchor.version,
                "section_path": list(anchor.section_path),
                "prefix_sha256": anchor.prefix_sha256,
                "suffix_sha256": anchor.suffix_sha256,
                "binding_root_id": evidence_id,
                "binding_state": "active",
                "superseded_at": None,
                "superseded_by_id": None,
            }
        )

    _insert_batches(session, Source, sources)
    _insert_batches(session, SourceVersion, versions)
    _insert_batches(session, Chunk, chunks)
    _insert_batches(session, Decision, decisions)
    _insert_batches(session, Evidence, evidence_rows)
    for offset in range(0, len(search_rows), 500):
        session.execute(
            text(
                "INSERT INTO chunk_search(chunk_id, source_id, content) "
                "VALUES (:chunk_id, :source_id, :content)"
            ),
            search_rows[offset : offset + 500],
        )
    session.commit()


def benchmark_decision_review_refresh(decision_count: int = 10_000) -> dict[str, Any]:
    """Measure deterministic review refresh and full live-integrity verification."""

    if isinstance(decision_count, bool) or decision_count < 1:
        raise ValueError("decision_count must be a positive integer")
    with tempfile.TemporaryDirectory(prefix="proofline-review-benchmark-") as directory:
        database = Path(directory) / "proofline.db"
        engine = make_engine(f"sqlite:///{database}")
        initialize_database(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with factory() as session:
                _seed_decision_review_benchmark(session, decision_count)
                tracemalloc.start()
                started = time.perf_counter()
                summary = refresh_decision_reviews(
                    session,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                )
                session.commit()
                refresh_latency_ms = (time.perf_counter() - started) * 1000
                started = time.perf_counter()
                integrity = verify_live_database(engine)
                verify_latency_ms = (time.perf_counter() - started) * 1000
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            database_bytes = os.path.getsize(database)
        finally:
            if tracemalloc.is_tracing():
                tracemalloc.stop()
            engine.dispose()
    if summary.opened != decision_count or integrity["decision_reviews"] != decision_count:
        raise RuntimeError("synthetic_review_count_mismatch")
    return {
        "schema": "proofline-decision-review-refresh-benchmark-v1",
        "fixture": "synthetic-generated-local-sqlite",
        "decision_count": decision_count,
        "review_count": summary.opened,
        "database_bytes": database_bytes,
        "refresh_latency_ms": refresh_latency_ms,
        "verify_latency_ms": verify_latency_ms,
        "peak_python_memory_bytes": peak,
        "qualification": (
            "synthetic local SQLite benchmark; excludes connectors, auth, hosted sync, network, "
            "and team production capacity"
        ),
    }
