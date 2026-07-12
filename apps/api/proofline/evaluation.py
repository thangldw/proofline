from __future__ import annotations

import hashlib
import json
import math
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from .database import initialize_database, make_engine
from .grounding import GroundingValidationError, answer_question
from .ingestion import ingest_source
from .model_gateway import (
    GenerationRequest,
    GenerationResult,
    ProviderRequestError,
    StructuredOutputError,
)
from .models import Decision, ModelRun, SourceVersion
from .retrieval import lexical_search
from .schemas import MemoryKind, SourceCreate


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


class GroundedExpectedStatement(BaseModel):
    text: str = Field(min_length=1)
    kind: Literal["direct", "synthesis", "inference"]
    supporting_source_uris: list[str] = Field(min_length=1)


class GroundedEvaluationQuery(BaseModel):
    id: str
    question: str = Field(min_length=2)
    expected_status: Literal["grounded", "insufficient_evidence"]
    expected_statements: list[GroundedExpectedStatement] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_contract(self) -> GroundedEvaluationQuery:
        if self.expected_status == "grounded" and not self.expected_statements:
            raise ValueError("grounded queries require expected statements")
        if self.expected_status == "insufficient_evidence" and self.expected_statements:
            raise ValueError("insufficient-evidence queries cannot expect statements")
        return self


class GroundedEvaluationDataset(BaseModel):
    version: str
    provenance: str
    description: str
    sources: list[EvaluationSource] = Field(min_length=1)
    queries: list[GroundedEvaluationQuery] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_references(self) -> GroundedEvaluationDataset:
        uris = {source.uri for source in self.sources}
        titles = [source.title for source in self.sources]
        if len(uris) != len(self.sources) or len(set(titles)) != len(titles):
            raise ValueError("grounded evaluation source URIs and titles must be unique")
        query_ids = [query.id for query in self.queries]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("grounded evaluation query IDs must be unique")
        referenced = {
            uri
            for query in self.queries
            for statement in query.expected_statements
            for uri in statement.supporting_source_uris
        }
        if unknown := referenced - uris:
            raise ValueError(f"unknown supporting source URIs: {sorted(unknown)}")
        return self


class GroundedQueryResult(BaseModel):
    query_id: str
    expected_status: str
    actual_status: str
    expected_statement_kinds: list[str]
    actual_statement_kinds: list[str]
    statement_kinds_match: bool
    expected_supporting_source_uris: list[str]
    resolved_source_uris: list[str]
    emitted_citations: int
    resolved_citations: int
    relevant_citations: int
    model_run_count: int
    error_code: str | None = None


class GroundedEvaluationReport(BaseModel):
    dataset_version: str
    dataset_provenance: str
    dataset_description: str
    query_count: int
    expected_grounded_count: int
    emitted_citations: int
    resolved_citations: int
    relevant_citations: int
    citation_resolution: float
    citation_precision: float
    grounded_success: float
    expected_status_accuracy: float
    statement_kind_accuracy: float
    queries: list[GroundedQueryResult]


class ExtractionExpectedMemory(BaseModel):
    kind: MemoryKind
    statement: str = Field(min_length=1)
    status: str = Field(min_length=1, max_length=30)
    evidence_quote: str = Field(min_length=1)


class ExtractionEvaluationSource(EvaluationSource):
    expected_memories: list[ExtractionExpectedMemory] = Field(default_factory=list)


class ExtractionEvaluationDataset(BaseModel):
    version: str
    provenance: str
    description: str
    sources: list[ExtractionEvaluationSource] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_expectations(self) -> ExtractionEvaluationDataset:
        uris = [source.uri for source in self.sources]
        if len(set(uris)) != len(uris):
            raise ValueError("extraction evaluation source URIs must be unique")
        keys = [
            (source.uri, item.kind, item.statement, item.status)
            for source in self.sources
            for item in source.expected_memories
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("extraction evaluation expectations must be unique")
        return self


class ExtractionKindMetrics(BaseModel):
    kind: MemoryKind
    expected_count: int
    extracted_count: int
    matched_count: int
    precision: float
    recall: float
    f1: float


class ExtractionSourceResult(BaseModel):
    source_uri: str
    expected_count: int
    extracted_count: int
    matched_count: int
    false_positive_count: int
    false_negative_count: int
    evidence_valid_count: int


class ExtractionEvaluationReport(BaseModel):
    dataset_version: str
    dataset_provenance: str
    dataset_description: str
    source_count: int
    negative_source_count: int
    model_run_count: int
    expected_count: int
    extracted_count: int
    matched_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float
    recall: float
    f1: float
    evidence_resolution: float
    expected_evidence_accuracy: float
    negative_source_accuracy: float
    kinds: list[ExtractionKindMetrics]
    sources: list[ExtractionSourceResult]


class DatasetScriptedGenerationProvider:
    """Generate dataset expectations using only evidence IDs present in the real request."""

    id = "grounded_eval_scripted"
    model = "synthetic-expectation-v1"

    def __init__(
        self,
        query: GroundedEvaluationQuery,
        title_by_uri: dict[str, str],
    ) -> None:
        self.query = query
        self.title_by_uri = title_by_uri
        self.call_count = 0
        self.last_emitted_evidence_ids: list[str] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.call_count += 1
        user_message = next(
            message for message in reversed(request.messages) if message.role == "user"
        )
        payload = json.loads(user_message.content)
        evidence = payload["evidence"]
        evidence_id_by_title: dict[str, str] = {}
        for item in evidence:
            evidence_id_by_title.setdefault(item["source_title"], item["evidence_id"])

        statements: list[dict] = []
        if self.query.expected_status == "insufficient_evidence":
            # This is reached only when retrieval unexpectedly found evidence. Returning a valid,
            # visibly inferred statement makes the status mismatch observable without bypassing
            # answer validation.
            statements.append(
                {
                    "text": "The synthetic evaluator unexpectedly retrieved evidence.",
                    "kind": "inference",
                    "evidence_ids": [],
                }
            )
        else:
            for statement in self.query.expected_statements:
                evidence_ids = []
                for uri in statement.supporting_source_uris:
                    title = self.title_by_uri[uri]
                    evidence_ids.append(evidence_id_by_title.get(title, f"unresolved:{uri}"))
                statements.append(
                    {
                        "text": statement.text,
                        "kind": statement.kind,
                        "evidence_ids": list(dict.fromkeys(evidence_ids)),
                    }
                )
        self.last_emitted_evidence_ids = list(
            dict.fromkeys(
                evidence_id for statement in statements for evidence_id in statement["evidence_ids"]
            )
        )
        return GenerationResult(
            content=json.dumps({"statements": statements}, separators=(",", ":")),
            prompt_tokens=0,
            completion_tokens=0,
        )


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


def evaluate_grounded_dataset(
    dataset_path: Path,
    limit: int = 8,
) -> GroundedEvaluationReport:
    """Run a credential-free synthetic grounded-QA corpus through the production answer path."""
    if not 1 <= limit <= 12:
        raise ValueError("grounded evaluation limit must be between 1 and 12")
    dataset = GroundedEvaluationDataset.model_validate_json(
        dataset_path.read_text(encoding="utf-8")
    )
    title_by_uri = {source.uri: source.title for source in dataset.sources}
    with tempfile.TemporaryDirectory(prefix="proofline-grounded-eval-") as temporary_directory:
        engine = make_engine(f"sqlite:///{Path(temporary_directory) / 'evaluation.db'}")
        initialize_database(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with factory() as session:
                source_uri_by_id = _ingest_dataset(session, dataset)
                results = [
                    _evaluate_grounded_query(
                        session,
                        query,
                        title_by_uri,
                        source_uri_by_id,
                        limit,
                    )
                    for query in dataset.queries
                ]
        finally:
            engine.dispose()

    query_count = len(results)
    expected_grounded = sum(result.expected_status == "grounded" for result in results)
    emitted = sum(result.emitted_citations for result in results)
    resolved = sum(result.resolved_citations for result in results)
    relevant = sum(result.relevant_citations for result in results)
    citation_resolution = resolved / emitted if emitted else 1.0
    citation_precision = relevant / resolved if resolved else (1.0 if emitted == 0 else 0.0)
    grounded_successes = sum(
        result.expected_status == "grounded" and result.actual_status == "grounded"
        for result in results
    )
    return GroundedEvaluationReport(
        dataset_version=dataset.version,
        dataset_provenance=dataset.provenance,
        dataset_description=dataset.description,
        query_count=query_count,
        expected_grounded_count=expected_grounded,
        emitted_citations=emitted,
        resolved_citations=resolved,
        relevant_citations=relevant,
        citation_resolution=citation_resolution,
        citation_precision=citation_precision,
        grounded_success=grounded_successes / expected_grounded if expected_grounded else 1.0,
        expected_status_accuracy=(
            sum(result.expected_status == result.actual_status for result in results) / query_count
        ),
        statement_kind_accuracy=(
            sum(result.statement_kinds_match for result in results) / query_count
        ),
        queries=results,
    )


def grounded_report_meets_thresholds(
    report: GroundedEvaluationReport,
    *,
    min_citation_resolution: float = 0,
    min_citation_precision: float = 0,
    min_grounded_success: float = 0,
    min_status_accuracy: float = 0,
) -> bool:
    return (
        report.citation_resolution >= min_citation_resolution
        and report.citation_precision >= min_citation_precision
        and report.grounded_success >= min_grounded_success
        and report.expected_status_accuracy >= min_status_accuracy
    )


def _classification_metrics(
    expected: int, extracted: int, matched: int
) -> tuple[float, float, float]:
    precision = matched / extracted if extracted else (1.0 if expected == 0 else 0.0)
    recall = matched / expected if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _memory_key(source_uri: str, memory: Decision) -> tuple[str, str, str, str]:
    return source_uri, memory.kind, memory.statement, memory.status


def _expected_key(source_uri: str, expected: ExtractionExpectedMemory) -> tuple[str, str, str, str]:
    return source_uri, expected.kind, expected.statement, expected.status


def _memory_evidence_is_exact(session: Session, memory: Decision) -> bool:
    if len(memory.evidence) != 1:
        return False
    evidence = memory.evidence[0]
    version = session.get(SourceVersion, evidence.source_version_id)
    if (
        version is None
        or evidence.source_id != memory.source_id
        or evidence.source_version_id != memory.source_version_id
        or version.source_id != memory.source_id
        or evidence.end_offset <= evidence.start_offset
        or version.content[evidence.start_offset : evidence.end_offset] != evidence.quote
        or evidence.start_line != version.content.count("\n", 0, evidence.start_offset) + 1
        or evidence.end_line != version.content.count("\n", 0, evidence.end_offset - 1) + 1
    ):
        return False
    return hashlib.sha256(evidence.quote.encode("utf-8")).hexdigest() == evidence.quote_hash


def evaluate_extraction_dataset(dataset_path: Path) -> ExtractionEvaluationReport:
    """Evaluate deterministic marked-memory extraction through real ingestion and persistence."""
    dataset = ExtractionEvaluationDataset.model_validate_json(
        dataset_path.read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="proofline-extraction-eval-") as temporary_directory:
        engine = make_engine(f"sqlite:///{Path(temporary_directory) / 'evaluation.db'}")
        initialize_database(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with factory() as session:
                source_uri_by_id: dict[str, str] = {}
                expected_by_key: dict[tuple[str, str, str, str], ExtractionExpectedMemory] = {}
                for item in dataset.sources:
                    source, _created = ingest_source(
                        session,
                        SourceCreate(title=item.title, uri=item.uri, content=item.content),
                    )
                    source_uri_by_id[source.id] = item.uri
                    for expected in item.expected_memories:
                        expected_by_key[_expected_key(item.uri, expected)] = expected

                memories = list(session.scalars(select(Decision).order_by(Decision.id)).all())
                model_run_count = session.scalar(select(func.count()).select_from(ModelRun)) or 0
                actual_by_key: dict[tuple[str, str, str, str], list[Decision]] = defaultdict(list)
                evidence_valid_by_memory_id: dict[str, bool] = {}
                for memory in memories:
                    key = _memory_key(source_uri_by_id[memory.source_id], memory)
                    actual_by_key[key].append(memory)
                    evidence_valid_by_memory_id[memory.id] = _memory_evidence_is_exact(
                        session, memory
                    )

                expected_counter = Counter(expected_by_key.keys())
                actual_counter = Counter(
                    {key: len(values) for key, values in actual_by_key.items()}
                )
                matched_counter = expected_counter & actual_counter
                expected_count = sum(expected_counter.values())
                extracted_count = sum(actual_counter.values())
                matched_count = sum(matched_counter.values())
                precision, recall, f1 = _classification_metrics(
                    expected_count, extracted_count, matched_count
                )
                evidence_valid_count = sum(evidence_valid_by_memory_id.values())
                expected_evidence_matches = 0
                for key, matched in matched_counter.items():
                    expected = expected_by_key[key]
                    candidates = actual_by_key[key]
                    expected_evidence_matches += min(
                        matched,
                        sum(
                            evidence_valid_by_memory_id[memory.id]
                            and memory.evidence[0].quote == expected.evidence_quote
                            for memory in candidates
                        ),
                    )

                kinds: list[ExtractionKindMetrics] = []
                for kind in ("decision", "assumption", "constraint", "alternative"):
                    kind_expected = sum(
                        count for key, count in expected_counter.items() if key[1] == kind
                    )
                    kind_extracted = sum(
                        count for key, count in actual_counter.items() if key[1] == kind
                    )
                    kind_matched = sum(
                        count for key, count in matched_counter.items() if key[1] == kind
                    )
                    kind_precision, kind_recall, kind_f1 = _classification_metrics(
                        kind_expected, kind_extracted, kind_matched
                    )
                    kinds.append(
                        ExtractionKindMetrics(
                            kind=kind,
                            expected_count=kind_expected,
                            extracted_count=kind_extracted,
                            matched_count=kind_matched,
                            precision=kind_precision,
                            recall=kind_recall,
                            f1=kind_f1,
                        )
                    )

                sources: list[ExtractionSourceResult] = []
                negative_correct = 0
                negative_count = 0
                for item in dataset.sources:
                    expected_for_source = sum(
                        count for key, count in expected_counter.items() if key[0] == item.uri
                    )
                    extracted_for_source = sum(
                        count for key, count in actual_counter.items() if key[0] == item.uri
                    )
                    matched_for_source = sum(
                        count for key, count in matched_counter.items() if key[0] == item.uri
                    )
                    evidence_for_source = sum(
                        evidence_valid_by_memory_id[memory.id]
                        for key, source_memories in actual_by_key.items()
                        if key[0] == item.uri
                        for memory in source_memories
                    )
                    if expected_for_source == 0:
                        negative_count += 1
                        negative_correct += extracted_for_source == 0
                    sources.append(
                        ExtractionSourceResult(
                            source_uri=item.uri,
                            expected_count=expected_for_source,
                            extracted_count=extracted_for_source,
                            matched_count=matched_for_source,
                            false_positive_count=extracted_for_source - matched_for_source,
                            false_negative_count=expected_for_source - matched_for_source,
                            evidence_valid_count=evidence_for_source,
                        )
                    )
        finally:
            engine.dispose()

    return ExtractionEvaluationReport(
        dataset_version=dataset.version,
        dataset_provenance=dataset.provenance,
        dataset_description=dataset.description,
        source_count=len(dataset.sources),
        negative_source_count=negative_count,
        model_run_count=model_run_count,
        expected_count=expected_count,
        extracted_count=extracted_count,
        matched_count=matched_count,
        false_positive_count=extracted_count - matched_count,
        false_negative_count=expected_count - matched_count,
        precision=precision,
        recall=recall,
        f1=f1,
        evidence_resolution=evidence_valid_count / extracted_count if extracted_count else 1.0,
        expected_evidence_accuracy=(
            expected_evidence_matches / matched_count if matched_count else 1.0
        ),
        negative_source_accuracy=negative_correct / negative_count if negative_count else 1.0,
        kinds=kinds,
        sources=sources,
    )


def extraction_report_meets_thresholds(
    report: ExtractionEvaluationReport,
    *,
    min_precision: float = 0,
    min_recall: float = 0,
    min_f1: float = 0,
    min_evidence_resolution: float = 0,
    min_expected_evidence_accuracy: float = 0,
    min_negative_source_accuracy: float = 0,
) -> bool:
    return (
        report.model_run_count == 0
        and report.precision >= min_precision
        and report.recall >= min_recall
        and report.f1 >= min_f1
        and report.evidence_resolution >= min_evidence_resolution
        and report.expected_evidence_accuracy >= min_expected_evidence_accuracy
        and report.negative_source_accuracy >= min_negative_source_accuracy
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


def _ingest_dataset(
    session: Session, dataset: RetrievalDataset | GroundedEvaluationDataset
) -> dict[str, str]:
    source_uri_by_id: dict[str, str] = {}
    for item in dataset.sources:
        source, _created = ingest_source(
            session,
            SourceCreate(title=item.title, uri=item.uri, content=item.content),
        )
        source_uri_by_id[source.id] = item.uri
    return source_uri_by_id


def _evaluate_grounded_query(
    session: Session,
    query: GroundedEvaluationQuery,
    title_by_uri: dict[str, str],
    source_uri_by_id: dict[str, str],
    limit: int,
) -> GroundedQueryResult:
    provider = DatasetScriptedGenerationProvider(query, title_by_uri)
    before_runs = session.scalar(select(func.count()).select_from(ModelRun)) or 0
    answer = None
    error_code = None
    try:
        answer = answer_question(session, query.question, provider, limit=limit)
        actual_status = answer.status
    except (GroundingValidationError, StructuredOutputError) as exc:
        actual_status = "validation_failed"
        run = session.get(ModelRun, exc.run_id)
        error_code = run.error_code if run else "validation_failed"
    except ProviderRequestError as exc:
        actual_status = "provider_failed"
        run = session.get(ModelRun, exc.run_id) if exc.run_id else None
        error_code = run.error_code if run else "provider_failed"
    after_runs = session.scalar(select(func.count()).select_from(ModelRun)) or 0

    emitted_ids = provider.last_emitted_evidence_ids
    resolved_ids = [] if answer is None else [citation.evidence_id for citation in answer.citations]
    resolved_uris = sorted(
        {
            source_uri_by_id[citation.source_id]
            for citation in (answer.citations if answer else [])
            if citation.source_id in source_uri_by_id
        }
    )
    expected_uris = sorted(
        {uri for statement in query.expected_statements for uri in statement.supporting_source_uris}
    )
    relevant_ids = {
        citation.evidence_id
        for citation in (answer.citations if answer else [])
        if source_uri_by_id.get(citation.source_id) in expected_uris
    }
    actual_kinds = [] if answer is None else [statement.kind for statement in answer.statements]
    expected_kinds = [statement.kind for statement in query.expected_statements]
    return GroundedQueryResult(
        query_id=query.id,
        expected_status=query.expected_status,
        actual_status=actual_status,
        expected_statement_kinds=expected_kinds,
        actual_statement_kinds=actual_kinds,
        statement_kinds_match=actual_kinds == expected_kinds,
        expected_supporting_source_uris=expected_uris,
        resolved_source_uris=resolved_uris,
        emitted_citations=len(set(emitted_ids)),
        resolved_citations=len(set(resolved_ids)),
        relevant_citations=len(relevant_ids),
        model_run_count=after_runs - before_runs,
        error_code=error_code,
    )


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
