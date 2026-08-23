from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .decision_health import DecisionHealthError, check_decision_health
from .decision_policy import DecisionHealthPolicy, policy_sha256
from .models import (
    AuditEvent,
    Decision,
    DecisionRelation,
    DecisionReview,
    Evidence,
    Source,
    SourceVersion,
    utc_now,
)

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
        "actor": review.actor,
        "closed_at": review.closed_at.isoformat() if review.closed_at else None,
        "current_source_version_id": review.current_source_version_id,
        "finding_fingerprint": review.finding_fingerprint,
        "note": review.note,
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
    after_extra: dict[str, str | None] | None = None,
) -> None:
    session.flush()
    after = _snapshot(review)
    if after_extra:
        after.update(after_extra)
    session.add(
        AuditEvent(
            workspace_id=review.workspace_id,
            actor=review.actor,
            action=action,
            object_type="decision_review",
            object_id=review.id,
            before_json=before,
            after_json=after,
        )
    )


def _get_actionable_review(
    session: Session,
    review_id: str,
    *,
    workspace_id: str,
) -> DecisionReview:
    review = session.scalar(
        select(DecisionReview).where(
            DecisionReview.id == review_id,
            DecisionReview.workspace_id == workspace_id,
        )
    )
    if review is None:
        raise DecisionReviewError("review_not_found")
    if review.state not in ACTIVE_REVIEW_STATES:
        raise DecisionReviewError("review_state_conflict")
    return review


def _clean_reason(reason: str | None, *, required: bool) -> str | None:
    cleaned = (reason or "").strip()
    if required and not cleaned:
        raise DecisionReviewError("review_reason_required")
    if len(cleaned) > 2_000:
        raise DecisionReviewError("review_reason_too_long")
    return cleaned or None


def _clean_actor(actor: str) -> str:
    cleaned = actor.strip()
    if not cleaned or len(cleaned) > 100:
        raise DecisionReviewError("review_actor_invalid")
    return cleaned


def _claim_transition(
    session: Session,
    review: DecisionReview,
    *,
    state: str,
    resolution: str | None,
    actor: str,
    note: str | None,
    closed_at: datetime | None,
) -> dict[str, str | None]:
    before = _snapshot(review)
    result = session.execute(
        update(DecisionReview)
        .where(
            DecisionReview.id == review.id,
            DecisionReview.workspace_id == review.workspace_id,
            DecisionReview.state == review.state,
        )
        .values(
            state=state,
            resolution=resolution,
            actor=actor,
            note=note,
            closed_at=closed_at,
            updated_at=utc_now(),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise DecisionReviewError("review_state_conflict")
    session.refresh(review)
    return before


def apply_review_action(
    session: Session,
    review_id: str,
    *,
    workspace_id: str,
    action: str,
    actor: str,
    reason: str | None = None,
    policy: DecisionHealthPolicy | None = None,
) -> DecisionReview:
    review = _get_actionable_review(session, review_id, workspace_id=workspace_id)
    selected_policy = policy or DecisionHealthPolicy()
    selected_actor = _clean_actor(actor)
    if action == "acknowledge":
        if review.state != "open":
            raise DecisionReviewError("review_state_conflict")
        note = _clean_reason(reason, required=False)
        next_state = "acknowledged"
        resolution = None
        closed_at = None
    elif action == "waive":
        if not selected_policy.allow_waiver:
            raise DecisionReviewError("review_waiver_disabled")
        note = _clean_reason(reason, required=True)
        next_state = "waived"
        resolution = "policy_waiver"
        closed_at = utc_now()
    else:
        raise DecisionReviewError("review_action_invalid")

    before = _claim_transition(
        session,
        review,
        state=next_state,
        resolution=resolution,
        actor=selected_actor,
        note=note,
        closed_at=closed_at,
    )
    _audit_transition(
        session,
        review,
        action=f"decision_review_{next_state}",
        before=before,
    )
    session.flush()
    return review


def reanchor_review(
    session: Session,
    review_id: str,
    *,
    workspace_id: str,
    expected_current_source_version_id: str,
    start_offset: int,
    end_offset: int,
    actor: str,
    reason: str,
) -> DecisionReview:
    review = _get_actionable_review(session, review_id, workspace_id=workspace_id)
    selected_actor = _clean_actor(actor)
    selected_reason = _clean_reason(reason, required=True)
    decision = session.get(Decision, review.decision_id)
    evidence = session.get(Evidence, review.evidence_id)
    if decision is None or evidence is None or evidence.binding_state != "active":
        raise DecisionReviewError("review_provenance_invalid")
    source = session.scalar(
        select(Source).where(
            Source.id == decision.source_id,
            Source.workspace_id == workspace_id,
        )
    )
    if source is None or source.current_version_id is None:
        raise DecisionReviewError("review_provenance_invalid")
    if (
        source.current_version_id != expected_current_source_version_id
        or review.current_source_version_id != expected_current_source_version_id
    ):
        raise DecisionReviewError("source_version_conflict")
    current_version = session.get(SourceVersion, source.current_version_id)
    if current_version is None or current_version.source_id != source.id:
        raise DecisionReviewError("review_provenance_invalid")
    if not 0 <= start_offset < end_offset <= len(current_version.content):
        raise DecisionReviewError("reanchor_span_invalid")
    active_evidence = [item for item in decision.evidence if item.binding_state == "active"]
    if len(active_evidence) != 1 or active_evidence[0].id != evidence.id:
        raise DecisionReviewError("decision_reanchor_multiple_evidence_unsupported")

    quote = current_version.content[start_offset:end_offset]
    replacement = Evidence.anchored(
        source_content=current_version.content,
        decision_id=decision.id,
        source_id=source.id,
        source_version_id=current_version.id,
        quote=quote,
        quote_hash=hashlib.sha256(quote.encode()).hexdigest(),
        start_offset=start_offset,
        end_offset=end_offset,
        start_line=current_version.content.count("\n", 0, start_offset) + 1,
        end_line=current_version.content.count("\n", 0, end_offset - 1) + 1,
        binding_root_id=evidence.binding_root_id,
    )
    now = utc_now()
    before = _claim_transition(
        session,
        review,
        state="resolved",
        resolution="reanchored",
        actor=selected_actor,
        note=selected_reason,
        closed_at=now,
    )
    decision.evidence.append(replacement)
    session.flush()
    evidence.binding_state = "superseded"
    evidence.superseded_at = now
    evidence.superseded_by_id = replacement.id
    decision.source_version_id = current_version.id
    decision.updated_at = now
    _audit_transition(
        session,
        review,
        action="decision_review_reanchored",
        before=before,
        after_extra={
            "new_evidence_id": replacement.id,
            "old_evidence_id": evidence.id,
            "source_version_id": current_version.id,
        },
    )
    session.flush()
    return review


def resolve_review(
    session: Session,
    review_id: str,
    *,
    workspace_id: str,
    action: str,
    actor: str,
    reason: str,
    replacement_decision_id: str | None = None,
) -> DecisionReview:
    review = _get_actionable_review(session, review_id, workspace_id=workspace_id)
    selected_actor = _clean_actor(actor)
    selected_reason = _clean_reason(reason, required=True)
    decision = session.scalar(
        select(Decision)
        .join(Source, Source.id == Decision.source_id)
        .where(
            Decision.id == review.decision_id,
            Source.workspace_id == workspace_id,
        )
    )
    if decision is None:
        raise DecisionReviewError("review_provenance_invalid")
    if action not in {"obsolete_decision", "supersede_decision"}:
        raise DecisionReviewError("review_action_invalid")
    if action == "obsolete_decision" and replacement_decision_id is not None:
        raise DecisionReviewError("replacement_decision_invalid")

    replacement: Decision | None = None
    if action == "supersede_decision":
        if replacement_decision_id is None or replacement_decision_id == decision.id:
            raise DecisionReviewError("replacement_decision_invalid")
        replacement = session.scalar(
            select(Decision)
            .join(Source, Source.id == Decision.source_id)
            .where(
                Decision.id == replacement_decision_id,
                Decision.kind == "decision",
                Decision.status == "accepted",
                Source.workspace_id == workspace_id,
            )
        )
        if replacement is None:
            raise DecisionReviewError("replacement_decision_not_found")

    now = utc_now()
    before = _claim_transition(
        session,
        review,
        state="resolved",
        resolution=action,
        actor=selected_actor,
        note=selected_reason,
        closed_at=now,
    )
    decision.status = "obsolete"
    decision.valid_to = now
    decision.updated_at = now
    if replacement is not None:
        replacement.valid_from = replacement.valid_from or now
        replacement.updated_at = now
        session.add(
            DecisionRelation(
                source_decision_id=replacement.id,
                target_decision_id=decision.id,
                kind="supersedes",
                valid_from=now,
                created_by="decision_review",
            )
        )

    _audit_transition(
        session,
        review,
        action=f"decision_review_{action}",
        before=before,
        after_extra={
            "decision_status": decision.status,
            "replacement_decision_id": replacement.id if replacement else None,
        },
    )
    other_reviews = session.scalars(
        select(DecisionReview).where(
            DecisionReview.decision_id == decision.id,
            DecisionReview.id != review.id,
            DecisionReview.state.in_(ACTIVE_REVIEW_STATES),
        )
    ).all()
    for other in other_reviews:
        other_before = _claim_transition(
            session,
            other,
            state="resolved",
            resolution=action,
            actor=selected_actor,
            note=selected_reason,
            closed_at=now,
        )
        _audit_transition(
            session,
            other,
            action=f"decision_review_{action}",
            before=other_before,
            after_extra={
                "decision_status": decision.status,
                "replacement_decision_id": replacement.id if replacement else None,
            },
        )
    session.flush()
    return review


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
