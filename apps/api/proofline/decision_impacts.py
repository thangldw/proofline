from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Decision, DecisionRelation, DecisionReview, Source, utc_now

DEPENDENCY_RELATION_KINDS = frozenset({"based_on", "implements"})
CURRENT_DECISION_STATUSES = frozenset({"active", "accepted"})
ROOT_REVIEW_STATES = frozenset({"open", "acknowledged"})


class DecisionImpactError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DecisionImpactFinding:
    root_review_id: str
    root_review_fingerprint: str
    root_decision_id: str
    root_decision_title: str
    impacted_decision_id: str
    impacted_decision_title: str
    depth: int
    decision_path: tuple[str, ...]
    relation_path: tuple[str, ...]
    relation_kinds: tuple[str, ...]
    evaluated_at: datetime
    fingerprint: str

    def model_dump(self) -> dict[str, object]:
        return {
            "root_review_id": self.root_review_id,
            "root_review_fingerprint": self.root_review_fingerprint,
            "root_decision_id": self.root_decision_id,
            "root_decision_title": self.root_decision_title,
            "impacted_decision_id": self.impacted_decision_id,
            "impacted_decision_title": self.impacted_decision_title,
            "depth": self.depth,
            "decision_path": list(self.decision_path),
            "relation_path": list(self.relation_path),
            "relation_kinds": list(self.relation_kinds),
            "evaluated_at": self.evaluated_at.isoformat(),
            "fingerprint": self.fingerprint,
        }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_active(relation: DecisionRelation, as_of: datetime) -> bool:
    return not (relation.valid_from is not None and _utc(relation.valid_from) > as_of) and not (
        relation.valid_to is not None and _utc(relation.valid_to) <= as_of
    )


def _fingerprint(
    review: DecisionReview,
    impacted_decision_id: str,
    relation_path: tuple[str, ...],
) -> str:
    payload = {
        "schema": "proofline-decision-impact-fingerprint-v1",
        "root_review_id": review.id,
        "root_review_fingerprint": review.finding_fingerprint,
        "impacted_decision_id": impacted_decision_id,
        "relation_path": list(relation_path),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(b"proofline/decision-impact/v1\0" + encoded).hexdigest()


def compute_decision_impacts(
    session: Session,
    *,
    workspace_id: str,
    as_of: datetime | None = None,
) -> list[DecisionImpactFinding]:
    """Derive transitive impact from unresolved reviews through explicit dependency relations."""

    evaluated_at = _utc(as_of or utc_now())
    decisions = list(
        session.scalars(
            select(Decision)
            .join(Source, Source.id == Decision.source_id)
            .where(
                Source.workspace_id == workspace_id,
                Decision.kind == "decision",
                Decision.status.in_(CURRENT_DECISION_STATUSES),
            )
            .order_by(Decision.id)
        ).all()
    )
    by_id = {decision.id: decision for decision in decisions}
    if not by_id:
        return []

    reviews = list(
        session.scalars(
            select(DecisionReview)
            .where(
                DecisionReview.workspace_id == workspace_id,
                DecisionReview.decision_id.in_(by_id),
                DecisionReview.state.in_(ROOT_REVIEW_STATES),
            )
            .order_by(DecisionReview.id)
        ).all()
    )
    if not reviews:
        return []

    relations = list(
        session.scalars(
            select(DecisionRelation)
            .where(
                DecisionRelation.source_decision_id.in_(by_id),
                DecisionRelation.target_decision_id.in_(by_id),
                DecisionRelation.kind.in_(DEPENDENCY_RELATION_KINDS),
            )
            .order_by(DecisionRelation.id)
        ).all()
    )
    adjacency: dict[str, list[DecisionRelation]] = {}
    for relation in relations:
        if _is_active(relation, evaluated_at):
            adjacency.setdefault(relation.target_decision_id, []).append(relation)

    findings: list[DecisionImpactFinding] = []
    for review in reviews:
        root = by_id.get(review.decision_id)
        if root is None:
            continue
        queue: list[tuple[int, tuple[str, ...], str, tuple[str, ...], tuple[str, ...]]] = [
            (0, (), root.id, (root.id,), ())
        ]
        best: dict[str, tuple[int, tuple[str, ...]]] = {root.id: (0, ())}
        while queue:
            depth, relation_path, current_id, decision_path, relation_kinds = heapq.heappop(queue)
            if best.get(current_id) != (depth, relation_path):
                continue
            if current_id != root.id:
                impacted = by_id[current_id]
                findings.append(
                    DecisionImpactFinding(
                        root_review_id=review.id,
                        root_review_fingerprint=review.finding_fingerprint,
                        root_decision_id=root.id,
                        root_decision_title=root.title,
                        impacted_decision_id=impacted.id,
                        impacted_decision_title=impacted.title,
                        depth=depth,
                        decision_path=decision_path,
                        relation_path=relation_path,
                        relation_kinds=relation_kinds,
                        evaluated_at=evaluated_at,
                        fingerprint=_fingerprint(review, impacted.id, relation_path),
                    )
                )
            for relation in adjacency.get(current_id, ()):
                dependent_id = relation.source_decision_id
                if dependent_id in decision_path:
                    continue
                candidate_path = relation_path + (relation.id,)
                candidate = (depth + 1, candidate_path)
                if dependent_id in best and best[dependent_id] <= candidate:
                    continue
                best[dependent_id] = candidate
                heapq.heappush(
                    queue,
                    (
                        depth + 1,
                        candidate_path,
                        dependent_id,
                        decision_path + (dependent_id,),
                        relation_kinds + (relation.kind,),
                    ),
                )

    return sorted(
        findings,
        key=lambda item: (
            item.root_review_id,
            item.depth,
            item.relation_path,
            item.impacted_decision_id,
        ),
    )
