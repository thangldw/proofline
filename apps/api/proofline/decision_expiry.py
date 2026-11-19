from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Decision, Source, SourceVersion

_BY = r"(?:review[ _-]?by|xem xét lại trước)\s*[:\-]\s*(\d{4}-\d{2}-\d{2})"
_EVERY = r"(?:review[ _-]?every|xem xét lại mỗi)\s*[:\-]\s*(\d{1,3})\s*(day|week|month|year)s?"
REVIEW_LINE = re.compile(rf"^(?:{_BY}|{_EVERY})\s*$", re.I)
_REVIEW_LINES = re.compile(rf"^\s*(?:{_BY}|{_EVERY})\s*$", re.I | re.M)
MAX_INTERVAL_YEARS = 10


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


def add_months(start: date, months: int) -> date:
    index = start.year * 12 + start.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    last_day = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28]
    last_day += [31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(start.day, last_day[month - 1]))


def _add_interval(start: date, amount: int, unit: str) -> date | None:
    if unit == "day":
        return start + timedelta(days=amount)
    if unit == "week":
        return start + timedelta(weeks=amount)
    months = amount if unit == "month" else amount * 12
    if months > MAX_INTERVAL_YEARS * 12:
        return None
    return add_months(start, months)


def review_by_date(quote: str, *, approved_on: date | None = None) -> date | None:
    """Earliest review date in a cited quote.

    `Review by: YYYY-MM-DD` is absolute. `Review every: N days|weeks|months|years` counts from
    `approved_on` (the date the cited source version was recorded) and is ignored without it.
    """

    dates: list[date] = []
    for match in _REVIEW_LINES.finditer(quote):
        if match.group(1):
            try:
                dates.append(date.fromisoformat(match.group(1)))
            except ValueError:
                continue
        elif approved_on is not None:
            amount = int(match.group(2))
            due = _add_interval(approved_on, amount, match.group(3).lower()) if amount else None
            if due is not None:
                dates.append(due)
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
        dates = []
        for evidence in decision.evidence:
            if evidence.binding_state != "active":
                continue
            version = session.get(SourceVersion, evidence.source_version_id)
            approved_on = version.created_at.date() if version is not None else None
            found = review_by_date(evidence.quote, approved_on=approved_on)
            if found is not None:
                dates.append(found)
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
