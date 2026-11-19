from __future__ import annotations

from datetime import timedelta
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .api import get_workspace_source, resolve_workspace_id
from .database import get_session
from .learning import extract_study_pairs, next_interval
from .models import (
    Source,
    SourceVersion,
    StudioArtifact,
    StudioCitation,
    StudyCard,
    StudyReview,
    utc_now,
)
from .schemas import (
    StudioArtifactCreate,
    StudioArtifactRead,
    StudioCitationRead,
    StudyCardRead,
    StudyReviewCreate,
    StudyReviewRead,
)
from .studio import StudioKind, build_studio_draft
from .studio_exports import StudioExportError, build_studio_export

router = APIRouter()


def study_card_to_read(card: StudyCard, source_title: str | None = None) -> StudyCardRead:
    return StudyCardRead.model_validate(card).model_copy(update={"source_title": source_title})


def studio_artifact_to_read(artifact: StudioArtifact, source_title: str) -> StudioArtifactRead:
    return StudioArtifactRead(
        id=artifact.id,
        workspace_id=artifact.workspace_id,
        source_id=artifact.source_id,
        source_version_id=artifact.source_version_id,
        source_title=source_title,
        kind=cast(StudioKind, artifact.kind),
        title=artifact.title,
        content=artifact.content_json,
        status=cast(Literal["ready"], artifact.status),
        generation_method=artifact.generation_method,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
        citations=[
            StudioCitationRead(
                id=citation.id,
                source_id=citation.source_id,
                source_version_id=citation.source_version_id,
                source_title=source_title,
                ordinal=citation.ordinal,
                quote=citation.quote,
                quote_hash=citation.quote_hash,
                start_offset=citation.start_offset,
                end_offset=citation.end_offset,
                start_line=citation.start_line,
                end_line=citation.end_line,
            )
            for citation in sorted(artifact.citations, key=lambda item: item.ordinal)
        ],
    )


@router.post(
    "/studio-artifacts",
    response_model=StudioArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
def create_studio_artifact(
    payload: StudioArtifactCreate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> StudioArtifactRead:
    source = get_workspace_source(session, payload.source_id, workspace_id)
    version = session.get(SourceVersion, source.current_version_id)
    if version is None:
        raise HTTPException(status_code=409, detail="Source has no current immutable version")
    try:
        draft = build_studio_draft(payload.kind, source.title, version.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    artifact = session.scalar(
        select(StudioArtifact)
        .where(
            StudioArtifact.source_version_id == version.id,
            StudioArtifact.kind == payload.kind,
        )
        .options(selectinload(StudioArtifact.citations))
    )
    if artifact is None:
        artifact = StudioArtifact(
            workspace_id=workspace_id,
            source_id=source.id,
            source_version_id=version.id,
            kind=payload.kind,
            title=draft.title,
            content_json=draft.content,
            status="ready",
            generation_method="deterministic-v1",
        )
        session.add(artifact)
    else:
        return studio_artifact_to_read(artifact, source.title)
    for ordinal, citation in enumerate(draft.citations):
        artifact.citations.append(
            StudioCitation(
                source_id=source.id,
                source_version_id=version.id,
                ordinal=ordinal,
                quote=citation.text,
                quote_hash=citation.quote_hash,
                start_offset=citation.start_offset,
                end_offset=citation.end_offset,
                start_line=citation.start_line,
                end_line=citation.end_line,
            )
        )
    session.commit()
    session.refresh(artifact)
    return studio_artifact_to_read(artifact, source.title)


@router.get("/studio-artifacts", response_model=list[StudioArtifactRead])
def list_studio_artifacts(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[StudioArtifactRead]:
    rows = session.execute(
        select(StudioArtifact, Source.title)
        .join(Source, Source.id == StudioArtifact.source_id)
        .where(StudioArtifact.workspace_id == workspace_id)
        .options(selectinload(StudioArtifact.citations))
        .order_by(StudioArtifact.updated_at.desc(), StudioArtifact.id)
    ).all()
    return [studio_artifact_to_read(artifact, title) for artifact, title in rows]


@router.get("/studio-artifacts/{artifact_id}", response_model=StudioArtifactRead)
def get_studio_artifact(
    artifact_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> StudioArtifactRead:
    row = session.execute(
        select(StudioArtifact, Source.title)
        .join(Source, Source.id == StudioArtifact.source_id)
        .where(
            StudioArtifact.id == artifact_id,
            StudioArtifact.workspace_id == workspace_id,
        )
        .options(selectinload(StudioArtifact.citations))
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Studio artifact not found")
    return studio_artifact_to_read(*row)


@router.get("/studio-artifacts/{artifact_id}/download")
def download_studio_artifact(
    artifact_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> Response:
    row = session.execute(
        select(StudioArtifact, Source.title, SourceVersion)
        .join(Source, Source.id == StudioArtifact.source_id)
        .join(SourceVersion, SourceVersion.id == StudioArtifact.source_version_id)
        .where(
            StudioArtifact.id == artifact_id,
            StudioArtifact.workspace_id == workspace_id,
        )
        .options(selectinload(StudioArtifact.citations))
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Studio artifact not found")
    artifact, source_title, version = row
    try:
        exported = build_studio_export(artifact, version, source_title)
    except StudioExportError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
    )


@router.delete("/studio-artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_studio_artifact(
    artifact_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> Response:
    artifact = session.scalar(
        select(StudioArtifact).where(
            StudioArtifact.id == artifact_id,
            StudioArtifact.workspace_id == workspace_id,
        )
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Studio artifact not found")
    session.delete(artifact)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sources/{source_id}/study-cards", response_model=list[StudyCardRead])
def create_study_cards(
    source_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[StudyCardRead]:
    source = get_workspace_source(session, source_id, workspace_id)
    version = session.get(SourceVersion, source.current_version_id)
    if version is None:
        raise HTTPException(status_code=409, detail="Source has no current immutable version")
    pairs = extract_study_pairs(version.content)
    if not pairs:
        raise HTTPException(
            status_code=422,
            detail="No deterministic study pairs found; use adjacent Q: and A: lines",
        )
    session.query(StudyCard).filter(
        StudyCard.source_id == source.id,
        StudyCard.source_version_id != version.id,
        StudyCard.state != "superseded",
    ).update({"state": "superseded", "updated_at": utc_now()})
    existing = {
        (card.start_offset, card.end_offset): card
        for card in session.scalars(
            select(StudyCard).where(StudyCard.source_version_id == version.id)
        ).all()
    }
    cards: list[StudyCard] = []
    for pair in pairs:
        card = existing.get((pair.start_offset, pair.end_offset))
        if card is None:
            card = StudyCard(
                workspace_id=workspace_id,
                source_id=source.id,
                source_version_id=version.id,
                question=pair.question,
                answer=pair.answer,
                quote_hash=pair.quote_hash,
                start_offset=pair.start_offset,
                end_offset=pair.end_offset,
                start_line=pair.start_line,
                end_line=pair.end_line,
                state="new",
                interval_days=0,
                due_at=utc_now(),
            )
            session.add(card)
        cards.append(card)
    session.commit()
    for card in cards:
        session.refresh(card)
    return [study_card_to_read(card, source.title) for card in cards]


@router.get("/study-cards", response_model=list[StudyCardRead])
def list_study_cards(
    include_superseded: bool = False,
    due_only: bool = False,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[StudyCardRead]:
    query = (
        select(StudyCard, Source.title)
        .join(Source, Source.id == StudyCard.source_id)
        .where(StudyCard.workspace_id == workspace_id)
        .order_by(StudyCard.due_at, StudyCard.created_at)
    )
    if not include_superseded:
        query = query.where(StudyCard.state != "superseded")
    if due_only:
        query = query.where(StudyCard.due_at <= utc_now())
    return [study_card_to_read(card, title) for card, title in session.execute(query).all()]


@router.get("/study-cards/{card_id}/reviews", response_model=list[StudyReviewRead])
def list_study_reviews(
    card_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[StudyReview]:
    card = session.get(StudyCard, card_id)
    if card is None or card.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Study card not found")
    return list(
        session.scalars(
            select(StudyReview)
            .where(StudyReview.card_id == card_id)
            .order_by(StudyReview.reviewed_at, StudyReview.id)
        ).all()
    )


@router.post("/study-cards/{card_id}/reviews", response_model=StudyReviewRead)
def review_study_card(
    card_id: str,
    payload: StudyReviewCreate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> StudyReview:
    card = session.get(StudyCard, card_id)
    if card is None or card.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Study card not found")
    if card.state == "superseded":
        raise HTTPException(status_code=409, detail="Superseded study card cannot be reviewed")
    reviewed_at = utc_now()
    interval = next_interval(payload.rating, card.interval_days)
    review = StudyReview(
        card_id=card.id,
        rating=payload.rating,
        previous_interval_days=card.interval_days,
        next_interval_days=interval,
        reviewed_at=reviewed_at,
    )
    card.interval_days = interval
    card.state = "learning" if payload.rating == "again" else "review"
    card.due_at = reviewed_at + timedelta(days=interval)
    card.updated_at = reviewed_at
    session.add(review)
    session.commit()
    session.refresh(review)
    return review
