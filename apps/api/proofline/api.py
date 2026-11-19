from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import get_session
from .folder_scanning import FolderScanError
from .git_ingestion import GitIngestionError, import_git_repository
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
from .models import (
    DEFAULT_WORKSPACE_ID,
    AuditEvent,
    Chunk,
    Decision,
    Evidence,
    GitRepository,
    IngestionJob,
    Source,
    SourceVersion,
    Workspace,
    utc_now,
)
from .notes import parse_note_links, parse_note_tags
from .schemas import (
    AuditEventRead,
    DecisionRead,
    DecisionUpdate,
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
    NoteRead,
    Overview,
    SourceCreate,
    SourceDeletionImpactRead,
    SourceRead,
    SourceVersionContentRead,
    SourceVersionRead,
    WorkspaceCreate,
    WorkspaceRead,
)

router: APIRouter = APIRouter(prefix="/api/v1")


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


from .action_proposals_api import router as action_proposals_router  # noqa: E402
from .answers_api import router as answers_router  # noqa: E402
from .decision_impact_api import router as decision_impact_router  # noqa: E402
from .decision_relations_api import router as decision_relations_router  # noqa: E402
from .decision_review_api import router as decision_review_router  # noqa: E402
from .extraction_api import router as extraction_router  # noqa: E402
from .model_api import router as model_router  # noqa: E402
from .notes_api import router as notes_router  # noqa: E402
from .studio_api import router as studio_router  # noqa: E402

router.include_router(decision_review_router)
router.include_router(notes_router)
router.include_router(studio_router)
router.include_router(decision_relations_router)
router.include_router(decision_impact_router)
router.include_router(action_proposals_router)
router.include_router(answers_router)
router.include_router(extraction_router)
router.include_router(model_router)
