from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .config import get_settings, load_provider_config, save_provider_config
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
    AuditEvent,
    Chunk,
    Decision,
    DecisionRelation,
    Evidence,
    GitRepository,
    IngestionJob,
    ModelRun,
    Source,
    SourceVersion,
    utc_now,
)
from .schemas import (
    AnswerRequest,
    AnswerResponse,
    AuditEventRead,
    DecisionRead,
    DecisionRelationCandidateRead,
    DecisionRelationCreate,
    DecisionRelationRead,
    DecisionTimelineRead,
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
    normalize_retrieval_filters,
)

router = APIRouter(prefix="/api/v1")


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


def decision_to_read(decision: Decision, source_title: str | None = None) -> DecisionRead:
    return DecisionRead.model_validate(decision).model_copy(
        update={"source_title": source_title, "evidence": decision.evidence}
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
    before = decision_snapshot(memory)
    for field, value in changes.items():
        setattr(memory, field, value)
    memory.updated_at = utc_now()
    after = decision_snapshot(memory)
    session.add(
        AuditEvent(
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
def overview(session: Session = Depends(get_session)) -> Overview:
    return Overview(
        sources=session.scalar(select(func.count()).select_from(Source)) or 0,
        chunks=session.scalar(
            select(func.count())
            .select_from(Chunk)
            .join(Source)
            .where(Chunk.source_version_id == Source.current_version_id)
        )
        or 0,
        decisions=session.scalar(
            select(func.count())
            .select_from(Decision)
            .join(Source)
            .where(
                Decision.source_version_id == Source.current_version_id,
                Decision.kind == "decision",
            )
        )
        or 0,
        memories=session.scalar(
            select(func.count())
            .select_from(Decision)
            .join(Source)
            .where(Decision.source_version_id == Source.current_version_id)
        )
        or 0,
        evidence=session.scalar(
            select(func.count())
            .select_from(Evidence)
            .join(Source)
            .where(Evidence.source_version_id == Source.current_version_id)
        )
        or 0,
    )


@router.post("/sources", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    response: Response,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
        pattern=r".*\S.*",
    ),
    session: Session = Depends(get_session),
) -> SourceRead:
    try:
        source, created, job = run_ingestion_job(session, payload, idempotency_key=idempotency_key)
    except IngestionIdempotencyConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"X-Proofline-Job-ID": exc.job_id},
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
    return source_to_read(hydrated)


@router.post("/folder-scans", response_model=FolderScanResponse)
def create_folder_scan(
    payload: FolderScanRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> FolderScanResponse:
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
    session: Session = Depends(get_session),
) -> GitRepositoryImportResponse:
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
def list_git_repositories(session: Session = Depends(get_session)) -> list[GitRepositoryRead]:
    repositories = session.scalars(
        select(GitRepository)
        .options(selectinload(GitRepository.sources))
        .order_by(GitRepository.indexed_at.desc())
    ).all()
    return [git_repository_to_read(repository) for repository in repositories]


@router.delete("/git-repositories/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_git_repository(repository_id: str, session: Session = Depends(get_session)) -> Response:
    repository = session.get(GitRepository, repository_id)
    if not repository:
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
def list_sources(session: Session = Depends(get_session)) -> list[SourceRead]:
    sources = session.scalars(
        select(Source)
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
    session: Session = Depends(get_session),
) -> list[IngestionJob]:
    query = select(IngestionJob).order_by(IngestionJob.updated_at.desc()).limit(limit)
    if job_state:
        query = query.where(IngestionJob.state == job_state)
    return list(session.scalars(query).all())


@router.get("/jobs/{job_id}", response_model=IngestionJobRead)
def get_job(job_id: str, session: Session = Depends(get_session)) -> IngestionJob:
    job = session.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


@router.post("/jobs/{job_id}/retry", response_model=IngestionJobRead)
def retry_job(job_id: str, session: Session = Depends(get_session)) -> IngestionJob:
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


@router.get("/model/reranking-provider", response_model=ProviderStatus)
def reranking_provider_status() -> ProviderStatus:
    return ProviderStatus(
        configured=False,
        reranking=False,
        mode="disabled",
        error_code="reranking_provider_disabled",
    )


@router.post("/model/embeddings/index", response_model=EmbeddingIndexResponse)
def index_embeddings(session: Session = Depends(get_session)) -> EmbeddingIndexResponse:
    try:
        provider = build_embedding_provider(get_settings())
        if provider is None:
            raise HTTPException(status_code=409, detail="Embedding provider is disabled")
        report = index_current_embeddings(session, provider)
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
    session: Session = Depends(get_session),
) -> list[ModelRun]:
    query = select(ModelRun)
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
    session: Session = Depends(get_session),
) -> ModelRunRetryResponse:
    parent = session.get(ModelRun, run_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Model run not found")
    if parent.status not in {"failed", "dead_letter"}:
        raise HTTPException(status_code=409, detail="Only failed model runs can be retried")
    source = session.get(Source, payload.source_id)
    if not source or not source.current_version_id:
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
def get_model_run(run_id: str, session: Session = Depends(get_session)) -> ModelRun:
    run = session.get(ModelRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Model run not found")
    return run


@router.get("/sources/{source_id}")
def get_source(source_id: str, session: Session = Depends(get_session)) -> dict:
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
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
    source_id: str, session: Session = Depends(get_session)
) -> SourceDeletionImpactRead:
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    impact = source_deletion_impact(session, source)
    return SourceDeletionImpactRead(
        source_id=source.id,
        title=source.title,
        current_version_id=source.current_version_id,
        **impact.__dict__,
    )


@router.get("/sources/{source_id}/versions", response_model=list[SourceVersionRead])
def list_source_versions(
    source_id: str, session: Session = Depends(get_session)
) -> list[SourceVersion]:
    if not session.get(Source, source_id):
        raise HTTPException(status_code=404, detail="Source not found")
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
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
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
    session: Session = Depends(get_session),
) -> list[MemoryRead]:
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
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
    source_id: str, version_id: str, session: Session = Depends(get_session)
) -> SourceVersion:
    version = session.scalar(
        select(SourceVersion).where(
            SourceVersion.id == version_id, SourceVersion.source_id == source_id
        )
    )
    if not version:
        raise HTTPException(status_code=404, detail="Source version not found")
    return version


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_source(source_id: str, session: Session = Depends(get_session)) -> Response:
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    delete_source(session, source)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/memories", response_model=list[MemoryRead])
def list_memories(
    memory_kind: MemoryKind | None = Query(default=None, alias="kind"),
    memory_status: str | None = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    query = (
        select(Decision, Source.title)
        .join(Source)
        .where(Decision.source_version_id == Source.current_version_id)
        .options(selectinload(Decision.evidence))
        .order_by(Decision.created_at.desc())
    )
    if memory_kind:
        query = query.where(Decision.kind == memory_kind)
    if memory_status:
        query = query.where(Decision.status == memory_status)
    return [decision_to_read(memory, title) for memory, title in session.execute(query).all()]


@router.get("/memories/{memory_id}", response_model=MemoryRead)
def get_memory(memory_id: str, session: Session = Depends(get_session)) -> DecisionRead:
    row = session.execute(
        select(Decision, Source.title)
        .join(Source)
        .where(Decision.id == memory_id)
        .options(selectinload(Decision.evidence))
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")
    return decision_to_read(row[0], row[1])


@router.patch("/memories/{memory_id}", response_model=MemoryRead)
def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    session: Session = Depends(get_session),
) -> DecisionRead:
    memory = session.scalar(
        select(Decision).where(Decision.id == memory_id).options(selectinload(Decision.evidence))
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
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    query = (
        select(Decision, Source.title)
        .join(Source)
        .where(
            Decision.source_version_id == Source.current_version_id,
            Decision.kind == "decision",
        )
        .options(selectinload(Decision.evidence))
        .order_by(Decision.created_at.desc())
    )
    if decision_status:
        query = query.where(Decision.status == decision_status)
    return [decision_to_read(decision, title) for decision, title in session.execute(query).all()]


@router.get("/decisions/{decision_id}", response_model=DecisionRead)
def get_decision(decision_id: str, session: Session = Depends(get_session)) -> DecisionRead:
    row = session.execute(
        select(Decision, Source.title)
        .join(Source)
        .where(Decision.id == decision_id, Decision.kind == "decision")
        .options(selectinload(Decision.evidence))
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision_to_read(row[0], row[1])


@router.patch("/decisions/{decision_id}", response_model=DecisionRead)
def update_decision(
    decision_id: str,
    payload: DecisionUpdate,
    session: Session = Depends(get_session),
) -> DecisionRead:
    decision = session.scalar(
        select(Decision)
        .where(Decision.id == decision_id, Decision.kind == "decision")
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


@router.post(
    "/decision-relations",
    response_model=DecisionRelationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_decision_relation(
    payload: DecisionRelationCreate,
    session: Session = Depends(get_session),
) -> DecisionRelation:
    decisions = {
        decision.id: decision
        for decision in session.scalars(
            select(Decision).where(
                Decision.id.in_([payload.source_decision_id, payload.target_decision_id]),
                Decision.kind == "decision",
            )
        ).all()
    }
    if len(decisions) != 2:
        raise HTTPException(status_code=404, detail="One or more decisions were not found")
    relation = DecisionRelation(**payload.model_dump(), created_by="local_user")
    session.add(relation)
    now = payload.valid_from or utc_now()
    if payload.kind == "supersedes":
        source = decisions[payload.source_decision_id]
        target = decisions[payload.target_decision_id]
        source_before = decision_snapshot(source)
        target_before = decision_snapshot(target)
        source.valid_from = source.valid_from or now
        target.valid_to = now
        target.status = "obsolete"
        session.add_all(
            [
                AuditEvent(
                    actor="local_user",
                    action="decision.supersedes",
                    object_type="decision",
                    object_id=source.id,
                    before_json=source_before,
                    after_json=decision_snapshot(source),
                ),
                AuditEvent(
                    actor="local_user",
                    action="decision.superseded",
                    object_type="decision",
                    object_id=target.id,
                    before_json=target_before,
                    after_json=decision_snapshot(target),
                ),
            ]
        )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Decision relation already exists") from exc
    session.refresh(relation)
    return relation


@router.get("/decision-relations", response_model=list[DecisionRelationRead])
def list_decision_relations(
    decision_id: str | None = None,
    relation_kind: str | None = Query(default=None, alias="kind"),
    session: Session = Depends(get_session),
) -> list[DecisionRelation]:
    query = select(DecisionRelation).order_by(DecisionRelation.created_at, DecisionRelation.id)
    if decision_id:
        query = query.where(
            (DecisionRelation.source_decision_id == decision_id)
            | (DecisionRelation.target_decision_id == decision_id)
        )
    if relation_kind:
        query = query.where(DecisionRelation.kind == relation_kind)
    return list(session.scalars(query).all())


@router.get("/decisions/{decision_id}/timeline", response_model=DecisionTimelineRead)
def get_decision_timeline(
    decision_id: str, session: Session = Depends(get_session)
) -> DecisionTimelineRead:
    decision = session.scalar(
        select(Decision)
        .where(Decision.id == decision_id, Decision.kind == "decision")
        .options(selectinload(Decision.evidence))
    )
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    incoming = list(
        session.scalars(
            select(DecisionRelation)
            .where(DecisionRelation.target_decision_id == decision_id)
            .order_by(DecisionRelation.created_at, DecisionRelation.id)
        ).all()
    )
    outgoing = list(
        session.scalars(
            select(DecisionRelation)
            .where(DecisionRelation.source_decision_id == decision_id)
            .order_by(DecisionRelation.created_at, DecisionRelation.id)
        ).all()
    )
    title = session.scalar(select(Source.title).where(Source.id == decision.source_id))
    return DecisionTimelineRead(
        decision=decision_to_read(decision, title), incoming=incoming, outgoing=outgoing
    )


@router.get("/decision-relation-candidates", response_model=list[DecisionRelationCandidateRead])
def list_decision_relation_candidates(
    session: Session = Depends(get_session),
) -> list[DecisionRelationCandidateRead]:
    candidates: list[DecisionRelationCandidateRead] = []
    relations = session.scalars(
        select(DecisionRelation).where(DecisionRelation.kind == "contradicts")
    ).all()
    for relation in relations:
        decisions = [
            session.get(Decision, relation.source_decision_id),
            session.get(Decision, relation.target_decision_id),
        ]
        if all(decision and decision.status != "obsolete" for decision in decisions):
            candidates.append(
                DecisionRelationCandidateRead(
                    kind="contradiction",
                    decision_ids=[relation.source_decision_id, relation.target_decision_id],
                    relation_id=relation.id,
                    reason="Both contradictory decisions are still non-obsolete; review required.",
                )
            )
    now = utc_now().replace(tzinfo=None)
    stale = session.scalars(
        select(Decision).where(
            Decision.kind == "decision",
            Decision.status.in_(["active", "accepted"]),
            Decision.valid_to.is_not(None),
            Decision.valid_to <= now,
        )
    ).all()
    candidates.extend(
        DecisionRelationCandidateRead(
            kind="stale",
            decision_ids=[decision.id],
            reason="Decision validity has ended but its review status is still current.",
        )
        for decision in stale
    )
    return candidates


@router.get("/audit-events", response_model=list[AuditEventRead])
def list_audit_events(
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[AuditEvent]:
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
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
    source_ids: list[str] | None = Query(default=None, alias="source_id"),
    ingested_from: datetime | None = Query(default=None),
    ingested_before: datetime | None = Query(default=None),
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
        )
    except (ProviderRequestError, EmbeddingValidationError) as exc:
        raise HTTPException(status_code=502, detail="Embedding provider request failed") from exc
    return SearchResponse(query=q, hits=hits)


@router.post("/answers", response_model=AnswerResponse)
def create_answer(
    payload: AnswerRequest,
    response: Response,
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
