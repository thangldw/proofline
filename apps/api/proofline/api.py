from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from .database import get_session
from .ingestion import delete_source, ingest_source
from .models import Chunk, Decision, Evidence, Source
from .schemas import DecisionRead, Overview, SearchHit, SearchResponse, SourceCreate, SourceRead

router = APIRouter(prefix="/api/v1")


def source_to_read(source: Source) -> SourceRead:
    return SourceRead(
        **{column.name: getattr(source, column.name) for column in Source.__table__.columns},
        chunk_count=len(source.chunks),
        decision_count=len(source.decisions),
    )


def decision_to_read(decision: Decision, source_title: str | None = None) -> DecisionRead:
    return DecisionRead.model_validate(decision).model_copy(
        update={"source_title": source_title, "evidence": decision.evidence}
    )


@router.get("/overview", response_model=Overview)
def overview(session: Session = Depends(get_session)) -> Overview:
    def count(model) -> int:
        return session.scalar(select(func.count()).select_from(model)) or 0

    return Overview(
        sources=count(Source),
        chunks=count(Chunk),
        decisions=count(Decision),
        evidence=count(Evidence),
    )


@router.post("/sources", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate, response: Response, session: Session = Depends(get_session)
) -> SourceRead:
    source, created = ingest_source(session, payload)
    if not created:
        response.status_code = status.HTTP_200_OK
    hydrated = session.scalar(
        select(Source)
        .where(Source.id == source.id)
        .options(selectinload(Source.chunks), selectinload(Source.decisions))
    )
    return source_to_read(hydrated)


@router.get("/sources", response_model=list[SourceRead])
def list_sources(session: Session = Depends(get_session)) -> list[SourceRead]:
    sources = session.scalars(
        select(Source)
        .options(selectinload(Source.chunks), selectinload(Source.decisions))
        .order_by(Source.indexed_at.desc())
    ).all()
    return [source_to_read(source) for source in sources]


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
    }


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
            SELECT c.id, c.source_id, s.title, c.content, c.start_offset, c.end_offset,
                   c.start_line, c.end_line, bm25(chunk_search) AS rank
            FROM chunk_search
            JOIN chunks c ON c.id = chunk_search.chunk_id
            JOIN sources s ON s.id = c.source_id
            WHERE chunk_search MATCH :query
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
            source_title=row[2],
            content=row[3],
            start_offset=row[4],
            end_offset=row[5],
            start_line=row[6],
            end_line=row[7],
            rank=row[8],
        )
        for row in rows
    ]
    return SearchResponse(query=q, hits=hits)
