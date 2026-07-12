from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import get_session
from .embeddings import hybrid_search, index_current_embeddings
from .extraction import (
    CandidateExtractionError,
    extract_decision_candidates,
    extract_memory_candidates,
)
from .folder_scanning import FolderScanError, scan_registered_folder
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
    Evidence,
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
    DecisionUpdate,
    EmbeddingIndexResponse,
    FolderScanRequest,
    FolderScanResponse,
    IngestionJobRead,
    MemoryKind,
    MemoryRead,
    MemoryUpdate,
    ModelRunRead,
    Overview,
    ProviderStatus,
    SearchResponse,
    SourceCreate,
    SourceDeletionImpactRead,
    SourceRead,
    SourceVersionContentRead,
    SourceVersionRead,
)

router = APIRouter(prefix="/api/v1")


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
    session: Session = Depends(get_session),
) -> FolderScanResponse:
    try:
        return scan_registered_folder(session, payload, get_settings().import_roots)
    except FolderScanError as exc:
        status_code = (
            status.HTTP_409_CONFLICT
            if exc.code in {"import_roots_disabled", "import_root_unavailable"}
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


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
        )
    if provider is None:
        return ProviderStatus(
            configured=False,
            remote_egress_allowed=settings.allow_remote_ai,
            error_code="provider_disabled",
        )
    capabilities = provider.capabilities()
    return ProviderStatus(
        configured=True,
        provider_id=provider.id,
        model_id=provider.model,
        generation=capabilities.generation,
        structured_output=capabilities.structured_output,
        remote_egress_allowed=settings.allow_remote_ai,
        healthy=provider.health() if check_health else None,
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
        )
    if provider is None:
        return ProviderStatus(
            configured=False,
            remote_egress_allowed=settings.allow_remote_ai,
            error_code="embedding_provider_disabled",
        )
    return ProviderStatus(
        configured=True,
        provider_id=provider.id,
        model_id=provider.model,
        generation=False,
        structured_output=False,
        remote_egress_allowed=settings.allow_remote_ai,
        healthy=provider.health() if check_health else None,
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
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[ModelRun]:
    query = select(ModelRun).order_by(ModelRun.created_at.desc()).limit(limit)
    if run_status:
        query = query.where(ModelRun.status == run_status)
    return list(session.scalars(query).all())


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
    hybrid: bool = True,
    session: Session = Depends(get_session),
) -> SearchResponse:
    try:
        embedding_provider = build_embedding_provider(get_settings()) if hybrid else None
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=409, detail="Embedding provider configuration is invalid"
        ) from exc
    try:
        hits = hybrid_search(session, q, embedding_provider, limit)
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
            session, payload.question, provider, embedding_provider, payload.limit
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
