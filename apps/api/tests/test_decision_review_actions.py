import pytest
from proofline.api import decision_to_read
from proofline.decision_policy import DecisionHealthPolicy
from proofline.decision_reviews import (
    DecisionReviewError,
    apply_review_action,
    reanchor_review,
    refresh_decision_reviews,
    resolve_review,
)
from proofline.evidence_packages import build_decision_package
from proofline.ingestion import ingest_source
from proofline.models import AuditEvent, Decision, DecisionRelation, DecisionReview, Evidence
from proofline.schemas import SourceCreate
from sqlalchemy import select

ORIGINAL = "# Queue\n\nDecision: Use SQLite.\nReason: local durability."
CHANGED = "# Queue\n\nDecision: Use NATS.\nReason: shared workload."


def _open_review(session):
    source, _created = ingest_source(
        session,
        SourceCreate(title="ADR", uri="file:///adr-actions.md", content=ORIGINAL),
    )
    decision = session.scalar(
        select(Decision).where(
            Decision.source_version_id == source.current_version_id,
            Decision.kind == "decision",
        )
    )
    assert decision is not None
    decision.status = "accepted"
    session.commit()
    source, _created = ingest_source(
        session,
        SourceCreate(title="ADR", uri=source.uri, content=CHANGED),
    )
    refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()
    review = session.scalar(select(DecisionReview).where(DecisionReview.decision_id == decision.id))
    assert review is not None
    return source, decision, review


def test_acknowledge_is_audited_and_second_acknowledgement_conflicts(session):
    source, _decision, review = _open_review(session)

    apply_review_action(
        session,
        review.id,
        workspace_id=source.workspace_id,
        action="acknowledge",
        actor="alice",
    )
    session.commit()

    assert review.state == "acknowledged"
    assert review.actor == "alice"
    event = session.scalar(
        select(AuditEvent).where(AuditEvent.action == "decision_review_acknowledged")
    )
    assert event is not None
    assert event.actor == "alice"
    with pytest.raises(DecisionReviewError, match="^review_state_conflict$"):
        apply_review_action(
            session,
            review.id,
            workspace_id=source.workspace_id,
            action="acknowledge",
            actor="alice",
        )


def test_waiver_requires_policy_permission_and_reason(session):
    source, _decision, review = _open_review(session)

    with pytest.raises(DecisionReviewError, match="^review_waiver_disabled$"):
        apply_review_action(
            session,
            review.id,
            workspace_id=source.workspace_id,
            action="waive",
            actor="release-bot",
            reason="time-boxed exception",
            policy=DecisionHealthPolicy(allow_waiver=False),
        )
    with pytest.raises(DecisionReviewError, match="^review_reason_required$"):
        apply_review_action(
            session,
            review.id,
            workspace_id=source.workspace_id,
            action="waive",
            actor="release-bot",
            reason=" ",
        )

    apply_review_action(
        session,
        review.id,
        workspace_id=source.workspace_id,
        action="waive",
        actor="release-bot",
        reason="time-boxed exception",
    )
    session.commit()

    assert review.state == "waived"
    assert review.resolution == "policy_waiver"
    assert review.note == "time-boxed exception"
    assert review.closed_at is not None


def test_review_actions_are_workspace_scoped(session):
    _source, _decision, review = _open_review(session)

    with pytest.raises(DecisionReviewError, match="^review_not_found$"):
        apply_review_action(
            session,
            review.id,
            workspace_id="00000000-0000-0000-0000-000000000099",
            action="acknowledge",
            actor="alice",
        )


def test_reanchor_rejects_source_version_conflict(session):
    source, _decision, review = _open_review(session)
    start = CHANGED.index("Decision: Use NATS.")

    with pytest.raises(DecisionReviewError, match="^source_version_conflict$"):
        reanchor_review(
            session,
            review.id,
            workspace_id=source.workspace_id,
            expected_current_source_version_id=review.cited_source_version_id,
            start_offset=start,
            end_offset=start + len("Decision: Use NATS."),
            actor="alice",
            reason="requirement intentionally changed",
        )


def test_reanchor_supersedes_binding_and_package_uses_only_new_evidence(session):
    source, decision, review = _open_review(session)
    old_evidence = session.get(Evidence, review.evidence_id)
    assert old_evidence is not None
    start = CHANGED.index("Decision: Use NATS.")
    end = start + len("Decision: Use NATS.")

    reanchor_review(
        session,
        review.id,
        workspace_id=source.workspace_id,
        expected_current_source_version_id=source.current_version_id,
        start_offset=start,
        end_offset=end,
        actor="alice",
        reason="requirement intentionally changed",
    )
    session.commit()

    active = session.scalar(
        select(Evidence).where(
            Evidence.decision_id == decision.id,
            Evidence.binding_state == "active",
        )
    )
    assert active is not None
    assert active.id != old_evidence.id
    assert active.binding_root_id == old_evidence.binding_root_id
    assert active.quote == "Decision: Use NATS."
    assert active.source_version_id == source.current_version_id
    assert old_evidence.binding_state == "superseded"
    assert old_evidence.superseded_by_id == active.id
    assert decision.source_version_id == source.current_version_id
    assert review.state == "resolved"
    assert review.resolution == "reanchored"
    assert [item.id for item in decision_to_read(decision).evidence] == [active.id]
    package = build_decision_package(session, decision.id)
    assert [item["id"] for item in package["payload"]["citations"]] == [active.id]


def test_resolve_review_can_mark_decision_obsolete(session):
    source, decision, review = _open_review(session)

    resolve_review(
        session,
        review.id,
        workspace_id=source.workspace_id,
        action="obsolete_decision",
        actor="alice",
        reason="decision no longer applies",
    )
    session.commit()

    assert decision.status == "obsolete"
    assert decision.valid_to is not None
    assert review.state == "resolved"
    assert review.resolution == "obsolete_decision"


def test_resolve_review_can_supersede_decision(session):
    source, decision, review = _open_review(session)
    replacement = session.scalar(
        select(Decision).where(
            Decision.source_version_id == source.current_version_id,
            Decision.kind == "decision",
        )
    )
    assert replacement is not None

    resolve_review(
        session,
        review.id,
        workspace_id=source.workspace_id,
        action="supersede_decision",
        replacement_decision_id=replacement.id,
        actor="alice",
        reason="new decision replaces the cited one",
    )
    session.commit()

    relation = session.scalar(select(DecisionRelation))
    assert relation is not None
    assert relation.kind == "supersedes"
    assert relation.source_decision_id == replacement.id
    assert relation.target_decision_id == decision.id
    assert decision.status == "obsolete"
    assert review.state == "resolved"
    assert review.resolution == "supersede_decision"
