from __future__ import annotations

import hashlib
import time
import tracemalloc
from typing import Any

from .ingestion import chunk_markdown, line_number


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
