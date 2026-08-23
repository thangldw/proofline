from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .decision_health import DecisionHealthError, check_decision_health
from .decision_policy import DecisionHealthPolicy, policy_sha256
from .models import AuditEvent, Decision, DecisionReview, Source, utc_now

ACTIVE_REVIEW_STATES = frozenset({"open", "acknowledged"})


class DecisionReviewError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReviewRefreshSummary:
    opened: int = 0
    superseded: int = 0
    resolved: int = 0
    updated: int = 0
    unchanged: int = 0

    def model_dump(self) -> dict[str, int]:
        return asdict(self)


def review_fingerprint(
    *,
    decision_id: str,
    evidence_id: str,
    cited_source_version_id: str,
    current_source_version_id: str,
    anchor_state: str,
) -> str:
    canonical = json.dumps(
        {
            "anchor_state": anchor_state,
            "cited_source_version_id": cited_source_version_id,
            "current_source_version_id": current_source_version_id,
            "decision_id": decision_id,
            "evidence_id": evidence_id,
            "schema": "proofline-decision-review-finding-v1",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot(review: DecisionReview) -> dict[str, str | None]:
    return {
        "anchor_state": review.anchor_state,
        "current_source_version_id": review.current_source_version_id,
        "finding_fingerprint": review.finding_fingerprint,
        "policy_hash": review.policy_hash,
        "resolution": review.resolution,
        "state": review.state,
    }


def _audit_transition(
    session: Session,
    review: DecisionReview,
    *,
    action: str,
    before: dict[str, str | None],
) -> None:
    session.flush()
    session.add(
        AuditEvent(
            workspace_id=review.workspace_id,
            actor=review.actor,
            action=action,
            object_type="decision_review",
            object_id=review.id,
            before_json=before,
            after_json=_snapshot(review),
        )
    )


def _scoped_active_reviews(
    session: Session, *, workspace_id: str, source_ids: set[str] | None
) -> list[DecisionReview]:
    statement = (
        select(DecisionReview)
        .join(Decision, Decision.id == DecisionReview.decision_id)
        .join(Source, Source.id == Decision.source_id)
        .where(
            DecisionReview.workspace_id == workspace_id,
            DecisionReview.state.in_(ACTIVE_REVIEW_STATES),
        )
        .order_by(DecisionReview.opened_at, DecisionReview.id)
    )
    if source_ids is not None:
        statement = statement.where(Source.id.in_(source_ids))
    return list(session.scalars(statement).all())


def refresh_decision_reviews(
    session: Session,
    *,
    workspace_id: str,
    source_ids: set[str] | None = None,
    policy: DecisionHealthPolicy | None = None,
) -> ReviewRefreshSummary:
    selected_policy = policy or DecisionHealthPolicy()
    selected_policy_hash = policy_sha256(selected_policy)
    try:
        findings = check_decision_health(
            session,
            workspace_id=workspace_id,
            source_ids=source_ids,
        )
    except (DecisionHealthError, ValueError) as exc:
        code = exc.code if isinstance(exc, DecisionHealthError) else str(exc)
        raise DecisionReviewError(code) from exc

    opened = superseded = resolved = updated = unchanged = 0
    active_reviews = _scoped_active_reviews(
        session,
        workspace_id=workspace_id,
        source_ids=source_ids,
    )
    findings_by_evidence = {finding.evidence_id: finding for finding in findings}

    for finding in findings:
        fingerprint = review_fingerprint(
            decision_id=finding.decision_id,
            evidence_id=finding.evidence_id,
            cited_source_version_id=finding.cited_source_version_id,
            current_source_version_id=finding.current_source_version_id,
            anchor_state=finding.reason,
        )
        for review in active_reviews:
            if (
                review.evidence_id == finding.evidence_id
                and review.current_source_version_id != finding.current_source_version_id
                and review.state in ACTIVE_REVIEW_STATES
            ):
                before = _snapshot(review)
                review.state = "superseded"
                review.resolution = "newer_source_version"
                review.closed_at = utc_now()
                review.updated_at = review.closed_at
                _audit_transition(
                    session,
                    review,
                    action="decision_review_superseded",
                    before=before,
                )
                superseded += 1

        existing = session.scalar(
            select(DecisionReview).where(DecisionReview.finding_fingerprint == fingerprint)
        )
        if existing is not None:
            if existing.policy_hash != selected_policy_hash:
                before = _snapshot(existing)
                existing.policy_hash = selected_policy_hash
                existing.updated_at = utc_now()
                _audit_transition(
                    session,
                    existing,
                    action="decision_review_policy_updated",
                    before=before,
                )
                updated += 1
            else:
                unchanged += 1
            continue

        review = DecisionReview(
            workspace_id=workspace_id,
            decision_id=finding.decision_id,
            evidence_id=finding.evidence_id,
            cited_source_version_id=finding.cited_source_version_id,
            current_source_version_id=finding.current_source_version_id,
            finding_fingerprint=fingerprint,
            anchor_state=finding.reason,
            severity="warning",
            policy_hash=selected_policy_hash,
            candidate_start_offset=finding.candidate_start_offset,
            candidate_end_offset=finding.candidate_end_offset,
            candidate_start_line=finding.candidate_start_line,
            candidate_end_line=finding.candidate_end_line,
            state="open",
            actor="local_system",
        )
        session.add(review)
        _audit_transition(session, review, action="decision_review_opened", before={})
        active_reviews.append(review)
        opened += 1

    for review in active_reviews:
        if review.state not in ACTIVE_REVIEW_STATES or review.evidence_id in findings_by_evidence:
            continue
        before = _snapshot(review)
        review.state = "resolved"
        review.resolution = "source_restored"
        review.closed_at = utc_now()
        review.updated_at = review.closed_at
        _audit_transition(
            session,
            review,
            action="decision_review_source_restored",
            before=before,
        )
        resolved += 1

    session.flush()
    return ReviewRefreshSummary(
        opened=opened,
        superseded=superseded,
        resolved=resolved,
        updated=updated,
        unchanged=unchanged,
    )
