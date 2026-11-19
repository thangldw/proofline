from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .anchors import EvidenceAnchor, resolve_evidence_anchor
from .models import Decision, Evidence, Source, SourceVersion

BLAME_STATUSES = ("active", "accepted")


class DecisionBlameError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class BlameEntry:
    decision_id: str
    decision_title: str
    decision_status: str
    evidence_id: str
    source_id: str
    state: str
    cited_start_line: int
    cited_end_line: int
    current_start_line: int | None
    current_end_line: int | None

    def model_dump(self) -> dict[str, str | int | None]:
        return asdict(self)

    def content_free_model_dump(self) -> dict[str, str | int | None]:
        document = self.model_dump()
        document.pop("decision_title")
        return document


def _find_sources(session: Session, target: str) -> list[Source]:
    suffix = "/" + target.replace("\\", "/").lstrip("/")
    return list(
        session.scalars(
            select(Source)
            .where(
                or_(
                    Source.uri == target,
                    Source.uri.endswith(suffix, autoescape=True),
                    Source.git_path == target,
                    Source.title == target,
                )
            )
            .order_by(Source.id)
        ).all()
    )


def blame(session: Session, target: str, line: int | None = None) -> list[BlameEntry]:
    """Return approved decisions anchored in `target`, optionally only those covering `line`.

    `line` is a 1-based line in the source's current version. Read-only and deterministic.
    """

    if not target.strip():
        raise DecisionBlameError("blame_target_invalid")
    if line is not None and line < 1:
        raise DecisionBlameError("blame_line_invalid")
    entries: list[BlameEntry] = []
    for source in _find_sources(session, target):
        if source.current_version_id is None:
            continue
        current = session.get(SourceVersion, source.current_version_id)
        if current is None:
            raise DecisionBlameError("current_source_version_missing")
        rows = session.execute(
            select(Decision, Evidence)
            .join(Evidence, Evidence.decision_id == Decision.id)
            .where(
                Decision.source_id == source.id,
                Decision.status.in_(BLAME_STATUSES),
                Evidence.binding_state == "active",
            )
            .order_by(Evidence.start_offset, Evidence.id)
        ).all()
        for decision, evidence in rows:
            entries.extend(_entries_for(session, source, current, decision, evidence, line))
    return entries


def _entries_for(
    session: Session,
    source: Source,
    current: SourceVersion,
    decision: Decision,
    evidence: Evidence,
    line: int | None,
) -> list[BlameEntry]:
    def make(state: str, start: int | None, end: int | None) -> BlameEntry:
        return BlameEntry(
            decision_id=decision.id,
            decision_title=decision.title,
            decision_status=decision.status,
            evidence_id=evidence.id,
            source_id=source.id,
            state=state,
            cited_start_line=evidence.start_line,
            cited_end_line=evidence.end_line,
            current_start_line=start,
            current_end_line=end,
        )

    if evidence.source_version_id == current.id:
        spans: list[tuple[int, int]] = [(evidence.start_line, evidence.end_line)]
        state = "unchanged"
    else:
        resolution = resolve_evidence_anchor(
            quote=evidence.quote,
            cited_anchor=EvidenceAnchor(
                version=evidence.anchor_version,
                section_path=tuple(evidence.section_path),
                prefix_sha256=evidence.prefix_sha256,
                suffix_sha256=evidence.suffix_sha256,
            ),
            current_content=current.content,
        )
        state = resolution.state
        spans = [(item.start_line, item.end_line) for item in resolution.candidates]
    if not spans:
        # Deleted: nothing to point at in the current text; match on the cited location.
        if line is None or evidence.start_line <= line <= evidence.end_line:
            return [make(state, None, None)]
        return []
    return [make(state, start, end) for start, end in spans if line is None or start <= line <= end]
