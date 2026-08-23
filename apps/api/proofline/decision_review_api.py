from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .api import resolve_workspace_id
from .database import get_session
from .decision_policy import DecisionHealthPolicy
from .decision_reviews import (
    ACTIVE_REVIEW_STATES,
    DecisionReviewError,
    apply_review_action,
    reanchor_review,
    refresh_decision_reviews,
    resolve_review,
)
from .models import AuditEvent, Decision, DecisionReview, Evidence, Source, SourceVersion, utc_now
from .schemas import (
    DecisionReviewAction,
    DecisionReviewListItem,
    DecisionReviewOverview,
    DecisionReviewRead,
    DecisionReviewReanchor,
    DecisionReviewResolve,
)

router = APIRouter()

ReviewState = Literal["open", "acknowledged", "resolved", "waived", "superseded"]
AnchorState = Literal["moved", "ambiguous", "changed", "deleted"]
Severity = Literal["warning", "error"]


def _raise_review_error(error: DecisionReviewError) -> None:
    code = error.code
    if code in {"review_not_found", "replacement_decision_not_found"}:
        status_code = 404
    elif code in {"review_state_conflict", "source_version_conflict"}:
        status_code = 409
    elif code in {
        "decision_reanchor_multiple_evidence_unsupported",
        "reanchor_span_invalid",
        "replacement_decision_invalid",
        "review_action_invalid",
        "review_actor_invalid",
        "review_reason_required",
        "review_reason_too_long",
        "review_waiver_disabled",
    }:
        status_code = 422
    else:
        status_code = 500
    raise HTTPException(status_code=status_code, detail={"code": code}) from error


def _get_workspace_review(
    session: Session,
    review_id: str,
    workspace_id: str,
) -> DecisionReview:
    review = session.scalar(
        select(DecisionReview).where(
            DecisionReview.id == review_id,
            DecisionReview.workspace_id == workspace_id,
        )
    )
    if review is None:
        raise HTTPException(status_code=404, detail={"code": "review_not_found"})
    return review


@router.get("/decision-health/overview", response_model=DecisionReviewOverview)
def decision_health_overview(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionReviewOverview:
    accepted = (
        session.scalar(
            select(func.count())
            .select_from(Decision)
            .join(Source, Source.id == Decision.source_id)
            .where(Source.workspace_id == workspace_id, Decision.status == "accepted")
        )
        or 0
    )
    review_required = (
        session.scalar(
            select(func.count(func.distinct(DecisionReview.decision_id)))
            .select_from(DecisionReview)
            .join(Decision, Decision.id == DecisionReview.decision_id)
            .where(
                DecisionReview.workspace_id == workspace_id,
                DecisionReview.state.in_(ACTIVE_REVIEW_STATES),
                Decision.status == "accepted",
            )
        )
        or 0
    )
    policy = DecisionHealthPolicy()
    overdue_before = utc_now() - timedelta(days=policy.max_open_age_days)
    overdue = (
        session.scalar(
            select(func.count())
            .select_from(DecisionReview)
            .where(
                DecisionReview.workspace_id == workspace_id,
                DecisionReview.state.in_(ACTIVE_REVIEW_STATES),
                DecisionReview.opened_at < overdue_before,
            )
        )
        or 0
    )
    waived = (
        session.scalar(
            select(func.count())
            .select_from(DecisionReview)
            .where(
                DecisionReview.workspace_id == workspace_id,
                DecisionReview.state == "waived",
            )
        )
        or 0
    )
    return DecisionReviewOverview(
        healthy_accepted=max(0, accepted - review_required),
        review_required=review_required,
        overdue=overdue,
        waived=waived,
    )


@router.get("/decision-reviews", response_model=list[DecisionReviewListItem])
def list_decision_reviews(
    state: ReviewState | None = None,
    anchor_state: AnchorState | None = None,
    severity: Severity | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[DecisionReviewListItem]:
    statement = (
        select(DecisionReview, Decision.status)
        .join(Decision, Decision.id == DecisionReview.decision_id)
        .where(DecisionReview.workspace_id == workspace_id)
    )
    if state is not None:
        statement = statement.where(DecisionReview.state == state)
    if anchor_state is not None:
        statement = statement.where(DecisionReview.anchor_state == anchor_state)
    if severity is not None:
        statement = statement.where(DecisionReview.severity == severity)
    statement = statement.order_by(
        case((DecisionReview.severity == "error", 0), else_=1),
        DecisionReview.opened_at,
        DecisionReview.id,
    ).limit(limit)
    return [
        DecisionReviewListItem.model_validate(
            {
                **DecisionReviewRead.model_validate(review).model_dump(),
                "decision_status": decision_status,
            }
        )
        for review, decision_status in session.execute(statement).all()
    ]


@router.post("/decision-reviews/refresh")
def refresh_reviews(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    try:
        summary = refresh_decision_reviews(session, workspace_id=workspace_id)
        session.commit()
    except DecisionReviewError as error:
        session.rollback()
        _raise_review_error(error)
    return summary.model_dump()


@router.get("/decision-reviews/{review_id}")
def get_decision_review(
    review_id: str,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> dict:
    review = _get_workspace_review(session, review_id, workspace_id)
    decision = session.get(Decision, review.decision_id)
    evidence = session.get(Evidence, review.evidence_id)
    cited = session.get(SourceVersion, review.cited_source_version_id)
    current = session.get(SourceVersion, review.current_source_version_id)
    if (
        decision is None
        or evidence is None
        or cited is None
        or current is None
        or cited.source_id != decision.source_id
        or current.source_id != decision.source_id
        or evidence.decision_id != decision.id
        or evidence.source_version_id != cited.id
        or hashlib.sha256(cited.content.encode()).hexdigest() != cited.content_hash
        or hashlib.sha256(current.content.encode()).hexdigest() != current.content_hash
        or cited.content[evidence.start_offset : evidence.end_offset] != evidence.quote
    ):
        raise HTTPException(status_code=500, detail={"code": "review_provenance_invalid"})
    candidate = None
    if review.candidate_start_offset is not None and review.candidate_end_offset is not None:
        if not (
            0 <= review.candidate_start_offset < review.candidate_end_offset <= len(current.content)
        ):
            raise HTTPException(status_code=500, detail={"code": "review_provenance_invalid"})
        candidate = {
            "start_offset": review.candidate_start_offset,
            "end_offset": review.candidate_end_offset,
            "start_line": review.candidate_start_line,
            "end_line": review.candidate_end_line,
            "quote": current.content[review.candidate_start_offset : review.candidate_end_offset],
        }
    events = session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.workspace_id == workspace_id,
            AuditEvent.object_type == "decision_review",
            AuditEvent.object_id == review.id,
        )
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    policy = DecisionHealthPolicy()
    return {
        "review": {
            **DecisionReviewRead.model_validate(review).model_dump(),
            "decision_status": decision.status,
        },
        "decision": {
            "id": decision.id,
            "title": decision.title,
            "statement": decision.statement,
            "status": decision.status,
        },
        "cited": {
            "source_version_id": cited.id,
            "content_sha256": cited.content_hash,
            "start_offset": evidence.start_offset,
            "end_offset": evidence.end_offset,
            "start_line": evidence.start_line,
            "end_line": evidence.end_line,
            "quote": evidence.quote,
        },
        "current": {
            "source_version_id": current.id,
            "content_sha256": current.content_hash,
            "candidate": candidate,
        },
        "policy": {
            "blocking": review.anchor_state in policy.fail_on,
            "hash": review.policy_hash,
        },
        "audit_events": [
            {
                "id": event.id,
                "actor": event.actor,
                "action": event.action,
                "before": event.before_json,
                "after": event.after_json,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


@router.patch("/decision-reviews/{review_id}", response_model=DecisionReviewRead)
def update_decision_review(
    review_id: str,
    payload: DecisionReviewAction,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionReview:
    try:
        review = apply_review_action(
            session,
            review_id,
            workspace_id=workspace_id,
            action=payload.action,
            actor="local_user",
            reason=payload.reason,
        )
        session.commit()
        session.refresh(review)
    except DecisionReviewError as error:
        session.rollback()
        _raise_review_error(error)
    return review


@router.post("/decision-reviews/{review_id}/reanchor", response_model=DecisionReviewRead)
def reanchor_decision_review(
    review_id: str,
    payload: DecisionReviewReanchor,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionReview:
    try:
        review = reanchor_review(
            session,
            review_id,
            workspace_id=workspace_id,
            actor="local_user",
            **payload.model_dump(),
        )
        session.commit()
        session.refresh(review)
    except DecisionReviewError as error:
        session.rollback()
        _raise_review_error(error)
    return review


@router.post("/decision-reviews/{review_id}/resolve", response_model=DecisionReviewRead)
def resolve_decision_review(
    review_id: str,
    payload: DecisionReviewResolve,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionReview:
    try:
        review = resolve_review(
            session,
            review_id,
            workspace_id=workspace_id,
            actor="local_user",
            **payload.model_dump(),
        )
        session.commit()
        session.refresh(review)
    except (DecisionReviewError, IntegrityError) as error:
        session.rollback()
        if isinstance(error, DecisionReviewError):
            _raise_review_error(error)
        _raise_review_error(DecisionReviewError("review_state_conflict"))
    return review
