from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .decision_health import check_decision_health
from .models import Decision, DecisionHealthSnapshot, Source, Workspace, utc_now

MAX_TREND_ROWS = 365


@dataclass(frozen=True)
class TrendPoint:
    taken_at: str
    approved: int
    findings: int
    moved: int
    changed: int
    ambiguous: int
    deleted: int

    @property
    def stale_percent(self) -> float:
        return round(100 * self.findings / self.approved, 1) if self.approved else 0.0

    def model_dump(self) -> dict[str, object]:
        return {**asdict(self), "stale_percent": self.stale_percent}


def record_snapshot(session: Session, workspace_id: str) -> DecisionHealthSnapshot:
    """Persist counts only (never titles or text) for the current health of one workspace."""

    findings = check_decision_health(session, workspace_id=workspace_id)
    approved = session.scalar(
        select(func.count(Decision.id))
        .join(Source, Source.id == Decision.source_id)
        .where(Source.workspace_id == workspace_id, Decision.status.in_(("active", "accepted")))
    )
    counts = {state: 0 for state in ("moved", "changed", "ambiguous", "deleted")}
    for finding in findings:
        if finding.reason in counts:
            counts[finding.reason] += 1
    snapshot = DecisionHealthSnapshot(
        workspace_id=workspace_id,
        taken_at=utc_now(),
        approved_count=approved or 0,
        finding_count=len(findings),
        moved_count=counts["moved"],
        changed_count=counts["changed"],
        ambiguous_count=counts["ambiguous"],
        deleted_count=counts["deleted"],
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def record_all_snapshots(session: Session) -> list[DecisionHealthSnapshot]:
    ids = session.scalars(select(Workspace.id).order_by(Workspace.id)).all()
    return [record_snapshot(session, workspace_id) for workspace_id in ids]


def trend(
    session: Session, *, workspace_id: str | None = None, limit: int = 30
) -> list[TrendPoint]:
    if not 1 <= limit <= MAX_TREND_ROWS:
        raise ValueError("trend_limit_invalid")
    statement = select(DecisionHealthSnapshot).order_by(
        DecisionHealthSnapshot.taken_at.desc(), DecisionHealthSnapshot.id.desc()
    )
    if workspace_id is not None:
        statement = statement.where(DecisionHealthSnapshot.workspace_id == workspace_id)
    rows = list(session.scalars(statement.limit(limit)).all())
    return [
        TrendPoint(
            taken_at=row.taken_at.isoformat(),
            approved=row.approved_count,
            findings=row.finding_count,
            moved=row.moved_count,
            changed=row.changed_count,
            ambiguous=row.ambiguous_count,
            deleted=row.deleted_count,
        )
        for row in reversed(rows)
    ]


def render_markdown(points: list[TrendPoint]) -> str:
    lines = [
        "| Taken at | Approved | Stale | Stale % | Moved | Changed | Ambiguous | Deleted |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {p.taken_at} | {p.approved} | {p.findings} | {p.stale_percent} | {p.moved} | "
        f"{p.changed} | {p.ambiguous} | {p.deleted} |"
        for p in points
    )
    return "\n".join(lines) + "\n"
