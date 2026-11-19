from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .api import decision_snapshot, decision_to_read, resolve_workspace_id
from .database import get_session
from .models import (
    AuditEvent,
    Decision,
    DecisionRelation,
    Source,
    utc_now,
)
from .schemas import (
    DecisionRelationCandidateRead,
    DecisionRelationCreate,
    DecisionRelationRead,
    DecisionTimelineRead,
)

router: APIRouter = APIRouter()


@router.post(
    "/decision-relations",
    response_model=DecisionRelationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_decision_relation(
    payload: DecisionRelationCreate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionRelation:
    decisions = {
        decision.id: decision
        for decision in session.scalars(
            select(Decision)
            .join(Source)
            .where(
                Decision.id.in_([payload.source_decision_id, payload.target_decision_id]),
                Decision.kind == "decision",
                Source.workspace_id == workspace_id,
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
                    workspace_id=workspace_id,
                    actor="local_user",
                    action="decision.supersedes",
                    object_type="decision",
                    object_id=source.id,
                    before_json=source_before,
                    after_json=decision_snapshot(source),
                ),
                AuditEvent(
                    workspace_id=workspace_id,
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
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[DecisionRelation]:
    workspace_decisions = (
        select(Decision.id).join(Source).where(Source.workspace_id == workspace_id)
    )
    query = (
        select(DecisionRelation)
        .where(
            DecisionRelation.source_decision_id.in_(workspace_decisions),
            DecisionRelation.target_decision_id.in_(workspace_decisions),
        )
        .order_by(DecisionRelation.created_at, DecisionRelation.id)
    )
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
    decision_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionTimelineRead:
    decision = session.scalar(
        select(Decision)
        .join(Source)
        .where(Decision.id == decision_id, Decision.kind == "decision")
        .where(Source.workspace_id == workspace_id)
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
        decision=decision_to_read(decision, title),
        incoming=[DecisionRelationRead.model_validate(item) for item in incoming],
        outgoing=[DecisionRelationRead.model_validate(item) for item in outgoing],
    )


@router.get("/decision-relation-candidates", response_model=list[DecisionRelationCandidateRead])
def list_decision_relation_candidates(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[DecisionRelationCandidateRead]:
    candidates: list[DecisionRelationCandidateRead] = []
    workspace_decisions = (
        select(Decision.id).join(Source).where(Source.workspace_id == workspace_id)
    )
    relations = session.scalars(
        select(DecisionRelation).where(
            DecisionRelation.kind == "contradicts",
            DecisionRelation.source_decision_id.in_(workspace_decisions),
            DecisionRelation.target_decision_id.in_(workspace_decisions),
        )
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
        select(Decision)
        .join(Source)
        .where(
            Decision.kind == "decision",
            Source.workspace_id == workspace_id,
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
