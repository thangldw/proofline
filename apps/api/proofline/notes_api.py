from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .api import get_workspace_source, note_to_read, resolve_workspace_id
from .database import get_session
from .ingestion import (
    run_ingestion_job,
)
from .models import (
    Source,
    SourceVersion,
)
from .notes import parse_note_links
from .schemas import (
    NoteBacklinkRead,
    NoteCreate,
    NoteRead,
    NoteUpdate,
    SourceCreate,
)

router: APIRouter = APIRouter()


def _workspace_notes(session: Session, workspace_id: str) -> list[Source]:
    return list(
        session.scalars(
            select(Source)
            .where(Source.workspace_id == workspace_id, Source.kind == "note")
            .options(selectinload(Source.versions))
            .order_by(Source.indexed_at.desc())
        ).all()
    )


@router.post("/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> NoteRead:
    source, _, _ = run_ingestion_job(
        session,
        SourceCreate(
            title=payload.title,
            content=payload.content,
            kind="note",
            uri=f"note://{uuid.uuid4()}",
            workspace_id=workspace_id,
        ),
    )
    notes = _workspace_notes(session, workspace_id)
    hydrated = next(note for note in notes if note.id == source.id)
    return note_to_read(hydrated, notes)


@router.get("/notes", response_model=list[NoteRead])
def list_notes(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[NoteRead]:
    notes = _workspace_notes(session, workspace_id)
    return [note_to_read(note, notes) for note in notes]


@router.get("/notes/{note_id}", response_model=NoteRead)
def get_note(
    note_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> NoteRead:
    notes = _workspace_notes(session, workspace_id)
    note = next((item for item in notes if item.id == note_id), None)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note_to_read(note, notes)


@router.put("/notes/{note_id}", response_model=NoteRead)
def update_note(
    note_id: str,
    payload: NoteUpdate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> NoteRead:
    note = get_workspace_source(session, note_id, workspace_id)
    if note.kind != "note":
        raise HTTPException(status_code=404, detail="Note not found")
    current = session.get(SourceVersion, note.current_version_id)
    if current is not None and current.content == payload.content:
        if note.title != payload.title:
            note.title = payload.title
            session.commit()
        notes = _workspace_notes(session, workspace_id)
        hydrated = next(item for item in notes if item.id == note.id)
        return note_to_read(hydrated, notes)
    source, _, _ = run_ingestion_job(
        session,
        SourceCreate(
            title=payload.title,
            content=payload.content,
            kind="note",
            uri=note.uri,
            workspace_id=workspace_id,
        ),
    )
    notes = _workspace_notes(session, workspace_id)
    hydrated = next(item for item in notes if item.id == source.id)
    return note_to_read(hydrated, notes)


@router.get("/notes/{note_id}/backlinks", response_model=list[NoteBacklinkRead])
def list_note_backlinks(
    note_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[NoteBacklinkRead]:
    target = get_workspace_source(session, note_id, workspace_id)
    if target.kind != "note":
        raise HTTPException(status_code=404, detail="Note not found")
    notes = _workspace_notes(session, workspace_id)
    same_title = [note for note in notes if note.title.casefold() == target.title.casefold()]
    if len(same_title) != 1:
        return []
    backlinks: list[NoteBacklinkRead] = []
    for source in notes:
        for link in parse_note_links(source.content):
            if link.target_title.casefold() != target.title.casefold():
                continue
            backlinks.append(
                NoteBacklinkRead(
                    **link.model_copy(update={"resolved_source_id": target.id}).model_dump(),
                    source_id=source.id,
                    source_version_id=source.current_version_id or "",
                    source_title=source.title,
                )
            )
    return backlinks
