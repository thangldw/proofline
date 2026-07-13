from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from . import __version__
from .config import Settings
from .database import initialize_database, make_engine
from .evaluation import (
    ExtractionEvaluationDataset,
    ExtractionEvaluationReport,
    ExtractionKindMetrics,
    ExtractionSourceResult,
    GroundedEvaluationReport,
    _classification_metrics,
    _memory_evidence_is_exact,
    evaluate_grounded_dataset,
)
from .extraction import extract_memory_candidates
from .ingestion import ingest_source
from .model_gateway import (
    GenerationProvider,
    GenerationRequest,
    GenerationResult,
    build_generation_provider,
    is_loopback_url,
)
from .models import Decision, ModelRun
from .schemas import SourceCreate

REAL_MODEL_SCHEMA = "proofline.real-model-comparison.v1"
PROMPT_VERSIONS = ("memory-candidate-extraction-v1", "grounded-answer-v1")


class RealModelProviderSpec(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    locality: Literal["local", "remote"]
    provider: Literal["qwen", "deepseek", "ollama", "vllm", "openai_compatible"]
    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1, max_length=200)
    model_revision: str = Field(min_length=1, max_length=200)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    input_usd_per_million_tokens: float = Field(ge=0)
    output_usd_per_million_tokens: float = Field(ge=0)
    execution_mode: Literal["real", "mock"] = "real"

    @model_validator(mode="after")
    def validate_boundary(self) -> RealModelProviderSpec:
        unpinned = self.model_id.casefold().startswith(
            "replace-"
        ) or self.model_revision.casefold().startswith("replace-")
        if unpinned:
            raise ValueError("model_id and model_revision must be pinned before preflight")
        loopback = is_loopback_url(self.base_url)
        if self.locality == "local" and not loopback:
            raise ValueError("local providers require a loopback base_url")
        if self.locality == "remote" and loopback:
            raise ValueError("remote providers cannot use a loopback base_url")
        if self.locality == "remote" and not self.api_key_env:
            raise ValueError("remote providers require api_key_env")
        return self


class RealModelComparisonPlan(BaseModel):
    schema_version: Literal[REAL_MODEL_SCHEMA]
    extraction_dataset: str = Field(min_length=1)
    grounded_dataset: str = Field(min_length=1)
    providers: list[RealModelProviderSpec] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_comparison(self) -> RealModelComparisonPlan:
        names = [provider.name for provider in self.providers]
        if len(set(names)) != len(names):
            raise ValueError("provider names must be unique")
        localities = {provider.locality for provider in self.providers}
        if localities != {"local", "remote"}:
            raise ValueError("comparison requires at least one local and one remote provider")
        modes = {provider.execution_mode for provider in self.providers}
        if len(modes) != 1:
            raise ValueError("a comparison cannot mix mock and real providers")
        return self


class DatasetReceipt(BaseModel):
    kind: Literal["extraction", "grounded_qa"]
    configured_path: str
    sha256: str
    version: str
    provenance: str


class ProviderPreflightReceipt(BaseModel):
    name: str
    locality: Literal["local", "remote"]
    provider_id: str
    model_id: str
    model_revision: str
    base_url: str
    prompt_versions: tuple[str, ...]
    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float
    status: Literal["ready", "blocked"]
    error_code: str | None = None
    execution_mode: Literal["real", "mock"]


class RealModelPreflightReceipt(BaseModel):
    schema_version: Literal[REAL_MODEL_SCHEMA]
    receipt_kind: Literal["preflight"] = "preflight"
    observed_at: datetime
    proofline_version: str
    proofline_revision: str
    plan_sha256: str
    status: Literal["ready", "blocked"]
    qualification: str
    datasets: list[DatasetReceipt]
    providers: list[ProviderPreflightReceipt]
    metric_definitions: dict[str, str]


class ProviderCallObservation(BaseModel):
    template_version: str
    status: Literal["succeeded", "failed"]
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class UsageSummary(BaseModel):
    call_count: int
    succeeded_count: int
    failed_count: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms_total: float
    latency_ms_p50: float
    latency_ms_p95: float
    estimated_cost_usd: float
    calls: list[ProviderCallObservation]


class ProviderComparisonResult(BaseModel):
    name: str
    locality: Literal["local", "remote"]
    provider_id: str
    model_id: str
    model_revision: str
    execution_mode: Literal["real", "mock"]
    status: Literal["completed", "failed"]
    extraction: ExtractionEvaluationReport | None = None
    grounded_qa: GroundedEvaluationReport | None = None
    abstention_accuracy: float | None = None
    usage: UsageSummary | None = None
    error_code: str | None = None


class RealModelComparisonReceipt(BaseModel):
    schema_version: Literal[REAL_MODEL_SCHEMA]
    receipt_kind: Literal["comparison"] = "comparison"
    evidence_class: Literal["real_model", "mock_integration"]
    observed_at: datetime
    proofline_version: str
    proofline_revision: str
    plan_sha256: str
    status: Literal["completed", "partial", "failed"]
    qualification: str
    datasets: list[DatasetReceipt]
    providers: list[ProviderComparisonResult]
    metric_definitions: dict[str, str]


class ComparisonObservedProvider:
    def __init__(self, provider: GenerationProvider) -> None:
        self.provider = provider
        self.id = provider.id
        self.model = provider.model
        self.calls: list[ProviderCallObservation] = []

    def capabilities(self):
        return self.provider.capabilities()

    def health(self) -> bool:
        return self.provider.health()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter_ns()
        try:
            result = self.provider.generate(request)
        except Exception:
            self.calls.append(
                ProviderCallObservation(
                    template_version=request.template_version,
                    status="failed",
                    latency_ms=(time.perf_counter_ns() - started) / 1_000_000,
                )
            )
            raise
        self.calls.append(
            ProviderCallObservation(
                template_version=request.template_version,
                status="succeeded",
                latency_ms=(time.perf_counter_ns() - started) / 1_000_000,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
        )
        return result


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_real_model_plan(path: Path) -> tuple[RealModelComparisonPlan, bytes]:
    raw = path.read_bytes()
    return RealModelComparisonPlan.model_validate_json(raw), raw


def _dataset_receipt(plan_path: Path, kind: str, configured_path: str) -> DatasetReceipt:
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = (plan_path.parent / path).resolve()
    raw = path.read_bytes()
    payload = json.loads(raw)
    return DatasetReceipt(
        kind=kind,
        configured_path=configured_path,
        sha256=_sha256(raw),
        version=payload["version"],
        provenance=payload["provenance"],
    )


def _resolve_dataset_path(plan_path: Path, configured_path: str) -> Path:
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else (plan_path.parent / path).resolve()


def _build_provider(spec: RealModelProviderSpec, api_key: str | None) -> GenerationProvider:
    settings = Settings(
        database_url="sqlite://",
        cors_origins=(),
        ai_provider=spec.provider,
        ai_base_url=spec.base_url,
        ai_model=spec.model_id,
        ai_api_key=api_key,
        allow_remote_ai=spec.locality == "remote",
    )
    provider = build_generation_provider(settings)
    if provider is None:
        raise ValueError("generation provider is disabled")
    return provider


def preflight_real_model_plan(
    path: Path,
    *,
    environ: dict[str, str] | None = None,
    health_check: Callable[[GenerationProvider], bool] | None = None,
    provider_factory: Callable[
        [RealModelProviderSpec, str | None], GenerationProvider
    ] = _build_provider,
) -> RealModelPreflightReceipt:
    plan, raw = load_real_model_plan(path)
    environment = os.environ if environ is None else environ
    check = health_check or (lambda provider: provider.health())
    datasets = [
        _dataset_receipt(path, "extraction", plan.extraction_dataset),
        _dataset_receipt(path, "grounded_qa", plan.grounded_dataset),
    ]
    provider_receipts: list[ProviderPreflightReceipt] = []
    for spec in plan.providers:
        api_key = environment.get(spec.api_key_env) if spec.api_key_env else None
        error_code = None
        if spec.locality == "remote" and not api_key:
            error_code = "credential_missing"
        else:
            provider = provider_factory(spec, api_key)
            if not check(provider):
                error_code = "provider_unavailable"
        provider_receipts.append(
            ProviderPreflightReceipt(
                name=spec.name,
                locality=spec.locality,
                provider_id=spec.provider,
                model_id=spec.model_id,
                model_revision=spec.model_revision,
                base_url=spec.base_url,
                prompt_versions=PROMPT_VERSIONS,
                input_usd_per_million_tokens=spec.input_usd_per_million_tokens,
                output_usd_per_million_tokens=spec.output_usd_per_million_tokens,
                status="blocked" if error_code else "ready",
                error_code=error_code,
                execution_mode=spec.execution_mode,
            )
        )
    ready = all(provider.status == "ready" for provider in provider_receipts)
    return RealModelPreflightReceipt(
        schema_version=REAL_MODEL_SCHEMA,
        observed_at=datetime.now(UTC),
        proofline_version=__version__,
        proofline_revision=_git_revision(),
        plan_sha256=_sha256(raw),
        status="ready" if ready else "blocked",
        qualification=(
            "Preflight only. This receipt proves configuration and endpoint readiness; it does "
            "not contain real-model quality, latency, cost, or pilot evidence."
        ),
        datasets=datasets,
        providers=provider_receipts,
        metric_definitions={
            "extraction_precision": "exact matched memories divided by model-extracted memories",
            "extraction_recall": "exact matched memories divided by expected memories",
            "citation_precision": "relevant resolved citations divided by resolved citations",
            "abstention_accuracy": "expected insufficient-evidence queries correctly abstained",
            "latency_ms": "wall-clock provider latency recorded per persisted model run",
            "estimated_cost_usd": (
                "provider-reported tokens multiplied by declared per-token prices"
            ),
        },
    )


def _model_key(source_uri: str, memory: Decision) -> tuple[str, str, str]:
    return source_uri, memory.kind, memory.statement


def _expected_model_key(source_uri: str, expected) -> tuple[str, str, str]:
    return source_uri, expected.kind, expected.statement


def evaluate_model_extraction_dataset(
    dataset_path: Path, provider: GenerationProvider
) -> ExtractionEvaluationReport:
    dataset = ExtractionEvaluationDataset.model_validate_json(
        dataset_path.read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="proofline-model-extraction-") as temporary_directory:
        engine = make_engine(f"sqlite:///{Path(temporary_directory) / 'evaluation.db'}")
        initialize_database(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with factory() as session:
                source_uri_by_id: dict[str, str] = {}
                expected_by_key = {}
                for item in dataset.sources:
                    source, _created = ingest_source(
                        session,
                        SourceCreate(title=item.title, uri=item.uri, content=item.content),
                    )
                    source_uri_by_id[source.id] = item.uri
                    for expected in item.expected_memories:
                        expected_by_key[_expected_model_key(item.uri, expected)] = expected
                    extract_memory_candidates(session, source, provider)

                memories = list(
                    session.scalars(
                        select(Decision)
                        .where(Decision.extraction_method == "model")
                        .order_by(Decision.id)
                    ).all()
                )
                model_run_count = session.scalar(select(func.count()).select_from(ModelRun)) or 0
                actual_by_key: dict[tuple[str, str, str], list[Decision]] = defaultdict(list)
                evidence_valid = {}
                for memory in memories:
                    key = _model_key(source_uri_by_id[memory.source_id], memory)
                    actual_by_key[key].append(memory)
                    evidence_valid[memory.id] = _memory_evidence_is_exact(session, memory)

                expected_counter = Counter(expected_by_key.keys())
                actual_counter = Counter({key: len(rows) for key, rows in actual_by_key.items()})
                matched_counter = expected_counter & actual_counter
                expected_count = sum(expected_counter.values())
                extracted_count = sum(actual_counter.values())
                matched_count = sum(matched_counter.values())
                precision, recall, f1 = _classification_metrics(
                    expected_count, extracted_count, matched_count
                )
                evidence_valid_count = sum(evidence_valid.values())
                expected_evidence_matches = 0
                for key, matched in matched_counter.items():
                    expected = expected_by_key[key]
                    candidates = actual_by_key[key]
                    relevant = sum(
                        evidence_valid[memory.id]
                        and any(
                            expected.evidence_quote in evidence.quote
                            for evidence in memory.evidence
                        )
                        for memory in candidates
                    )
                    expected_evidence_matches += min(matched, relevant)

                kinds = []
                for kind in ("decision", "assumption", "constraint", "alternative"):
                    kind_expected = sum(v for k, v in expected_counter.items() if k[1] == kind)
                    kind_extracted = sum(v for k, v in actual_counter.items() if k[1] == kind)
                    kind_matched = sum(v for k, v in matched_counter.items() if k[1] == kind)
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

                sources = []
                negative_count = 0
                negative_correct = 0
                for item in dataset.sources:
                    expected_for_source = sum(
                        value for key, value in expected_counter.items() if key[0] == item.uri
                    )
                    extracted_for_source = sum(
                        value for key, value in actual_counter.items() if key[0] == item.uri
                    )
                    matched_for_source = sum(
                        value for key, value in matched_counter.items() if key[0] == item.uri
                    )
                    evidence_for_source = sum(
                        evidence_valid[memory.id]
                        for key, rows in actual_by_key.items()
                        if key[0] == item.uri
                        for memory in rows
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


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _usage_summary(
    spec: RealModelProviderSpec, calls: list[ProviderCallObservation]
) -> UsageSummary:
    prompt_tokens = sum(call.prompt_tokens or 0 for call in calls)
    completion_tokens = sum(call.completion_tokens or 0 for call in calls)
    estimated_cost = (
        prompt_tokens * spec.input_usd_per_million_tokens
        + completion_tokens * spec.output_usd_per_million_tokens
    ) / 1_000_000
    latencies = [call.latency_ms for call in calls]
    return UsageSummary(
        call_count=len(calls),
        succeeded_count=sum(call.status == "succeeded" for call in calls),
        failed_count=sum(call.status == "failed" for call in calls),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms_total=sum(latencies),
        latency_ms_p50=_percentile(latencies, 50),
        latency_ms_p95=_percentile(latencies, 95),
        estimated_cost_usd=estimated_cost,
        calls=calls,
    )


def _abstention_accuracy(report: GroundedEvaluationReport) -> float:
    rows = [row for row in report.queries if row.expected_status == "insufficient_evidence"]
    if not rows:
        return 1.0
    return sum(row.actual_status == "insufficient_evidence" for row in rows) / len(rows)


def run_real_model_comparison(
    path: Path,
    *,
    environ: dict[str, str] | None = None,
    health_check: Callable[[GenerationProvider], bool] | None = None,
    provider_factory: Callable[
        [RealModelProviderSpec, str | None], GenerationProvider
    ] = _build_provider,
) -> RealModelComparisonReceipt:
    plan, raw = load_real_model_plan(path)
    if plan.providers[0].execution_mode == "mock" and provider_factory is _build_provider:
        raise ValueError("mock comparison requires an injected provider factory")
    environment = os.environ if environ is None else environ
    preflight = preflight_real_model_plan(
        path,
        environ=environment,
        health_check=health_check,
        provider_factory=provider_factory,
    )
    if preflight.status != "ready":
        raise ValueError("real-model comparison preflight is blocked")

    extraction_path = _resolve_dataset_path(path, plan.extraction_dataset)
    grounded_path = _resolve_dataset_path(path, plan.grounded_dataset)
    results = []
    for spec in plan.providers:
        api_key = environment.get(spec.api_key_env) if spec.api_key_env else None
        observed = ComparisonObservedProvider(provider_factory(spec, api_key))
        try:
            extraction = evaluate_model_extraction_dataset(extraction_path, observed)
            grounded = evaluate_grounded_dataset(grounded_path, provider=observed)
            results.append(
                ProviderComparisonResult(
                    name=spec.name,
                    locality=spec.locality,
                    provider_id=spec.provider,
                    model_id=spec.model_id,
                    model_revision=spec.model_revision,
                    execution_mode=spec.execution_mode,
                    status="completed",
                    extraction=extraction,
                    grounded_qa=grounded,
                    abstention_accuracy=_abstention_accuracy(grounded),
                    usage=_usage_summary(spec, observed.calls),
                )
            )
        except Exception:
            results.append(
                ProviderComparisonResult(
                    name=spec.name,
                    locality=spec.locality,
                    provider_id=spec.provider,
                    model_id=spec.model_id,
                    model_revision=spec.model_revision,
                    execution_mode=spec.execution_mode,
                    status="failed",
                    usage=_usage_summary(spec, observed.calls),
                    error_code="provider_evaluation_failed",
                )
            )
    completed = sum(result.status == "completed" for result in results)
    status = "completed" if completed == len(results) else "partial" if completed else "failed"
    mock = plan.providers[0].execution_mode == "mock"
    return RealModelComparisonReceipt(
        schema_version=REAL_MODEL_SCHEMA,
        evidence_class="mock_integration" if mock else "real_model",
        observed_at=datetime.now(UTC),
        proofline_version=__version__,
        proofline_revision=_git_revision(),
        plan_sha256=_sha256(raw),
        status=status,
        qualification=(
            "Mock integration receipt. It validates the comparison pipeline and calculations but "
            "is not real-model quality, cost, latency, or pilot evidence."
            if mock
            else "Real-model results on the frozen evaluation corpus; not external-pilot evidence."
        ),
        datasets=preflight.datasets,
        providers=results,
        metric_definitions=preflight.metric_definitions,
    )


def write_preflight_receipt(
    output: Path, receipt: RealModelPreflightReceipt, *, force: bool = False
) -> None:
    if output.exists() and not force:
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="real-model-", suffix=".json", dir=output.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(receipt.model_dump_json(indent=2))
            handle.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_comparison_receipt(
    output: Path, receipt: RealModelComparisonReceipt, *, force: bool = False
) -> None:
    if output.exists() and not force:
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="real-model-comparison-", suffix=".json", dir=output.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(receipt.model_dump_json(indent=2))
            handle.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
