#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from proofline.database import initialize_database, make_engine
from proofline.embeddings import index_current_embeddings, semantic_search
from proofline.ingestion import ingest_source
from proofline.model_gateway import FakeEmbeddingProvider
from proofline.schemas import SourceCreate
from sqlalchemy.orm import Session


def vector(value: str, dimensions: int = 32) -> list[float]:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return [1.0 if digest[index] & 1 else -1.0 for index in range(dimensions)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="proofline-vector-benchmark-") as temporary:
        database = Path(temporary) / "benchmark.db"
        engine = make_engine(f"sqlite:///{database}")
        initialize_database(engine)
        texts = [
            f"Decision: benchmark vector source {index} token-{index % 97}"
            for index in range(args.sources)
        ]
        vectors = {text: vector(text) for text in texts}
        vectors["benchmark query"] = vectors[texts[0]]
        provider = FakeEmbeddingProvider(vectors, model="synthetic-sign-vector-v1")
        tracemalloc.start()
        with Session(engine) as session:
            for index, text in enumerate(texts):
                ingest_source(
                    session,
                    SourceCreate(title=f"Source {index}", content=text, uri=f"benchmark://{index}"),
                )
            index_started = time.perf_counter()
            indexed = index_current_embeddings(session, provider)
            index_ms = (time.perf_counter() - index_started) * 1000
            update_started = time.perf_counter()
            repeated = index_current_embeddings(session, provider)
            no_op_update_ms = (time.perf_counter() - update_started) * 1000
            search_started = time.perf_counter()
            hits = semantic_search(session, "benchmark query", provider, limit=10)
            search_ms = (time.perf_counter() - search_started) * 1000
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        receipt = {
            "schema": "proofline-vector-index-benchmark-v1",
            "dataset": "synthetic-generated-no-source-content",
            "source_count": args.sources,
            "dimensions": 32,
            "provider": provider.id,
            "model": provider.model,
            "indexed": indexed.indexed,
            "repeat_skipped": repeated.skipped,
            "candidate_result_count": len(hits),
            "index_latency_ms": index_ms,
            "no_op_update_latency_ms": no_op_update_ms,
            "search_latency_ms": search_ms,
            "peak_python_memory_bytes": peak,
            "database_bytes": database.stat().st_size,
            "qualification": "synthetic local benchmark; not a 10,000-file or 1-GB scale claim",
        }
        engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
