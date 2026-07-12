from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from .database import get_session
from .ingestion import (
    IngestionConflict,
    IngestionExecutionError,
    delete_source,
    run_ingestion_job,
)
from .models import Chunk, Decision, Evidence, IngestionJob, Source, SourceVersion
from .schemas import (
    DecisionRead,
    IngestionJobRead,
    Overview,
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
