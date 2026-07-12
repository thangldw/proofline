from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import get_session
from .ingestion import (
    IngestionConflict,
    IngestionExecutionError,
    delete_source,
    run_ingestion_job,
)
from .model_gateway import ProviderConfigurationError, build_generation_provider
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
    AuditEventRead,
    DecisionRead,
    DecisionUpdate,
    IngestionJobRead,
    ModelRunRead,
    Overview,
    ProviderStatus,
    SearchHit,
    SearchResponse,
    SourceCreate,
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
            decision.source_version_id == source.current_version_id for decision in source.decisions
        ),
    )


def decision_to_read(decision: Decision, source_title: str | None = None) -> DecisionRead:
    return DecisionRead.model_validate(decision).model_copy(
        update={"source_title": source_title, "evidence": decision.evidence}
    )


def decision_snapshot(decision: Decision) -> dict[str, str | None]:
    return {
        "title": decision.title,
        "statement": decision.statement,
        "rationale": decision.rationale,
        "status": decision.status,
        "updated_at": decision.updated_at.isoformat(),
    }


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
    payload: SourceCreate, response: Response, session: Session = Depends(get_session)
) -> SourceRead:
    try:
        source, created, job = run_ingestion_job(session, payload)
    except IngestionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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


@router.get("/decisions", response_model=list[DecisionRead])
def list_decisions(
    decision_status: str | None = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    query = (
        select(Decision, Source.title)
        .join(Source)
        .where(Decision.source_version_id == Source.current_version_id)
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
        .where(Decision.id == decision_id)
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
        select(Decision).where(Decision.id == decision_id).options(selectinload(Decision.evidence))
    )
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="No decision changes supplied")
    before = decision_snapshot(decision)
    for field, value in changes.items():
        setattr(decision, field, value)
    decision.updated_at = utc_now()
    after = decision_snapshot(decision)
    session.add(
        AuditEvent(
            actor="local_user",
            action="decision.updated",
            object_type="decision",
            object_id=decision.id,
            before_json=before,
            after_json=after,
        )
    )
    session.commit()
    source_title = session.scalar(select(Source.title).where(Source.id == decision.source_id))
    session.refresh(decision)
    return decision_to_read(decision, source_title)


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
    session: Session = Depends(get_session),
) -> SearchResponse:
    terms = re.findall(r"[\w\-]+", q, flags=re.UNICODE)
    if not terms:
        return SearchResponse(query=q, hits=[])
    fts_query = " OR ".join(f'"{term}"' for term in terms)
    rows = session.execute(
        text(
            """
            SELECT c.id, c.source_id, c.source_version_id, s.title, c.content,
                   c.start_offset, c.end_offset, c.start_line, c.end_line,
                   bm25(chunk_search) AS rank
            FROM chunk_search
            JOIN chunks c ON c.id = chunk_search.chunk_id
            JOIN sources s ON s.id = c.source_id
            WHERE chunk_search MATCH :query
              AND c.source_version_id = s.current_version_id
            ORDER BY rank
            LIMIT :limit
            """
        ),
        {"query": fts_query, "limit": limit},
    ).all()
    hits = [
        SearchHit(
            chunk_id=row[0],
            source_id=row[1],
            source_version_id=row[2],
            source_title=row[3],
            content=row[4],
            start_offset=row[5],
            end_offset=row[6],
            start_line=row[7],
            end_line=row[8],
            rank=row[9],
        )
        for row in rows
    ]
    return SearchResponse(query=q, hits=hits)
