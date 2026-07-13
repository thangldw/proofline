#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from proofline.reranking import DeterministicTokenReranker
from proofline.schemas import SearchHit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    reranker = DeterministicTokenReranker()
    reciprocal_ranks = []
    latencies = []
    for query in dataset["queries"]:
        hits = [
            SearchHit(
                chunk_id=item["id"],
                source_id=item["id"],
                source_version_id=f"v-{item['id']}",
                source_title=item["id"],
                content=item["content"],
                start_offset=0,
                end_offset=len(item["content"]),
                start_line=1,
                end_line=1,
                rank=index,
            )
            for index, item in enumerate(query["candidates"], start=1)
        ]
        started = time.perf_counter()
        scores = {item.chunk_id: item.score for item in reranker.rerank(query["query"], hits)}
        latencies.append((time.perf_counter() - started) * 1000)
        ordered = sorted(hits, key=lambda hit: (-scores[hit.chunk_id], hit.chunk_id))
        rank = next(
            index
            for index, hit in enumerate(ordered, start=1)
            if hit.chunk_id == query["relevant_id"]
        )
        reciprocal_ranks.append(1 / rank)
    receipt = {
        "schema": "proofline-reranking-benchmark-v1",
        "dataset": str(args.dataset),
        "dataset_sha256": __import__("hashlib").sha256(args.dataset.read_bytes()).hexdigest(),
        "reranker_id": reranker.id,
        "model": reranker.model,
        "query_count": len(reciprocal_ranks),
        "mrr": statistics.fmean(reciprocal_ranks),
        "median_latency_ms": statistics.median(latencies),
        "qualification": "synthetic regression only; not real-model or pilot evidence",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
