from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .database import initialize_database, make_engine
from .evaluation import (
    DatasetScriptedGenerationProvider,
    EvaluationSource,
    GroundedEvaluationQuery,
    GroundedExpectedStatement,
    percentile,
)
from .grounding import answer_question
from .ingestion import ingest_source
from .models import ModelRun, SourceVersion
from .schemas import SourceCreate


class SyntheticPilotTask(BaseModel):
    id: str = Field(min_length=1)
    persona: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    temporal: bool = False
    question: str = Field(min_length=2)
    expected_status: str
    expected_statements: list[GroundedExpectedStatement] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_expected_answer(self) -> SyntheticPilotTask:
        GroundedEvaluationQuery(
            id=self.id,
            question=self.question,
            expected_status=self.expected_status,
            expected_statements=self.expected_statements,
        )
        return self

    def as_grounded_query(self) -> GroundedEvaluationQuery:
        return GroundedEvaluationQuery(
            id=self.id,
            question=self.question,
            expected_status=self.expected_status,
            expected_statements=self.expected_statements,
        )


class SyntheticPilotDataset(BaseModel):
    version: str = Field(min_length=1)
    provenance: str
    description: str
    sources: list[EvaluationSource] = Field(min_length=1)
    tasks: list[SyntheticPilotTask] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> SyntheticPilotDataset:
        uris = [source.uri for source in self.sources]
        if len(set(uris)) != len(uris):
            raise ValueError("synthetic pilot source URIs must be unique")
        task_ids = [task.id for task in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("synthetic pilot task IDs must be unique")
        known = set(uris)
        referenced = {
            uri
            for task in self.tasks
            for statement in task.expected_statements
            for uri in statement.supporting_source_uris
        }
        if unknown := referenced - known:
            raise ValueError(f"synthetic pilot tasks reference unknown sources: {sorted(unknown)}")
        if self.provenance != "synthetic-simulation":
            raise ValueError("pilot simulation datasets must declare synthetic-simulation")
        return self


class SyntheticTaskResult(BaseModel):
    task_id: str
    persona: str
    intent: str
    temporal: bool
    expected_status: str
    actual_status: str
    completed: bool
    expected_source_uris: list[str]
    resolved_source_uris: list[str]
    emitted_citations: int
    resolved_citations: int
    relevant_citations: int
    proofline_sources_inspected: int
    naive_sources_inspected: int
    local_latency_ms: float
    model_run_count: int


class SyntheticPilotReport(BaseModel):
    artifact_type: str = "synthetic_pilot_simulation"
    qualification: str
    dataset_version: str
    dataset_sha256: str
    proofline_revision: str
    observed_at_utc: str
    environment: dict[str, str]
    task_count: int
    persona_count: int
    temporal_task_count: int
    completed_tasks: int
    task_completion_rate: float
    emitted_citations: int
    resolved_citations: int
    relevant_citations: int
    citation_resolution: float
    citation_precision: float
    proofline_sources_inspected: int
    naive_sources_inspected: int
    source_inspection_reduction: float
    latency_unit: str
    latency: dict[str, float]
    tasks: list[SyntheticTaskResult]


def _expected_uris(task: SyntheticPilotTask) -> list[str]:
    return sorted(
        {uri for statement in task.expected_statements for uri in statement.supporting_source_uris}
    )


def _naive_inspection_count(ordered_uris: list[str], expected: list[str]) -> int:
    """Count a fixed URI-order scan until all expected sources are encountered."""
    if not expected:
        return len(ordered_uris)
    expected_set = set(expected)
    seen: set[str] = set()
    for index, uri in enumerate(ordered_uris, start=1):
        if uri in expected_set:
            seen.add(uri)
        if seen == expected_set:
            return index
    return len(ordered_uris)


def run_synthetic_pilot_simulation(
    dataset_path: Path,
    *,
    proofline_revision: str = "working-tree",
    limit: int = 8,
) -> SyntheticPilotReport:
    """Exercise the production local path; never interpret the result as real pilot evidence."""
    if not 1 <= limit <= 12:
        raise ValueError("simulation retrieval limit must be between 1 and 12")
    raw_dataset = dataset_path.read_bytes()
    dataset = SyntheticPilotDataset.model_validate_json(raw_dataset)
    dataset_hash = hashlib.sha256(raw_dataset).hexdigest()
    title_by_uri = {source.uri: source.title for source in dataset.sources}
    ordered_uris = sorted(title_by_uri)
    results: list[SyntheticTaskResult] = []

    with tempfile.TemporaryDirectory(prefix="proofline-pilot-simulation-") as temporary_directory:
        engine = make_engine(f"sqlite:///{Path(temporary_directory) / 'simulation.db'}")
        initialize_database(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with factory() as session:
                source_uri_by_id: dict[str, str] = {}
                for fixture in dataset.sources:
                    source, _created = ingest_source(
                        session,
                        SourceCreate(
                            title=fixture.title,
                            uri=fixture.uri,
                            content=fixture.content,
                        ),
                    )
                    for revision in fixture.revisions:
                        source, _created = ingest_source(
                            session,
                            SourceCreate(
                                title=fixture.title,
                                uri=fixture.uri,
                                content=revision,
                            ),
                        )
                    source_uri_by_id[source.id] = fixture.uri

                for task in dataset.tasks:
                    query = task.as_grounded_query()
                    provider = DatasetScriptedGenerationProvider(query, title_by_uri)
                    before_runs = session.scalar(select(func.count()).select_from(ModelRun)) or 0
                    started = time.perf_counter()
                    answer = answer_question(session, task.question, provider, limit=limit)
                    latency_ms = (time.perf_counter() - started) * 1000
                    after_runs = session.scalar(select(func.count()).select_from(ModelRun)) or 0

                    resolved = 0
                    relevant = 0
                    resolved_uris: set[str] = set()
                    expected = _expected_uris(task)
                    for citation in answer.citations:
                        version = session.get(SourceVersion, citation.source_version_id)
                        exact = (
                            version is not None
                            and version.source_id == citation.source_id
                            and version.content[citation.start_offset : citation.end_offset]
                            == citation.content
                        )
                        if not exact:
                            continue
                        resolved += 1
                        uri = source_uri_by_id.get(citation.source_id)
                        if uri is not None:
                            resolved_uris.add(uri)
                        if uri in expected:
                            relevant += 1

                    emitted = len(set(provider.last_emitted_evidence_ids))
                    actual_kinds = [statement.kind for statement in answer.statements]
                    expected_kinds = [statement.kind for statement in task.expected_statements]
                    completed = (
                        answer.status == task.expected_status
                        and actual_kinds == expected_kinds
                        and resolved == emitted
                        and relevant == resolved
                        and sorted(resolved_uris) == expected
                    )
                    results.append(
                        SyntheticTaskResult(
                            task_id=task.id,
                            persona=task.persona,
                            intent=task.intent,
                            temporal=task.temporal,
                            expected_status=task.expected_status,
                            actual_status=answer.status,
                            completed=completed,
                            expected_source_uris=expected,
                            resolved_source_uris=sorted(resolved_uris),
                            emitted_citations=emitted,
                            resolved_citations=resolved,
                            relevant_citations=relevant,
                            proofline_sources_inspected=len(resolved_uris),
                            naive_sources_inspected=_naive_inspection_count(ordered_uris, expected),
                            local_latency_ms=round(latency_ms, 3),
                            model_run_count=after_runs - before_runs,
                        )
                    )
        finally:
            engine.dispose()

    emitted = sum(result.emitted_citations for result in results)
    resolved = sum(result.resolved_citations for result in results)
    relevant = sum(result.relevant_citations for result in results)
    proofline_inspections = sum(result.proofline_sources_inspected for result in results)
    naive_inspections = sum(result.naive_sources_inspected for result in results)
    latencies = [result.local_latency_ms for result in results]
    completed = sum(result.completed for result in results)
    return SyntheticPilotReport(
        qualification=(
            "Credential-free deterministic simulation only. This is not external pilot, "
            "human-usefulness, adoption, willingness-to-pay, or production-latency evidence."
        ),
        dataset_version=dataset.version,
        dataset_sha256=dataset_hash,
        proofline_revision=proofline_revision,
        observed_at_utc=datetime.now(UTC).isoformat(),
        environment={
            "python": platform.python_version(),
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
        },
        task_count=len(results),
        persona_count=len({result.persona for result in results}),
        temporal_task_count=sum(result.temporal for result in results),
        completed_tasks=completed,
        task_completion_rate=completed / len(results),
        emitted_citations=emitted,
        resolved_citations=resolved,
        relevant_citations=relevant,
        citation_resolution=resolved / emitted if emitted else 1.0,
        citation_precision=relevant / resolved if resolved else 1.0,
        proofline_sources_inspected=proofline_inspections,
        naive_sources_inspected=naive_inspections,
        source_inspection_reduction=(
            1 - proofline_inspections / naive_inspections if naive_inspections else 0.0
        ),
        latency_unit="milliseconds (local observation only)",
        latency={
            "p50": round(median(latencies), 3),
            "p95": round(percentile(latencies, 95), 3),
            "max": round(max(latencies), 3),
        },
        tasks=results,
    )


def write_simulation_report(path: Path, report: SyntheticPilotReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
