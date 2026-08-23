from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .api import resolve_workspace_id
from .database import get_session
from .decision_impacts import DecisionImpactFinding, compute_decision_impacts
from .models import utc_now
from .schemas import DecisionImpactRead, DecisionImpactSummary

router = APIRouter()


def _as_of(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=422, detail={"code": "as_of_timezone_required"})
    return value.astimezone(UTC)


def _findings(
    session: Session,
    workspace_id: str,
    as_of: datetime | None,
) -> tuple[list[DecisionImpactFinding], datetime]:
    evaluated_at = _as_of(as_of)
    return (
        compute_decision_impacts(session, workspace_id=workspace_id, as_of=evaluated_at),
        evaluated_at,
    )


@router.get("/decision-impacts", response_model=list[DecisionImpactRead])
def list_decision_impacts(
    as_of: datetime | None = Query(default=None),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[DecisionImpactRead]:
    findings, _evaluated_at = _findings(session, workspace_id, as_of)
    return [DecisionImpactRead.model_validate(item.model_dump()) for item in findings]


@router.get("/decision-impacts/summary", response_model=DecisionImpactSummary)
def decision_impact_summary(
    as_of: datetime | None = Query(default=None),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> DecisionImpactSummary:
    findings, evaluated_at = _findings(session, workspace_id, as_of)
    return DecisionImpactSummary(
        root_review_count=len({item.root_review_id for item in findings}),
        impacted_decision_count=len({item.impacted_decision_id for item in findings}),
        finding_count=len(findings),
        max_depth=max((item.depth for item in findings), default=0),
        evaluated_at=evaluated_at,
    )
