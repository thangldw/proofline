from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from .database import initialize_database, make_engine
from .ingestion import ingest_source
from .retrieval import lexical_search
from .schemas import SourceCreate


class EvaluationSource(BaseModel):
    title: str
    uri: str
    content: str


class EvaluationQuery(BaseModel):
    id: str
    question: str
    relevance: dict[str, int]


class RetrievalDataset(BaseModel):
    version: str
    provenance: str
    description: str
    sources: list[EvaluationSource] = Field(min_length=1)
    queries: list[EvaluationQuery] = Field(min_length=1)


class QueryMetrics(BaseModel):
    query_id: str
    recall_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    retrieved_source_uris: list[str]


class EvaluationReport(BaseModel):
    dataset_version: str
    dataset_provenance: str
    query_count: int
    k: int
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg_at_k: float
    queries: list[QueryMetrics]


class LatencySummary(BaseModel):
    p50: float
    p95: float
    max: float


class LexicalBenchmarkReport(BaseModel):
    fixture_version: str
    fixture_provenance: str
    source_count: int
    chunk_count: int
    query_count: int
    matched_query_count: int
    result_limit: int
    latency_unit: str
    latency: LatencySummary


def discounted_cumulative_gain(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))


def percentile(values: list[float], percent: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sample."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def query_metrics(
    query_id: str,
    retrieved_uris: list[str],
    relevance: dict[str, int],
    k: int,
) -> QueryMetrics:
    ranked = retrieved_uris[:k]
    relevant = {uri for uri, grade in relevance.items() if grade > 0}
    retrieved_relevant = [uri for uri in ranked if uri in relevant]
    recall = len(set(retrieved_relevant)) / len(relevant) if relevant else 1.0
    precision = len(retrieved_relevant) / k if k else 0.0
    first_rank = next((index + 1 for index, uri in enumerate(ranked) if uri in relevant), None)
    reciprocal_rank = 1 / first_rank if first_rank else 0.0
    grades = [relevance.get(uri, 0) for uri in ranked]
    ideal = sorted(relevance.values(), reverse=True)[:k]
    ideal_dcg = discounted_cumulative_gain(ideal)
    ndcg = discounted_cumulative_gain(grades) / ideal_dcg if ideal_dcg else 1.0
    return QueryMetrics(
        query_id=query_id,
        recall_at_k=recall,
        precision_at_k=precision,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=ndcg,
        retrieved_source_uris=ranked,
    )


def evaluate_dataset(dataset_path: Path, k: int = 10) -> EvaluationReport:
    dataset = RetrievalDataset.model_validate_json(dataset_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="proofline-eval-") as temporary_directory:
        engine = make_engine(f"sqlite:///{Path(temporary_directory) / 'evaluation.db'}")
        initialize_database(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            source_uri_by_id = _ingest_dataset(session, dataset)
            results = [
                _evaluate_query(session, query, source_uri_by_id, k) for query in dataset.queries
            ]
        engine.dispose()
    count = len(results)
    return EvaluationReport(
        dataset_version=dataset.version,
        dataset_provenance=dataset.provenance,
        query_count=count,
        k=k,
        recall_at_k=sum(result.recall_at_k for result in results) / count,
        precision_at_k=sum(result.precision_at_k for result in results) / count,
        mrr=sum(result.reciprocal_rank for result in results) / count,
        ndcg_at_k=sum(result.ndcg_at_k for result in results) / count,
        queries=results,
    )


def benchmark_lexical_search(
    source_count: int = 1_000,
    query_count: int = 100,
    result_limit: int = 10,
) -> LexicalBenchmarkReport:
    """Measure lexical query latency against a deterministic temporary SQLite fixture.

    This is a local measurement utility, not a performance assertion. Its generated data is
    synthetic and intentionally simple so reports can be compared with their fixture metadata.
    """
    if source_count < 1:
        raise ValueError("source_count must be positive")
    if query_count < 1:
        raise ValueError("query_count must be positive")
    if result_limit < 1:
        raise ValueError("result_limit must be positive")

    with tempfile.TemporaryDirectory(prefix="proofline-benchmark-") as temporary_directory:
        engine = make_engine(f"sqlite:///{Path(temporary_directory) / 'benchmark.db'}")
        initialize_database(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with factory() as session:
                for index in range(source_count):
                    ingest_source(
                        session,
                        SourceCreate(
                            title=f"Benchmark ADR {index:06d}",
                            uri=f"benchmark://lexical/{index:06d}",
                            content=(
                                f"# Benchmark ADR {index:06d}\n\n"
                                f"Decision: Adopt benchmarktoken{index:06d} for local subsystem "
                                f"{index % 97:02d}.\n"
                                "Reason: This generated source supports deterministic local "
                                "lexical measurement."
                            ),
                        ),
                    )

                # Warm SQLite's page cache without including the warm-up in reported samples.
                lexical_search(session, "benchmarktoken000000", result_limit)
                latencies: list[float] = []
                matched_queries = 0
                for query_index in range(query_count):
                    source_index = (query_index * 7_919) % source_count
                    started = time.perf_counter_ns()
                    hits = lexical_search(
                        session,
                        f"benchmarktoken{source_index:06d}",
                        result_limit,
                    )
                    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
                    latencies.append(elapsed_ms)
                    if hits:
                        matched_queries += 1

                chunk_count = session.execute(text("SELECT COUNT(*) FROM chunks")).scalar_one()
        finally:
            engine.dispose()

    return LexicalBenchmarkReport(
        fixture_version="lexical-generated-v1",
        fixture_provenance="synthetic-generated",
        source_count=source_count,
        chunk_count=chunk_count,
        query_count=query_count,
        matched_query_count=matched_queries,
        result_limit=result_limit,
        latency_unit="milliseconds",
        latency=LatencySummary(
            p50=percentile(latencies, 50),
            p95=percentile(latencies, 95),
            max=max(latencies),
        ),
    )


def _ingest_dataset(session: Session, dataset: RetrievalDataset) -> dict[str, str]:
    source_uri_by_id: dict[str, str] = {}
    for item in dataset.sources:
        source, _created = ingest_source(
            session,
            SourceCreate(title=item.title, uri=item.uri, content=item.content),
        )
        source_uri_by_id[source.id] = item.uri
    return source_uri_by_id


def _evaluate_query(
    session: Session,
    query: EvaluationQuery,
    source_uri_by_id: dict[str, str],
    k: int,
) -> QueryMetrics:
    # Retrieve extra chunks before source-level deduplication so one verbose source cannot
    # consume the entire source-level evaluation window.
    hits = lexical_search(session, query.question, max(k * 5, k))
    ranked_uris = list(
        dict.fromkeys(
            source_uri_by_id[hit.source_id] for hit in hits if hit.source_id in source_uri_by_id
        )
    )
    return query_metrics(query.id, ranked_uris, query.relevance, k)


def report_json(report: EvaluationReport) -> str:
    return json.dumps(report.model_dump(), ensure_ascii=False, indent=2)
