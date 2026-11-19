from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from itertools import combinations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Decision, DecisionRelation
from .retrieval import ENGLISH_QUERY_STOPWORDS

MAX_DECISIONS = 2000


@dataclass(frozen=True)
class ConflictCandidate:
    first_id: str
    second_id: str
    shared_terms: list[str]
    similarity: float

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


def _terms(decision: Decision) -> frozenset[str]:
    words = re.findall(r"[\w\-]+", decision.title.casefold(), flags=re.UNICODE)
    return frozenset(w for w in words if len(w) > 2 and w not in ENGLISH_QUERY_STOPWORDS)


def find_conflict_candidates(
    session: Session, *, min_similarity: float = 0.5
) -> list[ConflictCandidate]:
    """Pairs of approved decisions about the same subject with different statements.

    A heuristic for humans to review, never a verdict: it compares title words only and skips
    pairs that already have a relation between them.
    """

    if not 0 < min_similarity <= 1:
        raise ValueError("min_similarity_invalid")
    decisions = list(
        session.scalars(
            select(Decision)
            .where(Decision.status.in_(("active", "accepted")), Decision.kind == "decision")
            .order_by(Decision.id)
            .limit(MAX_DECISIONS)
        ).all()
    )
    related = {
        frozenset((row.source_decision_id, row.target_decision_id))
        for row in session.scalars(
            select(DecisionRelation).where(
                or_(
                    DecisionRelation.source_decision_id.in_([d.id for d in decisions]),
                    DecisionRelation.target_decision_id.in_([d.id for d in decisions]),
                )
            )
        ).all()
    }
    terms = {decision.id: _terms(decision) for decision in decisions}
    found: list[ConflictCandidate] = []
    for first, second in combinations(decisions, 2):
        a, b = terms[first.id], terms[second.id]
        if (
            not a
            or not b
            or first.statement.strip().casefold() == second.statement.strip().casefold()
        ):
            continue
        if frozenset((first.id, second.id)) in related:
            continue
        similarity = len(a & b) / len(a | b)
        if similarity >= min_similarity:
            found.append(
                ConflictCandidate(
                    first_id=first.id,
                    second_id=second.id,
                    shared_terms=sorted(a & b),
                    similarity=round(similarity, 3),
                )
            )
    return sorted(found, key=lambda item: (-item.similarity, item.first_id, item.second_id))


RELATION_KINDS = ("based_on", "supersedes", "contradicts", "implements", "considered")


@dataclass(frozen=True)
class LinkSuggestion:
    other_id: str
    similarity: float
    shared_terms: list[str]
    other_is_older: bool
    kinds_to_consider: tuple[str, ...] = RELATION_KINDS

    def model_dump(self) -> dict[str, object]:
        return {**asdict(self), "kinds_to_consider": list(self.kinds_to_consider)}


def _text_terms(decision: Decision) -> frozenset[str]:
    words = re.findall(
        r"[\w\-]+", f"{decision.title} {decision.statement}".casefold(), flags=re.UNICODE
    )
    return frozenset(w for w in words if len(w) > 2 and w not in ENGLISH_QUERY_STOPWORDS)


def suggest_links(
    session: Session,
    decision_ref: str,
    *,
    limit: int = 5,
    min_similarity: float = 0.2,
) -> list[LinkSuggestion]:
    """Approved decisions a new decision probably relates to, for a person to link or ignore.

    Compares title and statement words only; it never creates a relation.
    """

    if not 1 <= limit <= 20 or not 0 < min_similarity <= 1:
        raise ValueError("suggest_arguments_invalid")
    decisions = list(session.scalars(select(Decision).order_by(Decision.id)).all())
    matches = [item for item in decisions if item.id.startswith(decision_ref)]
    if len(matches) != 1 or len(decision_ref) < 8:
        raise ValueError("decision_reference_invalid")
    subject = matches[0]
    related = {
        frozenset((row.source_decision_id, row.target_decision_id))
        for row in session.scalars(
            select(DecisionRelation).where(
                or_(
                    DecisionRelation.source_decision_id == subject.id,
                    DecisionRelation.target_decision_id == subject.id,
                )
            )
        ).all()
    }
    mine = _text_terms(subject)
    found: list[LinkSuggestion] = []
    for other in decisions:
        if other.id == subject.id or other.status not in {"active", "accepted"}:
            continue
        if other.source_version_id == subject.source_version_id:
            continue
        if frozenset((subject.id, other.id)) in related:
            continue
        theirs = _text_terms(other)
        if not mine or not theirs:
            continue
        similarity = len(mine & theirs) / len(mine | theirs)
        if similarity >= min_similarity:
            found.append(
                LinkSuggestion(
                    other_id=other.id,
                    similarity=round(similarity, 3),
                    shared_terms=sorted(mine & theirs),
                    other_is_older=(other.created_at, other.id) < (subject.created_at, subject.id),
                )
            )
    found.sort(key=lambda item: (-item.similarity, item.other_id))
    return found[:limit]
