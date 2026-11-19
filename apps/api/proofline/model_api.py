from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import provider_runtime, secret_store
from .api import resolve_workspace_id
from .config import get_settings, load_provider_config, provider_config_path, save_provider_config
from .database import get_session
from .embeddings import index_current_embeddings
from .extraction import (
    CandidateExtractionError,
    extract_memory_candidates,
)
from .model_gateway import (
    EmbeddingValidationError,
    ProviderConfigurationError,
    ProviderRequestError,
    StructuredOutputError,
    build_embedding_provider,
)
from .models import (
    ModelRun,
    Source,
    SourceVersion,
)
from .schemas import (
    EmbeddingIndexResponse,
    ModelRunRead,
    ModelRunRetryRequest,
    ModelRunRetryResponse,
    ProviderConfigurationRead,
    ProviderConfigurationUpdate,
    ProviderStatus,
)

router: APIRouter = APIRouter()


@router.get("/model/provider", response_model=ProviderStatus)
def model_provider_status(check_health: bool = False) -> ProviderStatus:
    settings = get_settings()
    try:
        provider = provider_runtime.build_generation_provider(settings)
    except ProviderConfigurationError:
        return ProviderStatus(
            configured=False,
            remote_egress_allowed=settings.allow_remote_ai,
            error_code="provider_configuration_invalid",
            mode="degraded",
        )
    if provider is None:
        return ProviderStatus(
            configured=False,
            remote_egress_allowed=settings.allow_remote_ai,
            error_code="provider_disabled",
            mode="disabled",
        )
    capabilities = provider.capabilities()
    healthy = provider.health() if check_health else None
    return ProviderStatus(
        configured=True,
        provider_id=provider.id,
        model_id=provider.model,
        generation=capabilities.generation,
        structured_output=capabilities.structured_output,
        remote_egress_allowed=settings.allow_remote_ai,
        healthy=healthy,
        mode="ready" if healthy else "degraded" if healthy is False else "unchecked",
    )


@router.get("/model/embedding-provider", response_model=ProviderStatus)
def embedding_provider_status(check_health: bool = False) -> ProviderStatus:
    settings = get_settings()
    try:
        provider = build_embedding_provider(settings)
    except ProviderConfigurationError:
        return ProviderStatus(
            configured=False,
            remote_egress_allowed=settings.allow_remote_ai,
            error_code="embedding_provider_configuration_invalid",
            mode="degraded",
        )
    if provider is None:
        return ProviderStatus(
            configured=False,
            remote_egress_allowed=settings.allow_remote_ai,
            error_code="embedding_provider_disabled",
            mode="disabled",
        )
    healthy = provider.health() if check_health else None
    return ProviderStatus(
        configured=True,
        provider_id=provider.id,
        model_id=provider.model,
        generation=False,
        structured_output=False,
        embedding=True,
        remote_egress_allowed=settings.allow_remote_ai,
        healthy=healthy,
        mode="ready" if healthy else "degraded" if healthy is False else "unchecked",
    )


def provider_configuration_read() -> ProviderConfigurationRead:
    settings = get_settings()
    return ProviderConfigurationRead(
        ai_provider=settings.ai_provider,
        ai_base_url=settings.ai_base_url,
        ai_model=settings.ai_model,
        ai_api_key_configured=bool(settings.ai_api_key),
        embedding_provider=settings.embedding_provider,
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model,
        embedding_api_key_configured=bool(settings.embedding_api_key),
        allow_remote_ai=settings.allow_remote_ai,
        secret_storage=secret_store.provider_secret_storage_kind(),
    )


@router.get("/model/configuration", response_model=ProviderConfigurationRead)
def get_provider_configuration() -> ProviderConfigurationRead:
    return provider_configuration_read()


@router.put("/model/configuration", response_model=ProviderConfigurationRead)
def update_provider_configuration(
    payload: ProviderConfigurationUpdate,
) -> ProviderConfigurationRead:
    existing = load_provider_config()
    values = payload.model_dump(exclude={"ai_api_key", "embedding_api_key"})
    platform_secrets = secret_store.get_provider_secret_store(provider_config_path())
    if platform_secrets is not None:
        return _update_provider_configuration_with_secret_store(
            payload, existing, values, platform_secrets
        )
    for field in ("ai_api_key", "embedding_api_key"):
        supplied = getattr(payload, field)
        if supplied is not None:
            if supplied:
                values[field] = supplied
            else:
                existing.pop(field, None)
        elif field in existing:
            values[field] = existing[field]
    candidate = existing | values
    save_provider_config(candidate)
    try:
        settings = get_settings()
        provider_runtime.build_generation_provider(settings)
        build_embedding_provider(settings)
    except ProviderConfigurationError as exc:
        save_provider_config(existing)
        raise HTTPException(status_code=422, detail="Provider configuration is invalid") from exc
    return provider_configuration_read()


def _update_provider_configuration_with_secret_store(
    payload: ProviderConfigurationUpdate,
    existing: dict,
    values: dict,
    platform_secrets: secret_store.ProviderSecretStore,
) -> ProviderConfigurationRead:
    fields = ("ai_api_key", "embedding_api_key")
    try:
        previous_secrets = {field: platform_secrets.get(field) for field in fields}
    except secret_store.ProviderSecretStoreError as exc:
        raise HTTPException(status_code=503, detail="OS keyring is unavailable") from exc
    candidate = existing | values
    try:
        for field in fields:
            supplied = getattr(payload, field)
            if supplied is not None:
                if supplied:
                    platform_secrets.set(field, supplied)
                else:
                    platform_secrets.delete(field)
            elif previous_secrets[field] is None and existing.get(field):
                platform_secrets.set(field, existing[field])
            candidate.pop(field, None)
        save_provider_config(candidate)
        settings = get_settings()
        provider_runtime.build_generation_provider(settings)
        build_embedding_provider(settings)
    except (ProviderConfigurationError, secret_store.ProviderSecretStoreError) as exc:
        save_provider_config(existing)
        _restore_provider_secrets(platform_secrets, previous_secrets)
        if isinstance(exc, secret_store.ProviderSecretStoreError):
            raise HTTPException(status_code=503, detail="OS keyring is unavailable") from exc
        raise HTTPException(status_code=422, detail="Provider configuration is invalid") from exc
    return provider_configuration_read()


def _restore_provider_secrets(
    platform_secrets: secret_store.ProviderSecretStore,
    previous: dict[str, str | None],
) -> None:
    for field, value in previous.items():
        if value is None:
            platform_secrets.delete(field)
        else:
            platform_secrets.set(field, value)


@router.get("/model/reranking-provider", response_model=ProviderStatus)
def reranking_provider_status() -> ProviderStatus:
    return ProviderStatus(
        configured=False,
        reranking=False,
        mode="disabled",
        error_code="reranking_provider_disabled",
    )


@router.post("/model/embeddings/index", response_model=EmbeddingIndexResponse)
def index_embeddings(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> EmbeddingIndexResponse:
    try:
        provider = build_embedding_provider(get_settings())
        if provider is None:
            raise HTTPException(status_code=409, detail="Embedding provider is disabled")
        report = index_current_embeddings(session, provider, workspace_id=workspace_id)
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=409, detail="Embedding provider configuration is invalid"
        ) from exc
    except (ProviderRequestError, EmbeddingValidationError) as exc:
        raise HTTPException(status_code=502, detail="Embedding provider request failed") from exc
    return EmbeddingIndexResponse(
        indexed=report.indexed,
        skipped=report.skipped,
        model_run_ids=report.model_run_ids,
    )


@router.get("/model/runs", response_model=list[ModelRunRead])
def list_model_runs(
    run_status: str | None = Query(default=None, alias="status"),
    operation: str | None = None,
    provider_id: str | None = None,
    parent_run_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[ModelRun]:
    query = select(ModelRun).where(ModelRun.workspace_id == workspace_id)
    if run_status:
        query = query.where(ModelRun.status == run_status)
    if operation:
        query = query.where(ModelRun.operation == operation)
    if provider_id:
        query = query.where(ModelRun.provider_id == provider_id)
    if parent_run_id:
        query = query.where(ModelRun.parent_run_id == parent_run_id)
    return list(session.scalars(query.order_by(ModelRun.created_at.desc()).limit(limit)).all())


@router.post("/model/runs/{run_id}/retry", response_model=ModelRunRetryResponse)
def retry_model_run(
    run_id: str,
    payload: ModelRunRetryRequest,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> ModelRunRetryResponse:
    parent = session.get(ModelRun, run_id)
    if not parent or parent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Model run not found")
    if parent.status not in {"failed", "dead_letter"}:
        raise HTTPException(status_code=409, detail="Only failed model runs can be retried")
    source = session.get(Source, payload.source_id)
    if not source or source.workspace_id != workspace_id or not source.current_version_id:
        raise HTTPException(status_code=404, detail="Source not found")
    version = session.get(SourceVersion, source.current_version_id)
    if not version or version.content_hash not in parent.input_hashes:
        raise HTTPException(
            status_code=409,
            detail="Retry source revision does not match the original immutable input",
        )
    try:
        provider = provider_runtime.build_generation_provider(get_settings())
        if provider is None:
            raise HTTPException(status_code=409, detail="AI provider is disabled")
        if provider.id != parent.provider_id or provider.model != parent.model_id:
            raise HTTPException(
                status_code=409,
                detail="Configured provider must match the failed run; fallback is disabled",
            )
        memories, run = extract_memory_candidates(
            session, source, provider, retry_parent_run_id=parent.id
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=409, detail="AI provider configuration is invalid") from exc
    except (ProviderRequestError, StructuredOutputError, CandidateExtractionError) as exc:
        retry_run_id = getattr(exc, "run_id", None)
        raise HTTPException(
            status_code=502,
            detail="Model-run retry failed and remains inspectable",
            headers={"X-Proofline-Model-Run-ID": retry_run_id} if retry_run_id else None,
        ) from exc
    return ModelRunRetryResponse(
        parent_run_id=parent.id,
        model_run_id=run.id,
        status=run.status,
        memory_count=len(memories),
    )


@router.get("/model/runs/{run_id}", response_model=ModelRunRead)
def get_model_run(
    run_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> ModelRun:
    run = session.get(ModelRun, run_id)
    if not run or run.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Model run not found")
    return run
