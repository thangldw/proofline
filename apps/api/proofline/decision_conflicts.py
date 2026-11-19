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
