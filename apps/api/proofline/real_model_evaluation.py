from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from . import __version__
from .config import Settings
from .model_gateway import GenerationProvider, build_generation_provider, is_loopback_url

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
            provider = _build_provider(spec, api_key)
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
