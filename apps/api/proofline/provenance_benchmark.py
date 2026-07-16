from __future__ import annotations

import hashlib
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .database import initialize_database, make_engine
from .evidence_packages import (
    atomic_write_package,
    build_decision_package,
    verify_decision_package,
)
from .ingestion import chunk_markdown, ingest_source, line_number
from .models import Decision
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
