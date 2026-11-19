from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Decision, Source

REVIEW_BY = re.compile(
    r"^\s*(?:review[ _-]?by|xem xét lại trước)\s*[:\-]\s*(\d{4}-\d{2}-\d{2})\s*$",
    re.I | re.M,
)


@dataclass(frozen=True)
class ExpiryFinding:
    decision_id: str
    decision_title: str
    review_by: str
    days_overdue: int
    state: str

    def model_dump(self) -> dict[str, str | int]:
        return asdict(self)

    def content_free_model_dump(self) -> dict[str, str | int]:
        document = self.model_dump()
        document.pop("decision_title")
        return document


def review_by_date(quote: str) -> date | None:
    """Return the earliest valid `Review by: YYYY-MM-DD` date in a cited quote."""

    dates: list[date] = []
    for match in REVIEW_BY.finditer(quote):
        try:
            dates.append(date.fromisoformat(match.group(1)))
        except ValueError:
            continue
    return min(dates) if dates else None


def check_expiry(
    session: Session,
    *,
    as_of: date,
    warn_within_days: int = 0,
    workspace_id: str | None = None,
) -> list[ExpiryFinding]:
    """Approved decisions whose declared review date has passed (or is near).

    The date is read from the decision's cited evidence, so changing it is a reviewed edit.
    """

    if warn_within_days < 0:
        raise ValueError("warn_within_days_invalid")
    statement = (
        select(Decision)
        .options(selectinload(Decision.evidence))
        .where(Decision.status.in_(("active", "accepted")))
        .order_by(Decision.id)
    )
    if workspace_id is not None:
        statement = statement.join(Source, Source.id == Decision.source_id).where(
            Source.workspace_id == workspace_id
        )
    findings: list[ExpiryFinding] = []
    for decision in session.scalars(statement).all():
        dates = [
            found
            for evidence in decision.evidence
            if evidence.binding_state == "active"
            if (found := review_by_date(evidence.quote)) is not None
        ]
        if not dates:
            continue
        due = min(dates)
        overdue = (as_of - due).days
        if overdue > 0:
            state = "overdue"
        elif -overdue <= warn_within_days:
            state = "due_soon"
        else:
            continue
        findings.append(
            ExpiryFinding(
                decision_id=decision.id,
                decision_title=decision.title,
                review_by=due.isoformat(),
                days_overdue=overdue,
                state=state,
            )
        )
    return sorted(findings, key=lambda item: (item.review_by, item.decision_id))
