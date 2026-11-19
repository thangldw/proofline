from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .decision_policy import DecisionPolicyError, load_decision_policy
from .integrity import IntegrityVerificationError, verify_live_database
from .migrations import MIGRATIONS
from .models import DecisionHealthSnapshot, DecisionReview, utc_now

SNAPSHOT_STALE_DAYS = 14


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str  # ok | warn | fail
    detail: str

    def model_dump(self) -> dict[str, str]:
        return asdict(self)


def run_doctor(
    engine: Engine, session: Session, *, policy_path: Path | None = None
) -> list[DoctorCheck]:
    """Read-only health overview of a local Proofline workspace; never changes data."""

    checks: list[DoctorCheck] = []
    latest = MIGRATIONS[-1][0]
    try:
        with engine.connect() as connection:
            applied = connection.execute(
                text("SELECT max(version) FROM schema_migrations")
            ).scalar()
    except Exception:
        return [DoctorCheck("database", "fail", "database_or_migrations_unavailable")]
    if applied == latest:
        checks.append(DoctorCheck("migrations", "ok", f"at version {latest}"))
    else:
        checks.append(DoctorCheck("migrations", "fail", f"at {applied}, expected {latest}"))

    try:
        counts = verify_live_database(engine)
        checks.append(DoctorCheck("integrity", "ok", f"{counts['sources']} sources verified"))
    except IntegrityVerificationError as exc:
        checks.append(DoctorCheck("integrity", "fail", exc.code))

    max_age = 14
    if policy_path is not None:
        try:
            policy = load_decision_policy(policy_path)
            max_age = policy.max_open_age_days
            checks.append(DoctorCheck("policy", "ok", f"{len(policy.overrides)} overrides"))
        except DecisionPolicyError as exc:
            checks.append(DoctorCheck("policy", "fail", exc.code))

    cutoff = utc_now() - timedelta(days=max_age)
    overdue = (
        session.scalar(
            select(func.count(DecisionReview.id)).where(
                DecisionReview.state.in_(("open", "acknowledged")),
                DecisionReview.opened_at < cutoff,
            )
        )
        or 0
    )
    open_total = (
        session.scalar(
            select(func.count(DecisionReview.id)).where(
                DecisionReview.state.in_(("open", "acknowledged"))
            )
        )
        or 0
    )
    if overdue:
        checks.append(
            DoctorCheck(
                "reviews", "warn", f"{overdue} of {open_total} open for over {max_age} days"
            )
        )
    else:
        checks.append(
            DoctorCheck("reviews", "ok", f"{open_total} open, none older than {max_age} days")
        )

    last = session.scalar(select(func.max(DecisionHealthSnapshot.taken_at)))
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    if last is None:
        checks.append(DoctorCheck("snapshots", "warn", "none recorded; run snapshot-health"))
    elif utc_now() - last > timedelta(days=SNAPSHOT_STALE_DAYS):
        checks.append(
            DoctorCheck("snapshots", "warn", f"last one is older than {SNAPSHOT_STALE_DAYS} days")
        )
    else:
        checks.append(DoctorCheck("snapshots", "ok", f"latest {last.date().isoformat()}"))
    return checks
