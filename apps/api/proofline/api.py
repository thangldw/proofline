from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import secret_store
from .config import get_settings, load_provider_config, provider_config_path, save_provider_config
from .database import get_session
from .embeddings import hybrid_search, index_current_embeddings
from .extraction import (
    CandidateExtractionError,
    extract_decision_candidates,
    extract_memory_candidates,
)
from .folder_scanning import FolderScanError
from .git_ingestion import GitIngestionError, import_git_repository
from .grounding import EvidenceIntegrityError, GroundingValidationError, answer_question
from .ingestion import (
    IngestionConflict,
    IngestionExecutionError,
    IngestionIdempotencyConflict,
    IngestionJobNotFound,
    IngestionRetryConflict,
    delete_source,
    retry_ingestion_job,
    run_ingestion_job,
    source_deletion_impact,
)
from .model_gateway import (
    EmbeddingValidationError,
    ProviderConfigurationError,
    ProviderRequestError,
    StructuredOutputError,
    build_embedding_provider,
    build_generation_provider,
)
from .models import (
    DEFAULT_WORKSPACE_ID,
    ActionProposal,
    AuditEvent,
    Chunk,
    Decision,
    Evidence,
    GitRepository,
    IngestionJob,
    ModelRun,
    ProposalCitation,
    Source,
    SourceVersion,
    Workspace,
    utc_now,
)
from .notes import parse_note_links, parse_note_tags
from .reranking import DeterministicTokenReranker
from .schemas import (
    ActionProposalCreate,
    ActionProposalRead,
    ActionProposalReview,
    AnswerRequest,
    AnswerResponse,
    AuditEventRead,
    DecisionRead,
    DecisionUpdate,
    EmbeddingIndexResponse,
    FolderScanRequest,
    FolderScanResponse,
    FolderWatchStatus,
    GitRepositoryCreate,
    GitRepositoryImportResponse,
    GitRepositoryRead,
    IngestionJobRead,
    MemoryKind,
    MemoryRead,
    MemoryUpdate,
    ModelRunRead,
    ModelRunRetryRequest,
    ModelRunRetryResponse,
    NoteRead,
    Overview,
    ProviderConfigurationRead,
    ProviderConfigurationUpdate,
    ProviderStatus,
    SearchResponse,
    SourceCreate,
    SourceDeletionImpactRead,
    SourceRead,
    SourceVersionContentRead,
    SourceVersionRead,
    WorkspaceCreate,
    WorkspaceRead,
    normalize_retrieval_filters,
)

router = APIRouter(prefix="/api/v1")


def resolve_workspace_id(
    workspace_id: str = Header(default=DEFAULT_WORKSPACE_ID, alias="X-Proofline-Workspace-ID"),
    session: Session = Depends(get_session),
) -> str:
    if not session.get(Workspace, workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace_id


def get_workspace_source(session: Session, source_id: str, workspace_id: str) -> Source:
    source = session.get(Source, source_id)
    if not source or source.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.post("/workspaces", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate, session: Session = Depends(get_session)
) -> Workspace:
    workspace = Workspace(slug=payload.slug, title=payload.title)
    session.add(workspace)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Workspace slug already exists") from exc
    session.refresh(workspace)
    return workspace


@router.get("/workspaces", response_model=list[WorkspaceRead])
def list_workspaces(session: Session = Depends(get_session)) -> list[Workspace]:
    return list(
        session.scalars(select(Workspace).order_by(Workspace.created_at, Workspace.id)).all()
    )


def git_repository_to_read(repository: GitRepository) -> GitRepositoryRead:
    return GitRepositoryRead.model_validate(repository).model_copy(
        update={
            "source_count": len(repository.sources),
            "file_count": sum(source.kind == "git_file" for source in repository.sources),
            "commit_count": sum(source.kind == "git_commit" for source in repository.sources),
        }
    )


def source_to_read(source: Source) -> SourceRead:
    return SourceRead(
        **{column.name: getattr(source, column.name) for column in Source.__table__.columns},
        version_count=len(source.versions),
        chunk_count=sum(
            chunk.source_version_id == source.current_version_id for chunk in source.chunks
        ),
        decision_count=sum(
            decision.source_version_id == source.current_version_id and decision.kind == "decision"
            for decision in source.decisions
        ),
        memory_count=sum(
            memory.source_version_id == source.current_version_id for memory in source.decisions
        ),
    )


def note_to_read(source: Source, notes: list[Source] | None = None) -> NoteRead:
    links = parse_note_links(source.content)
    title_candidates: dict[str, list[str]] = {}
    for note in notes or []:
        title_candidates.setdefault(note.title.casefold(), []).append(note.id)
    links = [
        link.model_copy(
            update={
                "resolved_source_id": (
                    candidates[0]
                    if len(candidates := title_candidates.get(link.target_title.casefold(), []))
                    == 1
                    else None
                )
            }
        )
        for link in links
    ]
    return NoteRead(
        id=source.id,
        workspace_id=source.workspace_id,
        title=source.title,
        content=source.content,
        uri=source.uri or "",
        current_version_id=source.current_version_id or "",
        version_count=len(source.versions),
        created_at=source.created_at,
        indexed_at=source.indexed_at,
        tags=parse_note_tags(source.content),
        links=links,
    )


def decision_to_read(decision: Decision, source_title: str | None = None) -> DecisionRead:
    return DecisionRead.model_validate(decision).model_copy(
        update={
            "source_title": source_title,
            "evidence": [item for item in decision.evidence if item.binding_state == "active"],
        }
    )


def decision_snapshot(decision: Decision) -> dict[str, str | None]:
    return {
        "kind": decision.kind,
        "title": decision.title,
        "statement": decision.statement,
        "rationale": decision.rationale,
        "status": decision.status,
        "valid_from": decision.valid_from.isoformat() if decision.valid_from else None,
        "valid_to": decision.valid_to.isoformat() if decision.valid_to else None,
        "updated_at": decision.updated_at.isoformat(),
    }


def apply_memory_update(
    session: Session,
    memory: Decision,
    changes: dict,
    *,
    object_type: str,
    action: str,
) -> DecisionRead:
    workspace_id = session.scalar(select(Source.workspace_id).where(Source.id == memory.source_id))
    before = decision_snapshot(memory)
    for field, value in changes.items():
        setattr(memory, field, value)
    memory.updated_at = utc_now()
    after = decision_snapshot(memory)
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor="local_user",
            action=action,
            object_type=object_type,
            object_id=memory.id,
            before_json=before,
            after_json=after,
        )
    )
    session.commit()
    source_title = session.scalar(select(Source.title).where(Source.id == memory.source_id))
    session.refresh(memory)
    return decision_to_read(memory, source_title)


@router.get("/overview", response_model=Overview)
def overview(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> Overview:
    return Overview(
        sources=session.scalar(
            select(func.count()).select_from(Source).where(Source.workspace_id == workspace_id)
        )
        or 0,
        chunks=session.scalar(
            select(func.count())
            .select_from(Chunk)
            .join(Source)
            .where(
                Chunk.source_version_id == Source.current_version_id,
                Source.workspace_id == workspace_id,
            )
        )
        or 0,
        decisions=session.scalar(
            select(func.count())
            .select_from(Decision)
            .join(Source)
            .where(
                Decision.source_version_id == Source.current_version_id,
                Decision.kind == "decision",
                Source.workspace_id == workspace_id,
            )
        )
        or 0,
        memories=session.scalar(
            select(func.count())
            .select_from(Decision)
            .join(Source)
            .where(
                Decision.source_version_id == Source.current_version_id,
                Source.workspace_id == workspace_id,
            )
        )
        or 0,
        evidence=session.scalar(
            select(func.count())
            .select_from(Evidence)
            .join(Source)
            .where(
                Evidence.source_version_id == Source.current_version_id,
                Source.workspace_id == workspace_id,
            )
        )
        or 0,
    )


@router.post("/sources", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    response: Response,
    workspace_id: str = Depends(resolve_workspace_id),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
        pattern=r".*\S.*",
    ),
    session: Session = Depends(get_session),
) -> SourceRead:
    payload = payload.model_copy(update={"workspace_id": workspace_id})
    try:
        source, created, job = run_ingestion_job(session, payload, idempotency_key=idempotency_key)
    except IngestionIdempotencyConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"X-Proofline-Job-ID": exc.job_id or ""},
        ) from exc
    except IngestionConflict as exc:
        headers = {"X-Proofline-Job-ID": exc.job_id} if exc.job_id else None
        raise HTTPException(status_code=409, detail=str(exc), headers=headers) from exc
    except IngestionExecutionError as exc:
        raise HTTPException(
            status_code=500,
            detail="ingestion failed; inspect the persisted job",
            headers={"X-Proofline-Job-ID": exc.job_id},
        ) from exc
    response.headers["X-Proofline-Job-ID"] = job.id
    if not created:
        response.status_code = status.HTTP_200_OK
    hydrated = session.scalar(
        select(Source)
        .where(Source.id == source.id)
        .options(
            selectinload(Source.versions),
            selectinload(Source.chunks),
            selectinload(Source.decisions),
        )
    )
    if hydrated is None:
        raise HTTPException(status_code=404, detail="source_not_found")
    return source_to_read(hydrated)


@router.post("/folder-scans", response_model=FolderScanResponse)
def create_folder_scan(
    payload: FolderScanRequest,
    request: Request,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> FolderScanResponse:
    payload = payload.model_copy(update={"workspace_id": workspace_id})
    try:
        return request.app.state.folder_scan_coordinator.scan(
            session, payload, get_settings().import_roots
        )
    except FolderScanError as exc:
        status_code = (
            status.HTTP_409_CONFLICT
            if exc.code
            in {
                "import_roots_disabled",
                "import_root_unavailable",
                "missing_confirmation_mismatch",
                "missing_deletion_scan_failed",
                "missing_deletion_failed",
            }
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.post(
    "/git-repositories",
    response_model=GitRepositoryImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_git_repository(
    payload: GitRepositoryCreate,
    response: Response,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> GitRepositoryImportResponse:
    payload = payload.model_copy(update={"workspace_id": workspace_id})
    try:
        repository, commit_sha, created, unchanged, failures = import_git_repository(
            session, payload
        )
    except GitIngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    if unchanged:
        response.status_code = status.HTTP_200_OK
    session.refresh(repository, attribute_names=["sources"])
    return GitRepositoryImportResponse(
        repository=git_repository_to_read(repository),
        commit_sha=commit_sha,
        created_count=created,
        unchanged_count=unchanged,
        failed_count=len(failures),
        failures=failures,
    )


@router.get("/git-repositories", response_model=list[GitRepositoryRead])
def list_git_repositories(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[GitRepositoryRead]:
    repositories = session.scalars(
        select(GitRepository)
        .where(GitRepository.workspace_id == workspace_id)
        .options(selectinload(GitRepository.sources))
        .order_by(GitRepository.indexed_at.desc())
    ).all()
    return [git_repository_to_read(repository) for repository in repositories]


@router.delete("/git-repositories/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_git_repository(
    repository_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> Response:
    repository = session.get(GitRepository, repository_id)
    if not repository or repository.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Git repository not found")
    for source in list(repository.sources):
        delete_source(session, source)
    session.expire(repository, ["sources"])
    session.delete(repository)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/folder-watch", response_model=FolderWatchStatus)
def folder_watch_status(request: Request) -> FolderWatchStatus:
    return FolderWatchStatus.model_validate(request.app.state.folder_watcher.snapshot())


@router.get("/sources", response_model=list[SourceRead])
def list_sources(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[SourceRead]:
    sources = session.scalars(
        select(Source)
        .where(Source.workspace_id == workspace_id)
        .options(
            selectinload(Source.versions),
            selectinload(Source.chunks),
            selectinload(Source.decisions),
        )
        .order_by(Source.indexed_at.desc())
    ).all()
    return [source_to_read(source) for source in sources]


@router.get("/jobs", response_model=list[IngestionJobRead])
def list_jobs(
    job_state: str | None = Query(default=None, alias="state"),
    limit: int = Query(default=50, ge=1, le=200),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[IngestionJob]:
    query = (
        select(IngestionJob)
        .where(IngestionJob.workspace_id == workspace_id)
        .order_by(IngestionJob.updated_at.desc())
        .limit(limit)
    )
    if job_state:
        query = query.where(IngestionJob.state == job_state)
    return list(session.scalars(query).all())


@router.get("/jobs/{job_id}", response_model=IngestionJobRead)
def get_job(
    job_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> IngestionJob:
    job = session.get(IngestionJob, job_id)
    if not job or job.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


@router.post("/jobs/{job_id}/retry", response_model=IngestionJobRead)
def retry_job(
    job_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> IngestionJob:
    job = session.get(IngestionJob, job_id)
    if not job or job.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    try:
        return retry_ingestion_job(session, job_id)
    except IngestionJobNotFound as exc:
        raise HTTPException(status_code=404, detail="Ingestion job not found") from exc
    except (IngestionRetryConflict, IngestionConflict) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"X-Proofline-Job-ID": job_id},
        ) from exc
    except IngestionExecutionError as exc:
        raise HTTPException(
            status_code=500,
            detail="ingestion retry failed; inspect the persisted job",
            headers={"X-Proofline-Job-ID": exc.job_id},
        ) from exc


@router.get("/model/provider", response_model=ProviderStatus)
def model_provider_status(check_health: bool = False) -> ProviderStatus:
    settings = get_settings()
    try:
        provider = build_generation_provider(settings)
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
        build_generation_provider(settings)
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
        build_generation_provider(settings)
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
        provider = build_generation_provider(get_settings())
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


@router.get("/sources/{source_id}")
def get_source(
    source_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> dict:
    source = get_workspace_source(session, source_id, workspace_id)
    return {
        "id": source.id,
        "title": source.title,
        "kind": source.kind,
        "uri": source.uri,
        "content": source.content,
        "status": source.status,
        "created_at": source.created_at,
        "indexed_at": source.indexed_at,
        "current_version_id": source.current_version_id,
    }


@router.get(
    "/sources/{source_id}/deletion-impact",
    response_model=SourceDeletionImpactRead,
)
def get_source_deletion_impact(
    source_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> SourceDeletionImpactRead:
    source = get_workspace_source(session, source_id, workspace_id)
    impact = source_deletion_impact(session, source)
    return SourceDeletionImpactRead(
        source_id=source.id,
        title=source.title,
        current_version_id=source.current_version_id,
        **impact.__dict__,
    )


@router.get("/sources/{source_id}/versions", response_model=list[SourceVersionRead])
def list_source_versions(
    source_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[SourceVersion]:
    get_workspace_source(session, source_id, workspace_id)
    return list(
        session.scalars(
            select(SourceVersion)
            .where(SourceVersion.source_id == source_id)
            .order_by(SourceVersion.created_at.desc())
        ).all()
    )


@router.post("/sources/{source_id}/extract-decisions", response_model=list[DecisionRead])
def extract_source_decisions(
    source_id: str,
    response: Response,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    source = get_workspace_source(session, source_id, workspace_id)
    try:
        provider = build_generation_provider(get_settings())
        if provider is None:
            raise HTTPException(status_code=409, detail="AI provider is disabled")
        decisions, run = extract_decision_candidates(session, source, provider)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=409, detail="AI provider configuration is invalid") from exc
    except (ProviderRequestError, StructuredOutputError, CandidateExtractionError) as exc:
        run_id = getattr(exc, "run_id", None)
        headers = {"X-Proofline-Model-Run-ID": run_id} if run_id else None
        raise HTTPException(
            status_code=502,
            detail="model output could not produce grounded decision candidates",
            headers=headers,
        ) from exc
    response.headers["X-Proofline-Model-Run-ID"] = run.id
    return [decision_to_read(decision, source.title) for decision in decisions]


@router.post("/sources/{source_id}/extract-memories", response_model=list[MemoryRead])
def extract_source_memories(
    source_id: str,
    response: Response,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[MemoryRead]:
    source = get_workspace_source(session, source_id, workspace_id)
    try:
        provider = build_generation_provider(get_settings())
        if provider is None:
            raise HTTPException(status_code=409, detail="AI provider is disabled")
        memories, run = extract_memory_candidates(session, source, provider)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=409, detail="AI provider configuration is invalid") from exc
    except (ProviderRequestError, StructuredOutputError, CandidateExtractionError) as exc:
        run_id = getattr(exc, "run_id", None)
        headers = {"X-Proofline-Model-Run-ID": run_id} if run_id else None
        raise HTTPException(
            status_code=502,
            detail="model output could not produce grounded memory candidates",
            headers=headers,
        ) from exc
    response.headers["X-Proofline-Model-Run-ID"] = run.id
    return [
        MemoryRead(**decision_to_read(memory, source.title).model_dump()) for memory in memories
    ]


@router.get(
    "/sources/{source_id}/versions/{version_id}",
    response_model=SourceVersionContentRead,
)
def get_source_version(
    source_id: str,
    version_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> SourceVersion:
    get_workspace_source(session, source_id, workspace_id)
    version = session.scalar(
        select(SourceVersion).where(
            SourceVersion.id == version_id, SourceVersion.source_id == source_id
        )
    )
    if not version:
        raise HTTPException(status_code=404, detail="Source version not found")
    return version


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_source(
    source_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> Response:
    source = get_workspace_source(session, source_id, workspace_id)
    delete_source(session, source)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/memories", response_model=list[MemoryRead])
def list_memories(
    memory_kind: MemoryKind | None = Query(default=None, alias="kind"),
    memory_status: str | None = Query(default=None, alias="status"),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    query = (
        select(Decision, Source.title)
        .join(Source)
        .where(
            Decision.source_version_id == Source.current_version_id,
            Source.workspace_id == workspace_id,
        )
        .options(selectinload(Decision.evidence))
        .order_by(Decision.created_at.desc())
    )
    if memory_kind:
        query = query.where(Decision.kind == memory_kind)
    if memory_status:
        query = query.where(Decision.status == memory_status)
    return [decision_to_read(memory, title) for memory, title in session.execute(query).all()]


@router.get("/memories/{memory_id}", response_model=MemoryRead)
def get_memory(
    memory_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionRead:
    row = session.execute(
        select(Decision, Source.title)
        .join(Source)
        .where(Decision.id == memory_id, Source.workspace_id == workspace_id)
        .options(selectinload(Decision.evidence))
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")
    return decision_to_read(row[0], row[1])


@router.patch("/memories/{memory_id}", response_model=MemoryRead)
def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionRead:
    memory = session.scalar(
        select(Decision)
        .join(Source)
        .where(Decision.id == memory_id, Source.workspace_id == workspace_id)
        .options(selectinload(Decision.evidence))
    )
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="No memory changes supplied")
    return apply_memory_update(
        session,
        memory,
        changes,
        object_type="memory",
        action="memory.updated",
    )


@router.get("/decisions", response_model=list[DecisionRead])
def list_decisions(
    decision_status: str | None = Query(default=None, alias="status"),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    query = (
        select(Decision, Source.title)
        .join(Source)
        .where(
            Decision.source_version_id == Source.current_version_id,
            Decision.kind == "decision",
            Source.workspace_id == workspace_id,
        )
        .options(selectinload(Decision.evidence))
        .order_by(Decision.created_at.desc())
    )
    if decision_status:
        query = query.where(Decision.status == decision_status)
    return [decision_to_read(decision, title) for decision, title in session.execute(query).all()]


@router.get("/decisions/{decision_id}", response_model=DecisionRead)
def get_decision(
    decision_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionRead:
    row = session.execute(
        select(Decision, Source.title)
        .join(Source)
        .where(
            Decision.id == decision_id,
            Decision.kind == "decision",
            Source.workspace_id == workspace_id,
        )
        .options(selectinload(Decision.evidence))
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision_to_read(row[0], row[1])


@router.patch("/decisions/{decision_id}", response_model=DecisionRead)
def update_decision(
    decision_id: str,
    payload: DecisionUpdate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionRead:
    decision = session.scalar(
        select(Decision)
        .join(Source)
        .where(
            Decision.id == decision_id,
            Decision.kind == "decision",
            Source.workspace_id == workspace_id,
        )
        .options(selectinload(Decision.evidence))
    )
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="No decision changes supplied")
    return apply_memory_update(
        session,
        decision,
        changes,
        object_type="decision",
        action="decision.updated",
    )


@router.get("/audit-events", response_model=list[AuditEventRead])
def list_audit_events(
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[AuditEvent]:
    query = (
        select(AuditEvent)
        .where(AuditEvent.workspace_id == workspace_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    if object_type:
        query = query.where(AuditEvent.object_type == object_type)
    if object_id:
        query = query.where(AuditEvent.object_id == object_id)
    return list(session.scalars(query).all())


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    max_per_source: int = Query(default=2, ge=1, le=50),
    min_semantic_score: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    ),
    hybrid: bool = True,
    rerank: bool = False,
    source_ids: list[str] | None = Query(default=None, alias="source_id"),
    ingested_from: datetime | None = Query(default=None),
    ingested_before: datetime | None = Query(default=None),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> SearchResponse:
    try:
        source_ids, ingested_from, ingested_before = normalize_retrieval_filters(
            source_ids, ingested_from, ingested_before
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        embedding_provider = build_embedding_provider(get_settings()) if hybrid else None
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=409, detail="Embedding provider configuration is invalid"
        ) from exc
    try:
        hits = hybrid_search(
            session,
            q,
            embedding_provider,
            limit,
            max_per_source=max_per_source,
            min_semantic_score=min_semantic_score,
            source_ids=source_ids,
            ingested_from=ingested_from,
            ingested_before=ingested_before,
            reranker=DeterministicTokenReranker() if rerank else None,
            workspace_id=workspace_id,
        )
    except (ProviderRequestError, EmbeddingValidationError) as exc:
        raise HTTPException(status_code=502, detail="Embedding provider request failed") from exc
    return SearchResponse(query=q, hits=hits)


@router.post("/answers", response_model=AnswerResponse)
def create_answer(
    payload: AnswerRequest,
    response: Response,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> AnswerResponse:
    try:
        settings = get_settings()
        provider = build_generation_provider(settings)
        embedding_provider = build_embedding_provider(settings)
        answer = answer_question(
            session,
            payload.question,
            provider,
            embedding_provider,
            payload.limit,
            payload.max_per_source,
            payload.min_semantic_score,
            payload.source_ids,
            payload.ingested_from,
            payload.ingested_before,
            reranker=DeterministicTokenReranker() if payload.rerank else None,
            workspace_id=workspace_id,
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=409, detail="AI provider configuration is invalid") from exc
    except (
        ProviderRequestError,
        EmbeddingValidationError,
        StructuredOutputError,
        GroundingValidationError,
    ) as exc:
        run_id = getattr(exc, "run_id", None)
        headers = {"X-Proofline-Model-Run-ID": run_id} if run_id else None
        raise HTTPException(
            status_code=502,
            detail="model output could not produce a grounded answer",
            headers=headers,
        ) from exc
    except EvidenceIntegrityError as exc:
        raise HTTPException(status_code=500, detail="evidence integrity validation failed") from exc
    if answer.model_run_id:
        response.headers["X-Proofline-Model-Run-ID"] = answer.model_run_id
    return answer


@router.post(
    "/action-proposals", response_model=ActionProposalRead, status_code=status.HTTP_201_CREATED
)
def create_action_proposal(
    payload: ActionProposalCreate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> ActionProposal:
    try:
        settings = get_settings()
        answer = answer_question(
            session,
            payload.question,
            build_generation_provider(settings),
            build_embedding_provider(settings),
            payload.limit,
            payload.max_per_source,
            payload.min_semantic_score,
            payload.source_ids,
            payload.ingested_from,
            payload.ingested_before,
            reranker=DeterministicTokenReranker() if payload.rerank else None,
            workspace_id=workspace_id,
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=409, detail="AI provider configuration is invalid") from exc
    except (
        ProviderRequestError,
        EmbeddingValidationError,
        StructuredOutputError,
        GroundingValidationError,
    ) as exc:
        raise HTTPException(status_code=502, detail="grounded proposal generation failed") from exc
    except EvidenceIntegrityError as exc:
        raise HTTPException(status_code=500, detail="evidence integrity validation failed") from exc
    if answer.status != "grounded" or answer.model_run_id is None:
        raise HTTPException(
            status_code=422 if answer.status == "insufficient_evidence" else 409,
            detail=(
                "Insufficient evidence for an action proposal"
                if answer.status == "insufficient_evidence"
                else "A generation provider is required for action proposals"
            ),
        )
    proposal = ActionProposal(
        workspace_id=workspace_id,
        goal=payload.question,
        body=answer.answer,
        status="candidate",
        model_run_id=answer.model_run_id,
    )
    for citation in answer.citations:
        proposal.citations.append(
            ProposalCitation(
                source_id=citation.source_id,
                source_version_id=citation.source_version_id,
                chunk_id=citation.evidence_id,
                source_title=citation.source_title,
                quote=citation.content,
                quote_hash=hashlib.sha256(citation.content.encode("utf-8")).hexdigest(),
                start_offset=citation.start_offset,
                end_offset=citation.end_offset,
                start_line=citation.start_line,
                end_line=citation.end_line,
            )
        )
    session.add(proposal)
    session.flush()
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor="model",
            action="action_proposal.created",
            object_type="action_proposal",
            object_id=proposal.id,
            before_json={},
            after_json={"status": "candidate", "model_run_id": proposal.model_run_id},
        )
    )
    session.commit()
    session.refresh(proposal)
    return proposal


@router.get("/action-proposals", response_model=list[ActionProposalRead])
def list_action_proposals(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[ActionProposal]:
    return list(
        session.scalars(
            select(ActionProposal)
            .where(ActionProposal.workspace_id == workspace_id)
            .options(selectinload(ActionProposal.citations))
            .order_by(ActionProposal.created_at.desc())
        ).all()
    )


@router.patch("/action-proposals/{proposal_id}", response_model=ActionProposalRead)
def review_action_proposal(
    proposal_id: str,
    payload: ActionProposalReview,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> ActionProposal:
    proposal = session.scalar(
        select(ActionProposal)
        .where(ActionProposal.id == proposal_id, ActionProposal.workspace_id == workspace_id)
        .options(selectinload(ActionProposal.citations))
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Action proposal not found")
    if proposal.status != "candidate":
        raise HTTPException(status_code=409, detail="Action proposal was already reviewed")
    before = proposal.status
    proposal.status = payload.status
    proposal.updated_at = utc_now()
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor="local_user",
            action="action_proposal.reviewed",
            object_type="action_proposal",
            object_id=proposal.id,
            before_json={"status": before},
            after_json={"status": proposal.status},
        )
    )
    session.commit()
    session.refresh(proposal)
    return proposal


from .decision_impact_api import router as decision_impact_router  # noqa: E402
from .decision_relations_api import router as decision_relations_router  # noqa: E402
from .decision_review_api import router as decision_review_router  # noqa: E402
from .notes_api import router as notes_router  # noqa: E402
from .studio_api import router as studio_router  # noqa: E402

router.include_router(decision_review_router)
router.include_router(notes_router)
router.include_router(studio_router)
router.include_router(decision_relations_router)
router.include_router(decision_impact_router)
