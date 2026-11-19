from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .anchors import EvidenceAnchor, resolve_evidence_anchor
from .decision_why import _terms
from .models import AuditEvent, Decision, Evidence, Source, SourceVersion

APPROVED = ("active", "accepted")
RESTORE_ACTION = "source.version_restored"


class AsOfError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AsOfAnswer:
    decision_id: str
    decision_title: str
    status: str
    health: str
    source_id: str
    source_title: str
    cited_version_number: int
    version_in_force: int
    start_line: int
    end_line: int
    quote: str

    def model_dump(self) -> dict[str, object]:
        return asdict(self)

    def content_free_model_dump(self) -> dict[str, object]:
        document = self.model_dump()
        for key in ("decision_title", "source_title", "quote"):
            document.pop(key)
        return document


def parse_as_of(value: str) -> datetime:
    """A date means the end of that UTC day; a datetime is taken as UTC when it has no zone."""

    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return datetime.combine(date.fromisoformat(value), time.max)
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AsOfError("as_of_invalid") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def status_at(decision: Decision, events: list[AuditEvent], moment: datetime) -> str | None:
    """Status in force at `moment` from audited `decision.updated` events, else the oldest known.

    Changes made without an audit event (for example editing the database directly) are not
    visible here; the nearest recorded status is used instead.
    """

    updates = sorted(
        (
            (_naive(event.created_at), event)
            for event in events
            if event.action == "decision.updated"
            and isinstance(event.after_json, dict)
            and "status" in event.after_json
        ),
        key=lambda item: item[0],
    )
    before = [event for stamp, event in updates if stamp <= moment]
    if before:
        return str(before[-1].after_json["status"])
    if updates:
        recorded = updates[0][1].before_json
        return str(recorded.get("status")) if isinstance(recorded, dict) else None
    return decision.status


def _version_in_force(
    versions: list[SourceVersion], restores: list[AuditEvent], moment: datetime
) -> SourceVersion | None:
    by_id = {version.id: version for version in versions}
    timeline: list[tuple[datetime, SourceVersion]] = [
        (_naive(version.created_at), version) for version in versions
    ]
    for event in restores:
        target = by_id.get(str(event.after_json.get("version_id"))) if event.after_json else None
        if target is not None:
            timeline.append((_naive(event.created_at), target))
    eligible = [item for item in timeline if item[0] <= moment]
    return max(eligible, key=lambda item: item[0])[1] if eligible else None


def decisions_as_of(
    session: Session, moment: datetime, *, question: str | None = None
) -> list[AsOfAnswer]:
    terms = _terms(question) if question else []
    if question is not None and not terms:
        raise AsOfError("question_invalid")
    decisions = session.scalars(
        select(Decision)
        .options(selectinload(Decision.evidence))
        .where(Decision.kind == "decision")
        .order_by(Decision.id)
    ).all()
    audit = session.scalars(select(AuditEvent).order_by(AuditEvent.created_at)).all()
    updates: dict[str, list[AuditEvent]] = {}
    restores: dict[str, list[AuditEvent]] = {}
    for event in audit:
        if event.action == "decision.updated":
            updates.setdefault(event.object_id, []).append(event)
        elif event.action == RESTORE_ACTION:
            restores.setdefault(event.object_id, []).append(event)
    versions: dict[str, list[SourceVersion]] = {}
    for version in session.scalars(select(SourceVersion).order_by(SourceVersion.version_number)):
        versions.setdefault(version.source_id, []).append(version)
    sources = {item.id: item for item in session.scalars(select(Source))}
    answers: list[AsOfAnswer] = []
    for decision in decisions:
        if _naive(decision.created_at) > moment:
            continue
        status = status_at(decision, updates.get(decision.id, []), moment)
        if status not in APPROVED:
            continue
        haystack = f"{decision.title}\n{decision.statement}\n{decision.rationale or ''}".casefold()
        if terms and not any(term in haystack for term in terms):
            continue
        source_versions = versions.get(decision.source_id, [])
        in_force = _version_in_force(source_versions, restores.get(decision.source_id, []), moment)
        cited = next((v for v in source_versions if v.id == decision.source_version_id), None)
        source = sources.get(decision.source_id)
        if in_force is None or cited is None or source is None:
            continue
        evidence = _evidence_at(decision, versions, moment)
        if evidence is None:
            continue
        health = _health(evidence, cited, in_force)
        answers.append(
            AsOfAnswer(
                decision_id=decision.id,
                decision_title=decision.title,
                status=status,
                health=health,
                source_id=source.id,
                source_title=source.title,
                cited_version_number=cited.version_number,
                version_in_force=in_force.version_number,
                start_line=evidence.start_line,
                end_line=evidence.end_line,
                quote=evidence.quote,
            )
        )
    return answers


def _evidence_at(
    decision: Decision, versions: dict[str, list[SourceVersion]], moment: datetime
) -> Evidence | None:
    created = {v.id: _naive(v.created_at) for items in versions.values() for v in items}
    candidates = [
        item
        for item in decision.evidence
        if (item.superseded_at is None or _naive(item.superseded_at) > moment)
        and created.get(item.source_version_id, moment) <= moment
    ]
    return min(candidates, key=lambda item: (item.start_offset, item.id)) if candidates else None


def _health(evidence: Evidence, cited: SourceVersion, in_force: SourceVersion) -> str:
    if in_force.id == evidence.source_version_id:
        return "current"
    resolution = resolve_evidence_anchor(
        quote=evidence.quote,
        cited_anchor=EvidenceAnchor(
            version=evidence.anchor_version,
            section_path=tuple(evidence.section_path),
            prefix_sha256=evidence.prefix_sha256,
            suffix_sha256=evidence.suffix_sha256,
        ),
        current_content=in_force.content,
    )
    return "current" if resolution.state == "unchanged" else resolution.state
