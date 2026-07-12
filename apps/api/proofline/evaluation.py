from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field
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


def discounted_cumulative_gain(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))


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
