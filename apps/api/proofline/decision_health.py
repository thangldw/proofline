from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Decision, Source, SourceVersion


class DecisionHealthError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DecisionHealthFinding:
    decision_id: str
    decision_title: str
    source_id: str
    source_uri: str | None
    source_title: str
    cited_source_version_id: str
    current_source_version_id: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    quote_sha256: str
    cited_content_sha256: str
    current_content_sha256: str
    reason: str = "citation_changed"

    def model_dump(self) -> dict[str, str | int | None]:
        return asdict(self)

    @property
    def locator(self) -> str:
        return f"{self.source_title}:{self.start_line}-{self.end_line}"


def check_decision_health(session: Session) -> list[DecisionHealthFinding]:
    """Return approved decisions whose exact evidence no longer resolves in the current source.

    This check is intentionally deterministic and read-only. A source revision alone is not enough
    to invalidate a decision: the cited quote must be absent from the current immutable version.
    """

    decisions = session.scalars(
        select(Decision).where(Decision.status.in_(("active", "accepted"))).order_by(Decision.id)
    ).all()
    findings: list[DecisionHealthFinding] = []
    for decision in decisions:
        source = session.get(Source, decision.source_id)
        cited_version = session.get(SourceVersion, decision.source_version_id)
        if source is None or cited_version is None:
            raise DecisionHealthError("decision_source_missing")
        if source.content_hash != hashlib.sha256(f"source:{source.id}".encode()).hexdigest():
            raise DecisionHealthError("source_identity_invalid")
        if source.current_version_id is None:
            raise DecisionHealthError("current_source_version_missing")
        current_version = session.get(SourceVersion, source.current_version_id)
        if current_version is None:
            raise DecisionHealthError("current_source_version_missing")
        if any(
            version.content_hash != hashlib.sha256(version.content.encode()).hexdigest()
            or version.content_length != len(version.content)
            for version in (cited_version, current_version)
        ):
            raise DecisionHealthError("source_version_hash_mismatch")
        if not decision.evidence:
            raise DecisionHealthError("approved_decision_evidence_missing")
        for evidence in sorted(decision.evidence, key=lambda item: (item.start_offset, item.id)):
            exact = cited_version.content[evidence.start_offset : evidence.end_offset]
            if (
                evidence.source_id != source.id
                or evidence.source_version_id != cited_version.id
                or not 0
                <= evidence.start_offset
                < evidence.end_offset
                <= len(cited_version.content)
                or exact != evidence.quote
                or hashlib.sha256(exact.encode()).hexdigest() != evidence.quote_hash
                or evidence.start_line
                != cited_version.content.count("\n", 0, evidence.start_offset) + 1
                or evidence.end_line
                != cited_version.content.count("\n", 0, evidence.end_offset - 1) + 1
            ):
                raise DecisionHealthError("citation_provenance_invalid")
            if current_version.id == cited_version.id:
                continue
            if evidence.quote in current_version.content:
                continue
            findings.append(
                DecisionHealthFinding(
                    decision_id=decision.id,
                    decision_title=decision.title,
                    source_id=source.id,
                    source_uri=source.uri,
                    source_title=source.title,
                    cited_source_version_id=cited_version.id,
                    current_source_version_id=current_version.id,
                    start_offset=evidence.start_offset,
                    end_offset=evidence.end_offset,
                    start_line=evidence.start_line,
                    end_line=evidence.end_line,
                    quote_sha256=evidence.quote_hash,
                    cited_content_sha256=cited_version.content_hash,
                    current_content_sha256=current_version.content_hash,
                )
            )
    return findings
