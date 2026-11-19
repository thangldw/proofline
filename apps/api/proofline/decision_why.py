from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .decision_health import check_decision_health
from .models import Decision, Source
from .retrieval import ENGLISH_QUERY_STOPWORDS

MAX_QUESTION_CHARS = 500


class DecisionWhyError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WhyAnswer:
    decision_id: str
    decision_title: str
    status: str
    health: str
    matched_terms: list[str]
    source_id: str
    source_title: str
    start_line: int
    end_line: int
    quote: str
    rationale: str | None

    def model_dump(self) -> dict[str, object]:
        return asdict(self)

    def content_free_model_dump(self) -> dict[str, object]:
        document = self.model_dump()
        for key in ("decision_title", "source_title", "quote", "rationale"):
            document.pop(key)
        return document


def _terms(question: str) -> list[str]:
    raw = [item.casefold() for item in re.findall(r"[\w\-]+", question, flags=re.UNICODE)]
    kept = [item for item in raw if item not in ENGLISH_QUERY_STOPWORDS and len(item) > 1]
    return list(dict.fromkeys(kept or raw))


def why(session: Session, question: str, *, limit: int = 5) -> list[WhyAnswer]:
    """Approved decisions relevant to a question, with their exact citation and health.

    Deterministic term matching over decision text; it never generates prose. A decision whose
    citation no longer resolves is returned with its health state so the caller can distrust it.
    """

    if not question.strip() or len(question) > MAX_QUESTION_CHARS:
        raise DecisionWhyError("question_invalid")
    if not 1 <= limit <= 20:
        raise DecisionWhyError("limit_invalid")
    terms = _terms(question)
    if not terms:
        return []
    decisions = session.scalars(
        select(Decision)
        .options(selectinload(Decision.evidence))
        .where(Decision.status.in_(("active", "accepted")))
        .order_by(Decision.id)
    ).all()
    scored: list[tuple[int, Decision, list[str]]] = []
    for decision in decisions:
        haystack = f"{decision.title}\n{decision.statement}\n{decision.rationale or ''}".casefold()
        matched = [term for term in terms if term in haystack]
        if matched:
            scored.append((len(matched), decision, matched))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    selected = scored[:limit]
    if not selected:
        return []
    findings = {
        finding.decision_id: finding.reason
        for finding in check_decision_health(
            session, source_ids={decision.source_id for _, decision, _ in selected}
        )
    }
    sources = {
        source.id: source
        for source in session.scalars(
            select(Source).where(Source.id.in_({decision.source_id for _, decision, _ in selected}))
        ).all()
    }
    answers: list[WhyAnswer] = []
    for _, decision, matched in selected:
        active = [item for item in decision.evidence if item.binding_state == "active"]
        if not active:
            continue
        evidence = min(active, key=lambda item: (item.start_offset, item.id))
        source = sources[decision.source_id]
        answers.append(
            WhyAnswer(
                decision_id=decision.id,
                decision_title=decision.title,
                status=decision.status,
                health=findings.get(decision.id, "current"),
                matched_terms=matched,
                source_id=source.id,
                source_title=source.title,
                start_line=evidence.start_line,
                end_line=evidence.end_line,
                quote=evidence.quote,
                rationale=decision.rationale,
            )
        )
    return answers
