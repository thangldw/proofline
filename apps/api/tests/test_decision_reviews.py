import pytest
from proofline.decision_policy import DecisionHealthPolicy, policy_sha256
from proofline.decision_reviews import (
    DecisionReviewError,
    refresh_decision_reviews,
    review_fingerprint,
)
from proofline.ingestion import ingest_source
from proofline.models import AuditEvent, Decision, DecisionReview, Evidence
from proofline.schemas import SourceCreate
from sqlalchemy import func, select

ORIGINAL = "# Queue\n\nDecision: Use SQLite.\nReason: local durability."
CHANGED = "# Queue\n\nDecision: Use NATS.\nReason: shared workload."


def _accepted_decision(session):
    source, _created = ingest_source(
        session,
        SourceCreate(title="ADR", uri="file:///adr.md", content=ORIGINAL),
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
    return source, decision


def _change_source(session, source, content=CHANGED):
    updated, created = ingest_source(
        session,
        SourceCreate(title="ADR", uri=source.uri, content=content),
    )
    assert created is False
    return updated


def test_refresh_opens_one_review_without_changing_accepted_decision(session):
    source, decision = _accepted_decision(session)
    _change_source(session, source)

    first = refresh_decision_reviews(session, workspace_id=source.workspace_id)
    second = refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()

    assert first.opened == 1
    assert second.opened == 0
    assert session.get(Decision, decision.id).status == "accepted"
    review = session.scalar(select(DecisionReview))
    assert review is not None
    assert review.state == "open"
    assert review.anchor_state == "changed"
    assert review.finding_fingerprint == review_fingerprint(
        decision_id=decision.id,
        evidence_id=review.evidence_id,
        cited_source_version_id=review.cited_source_version_id,
        current_source_version_id=review.current_source_version_id,
        anchor_state=review.anchor_state,
    )
    assert session.scalar(select(func.count()).select_from(DecisionReview)) == 1


def test_new_source_version_supersedes_previous_open_finding(session):
    source, decision = _accepted_decision(session)
    _change_source(session, source)
    refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()
    first = session.scalar(select(DecisionReview))
    assert first is not None

    _change_source(
        session,
        source,
        "# Queue\n\nDecision: Use Kafka.\nReason: durable shared workload.",
    )
    summary = refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()

    session.refresh(first)
    reviews = list(
        session.scalars(
            select(DecisionReview)
            .where(DecisionReview.decision_id == decision.id)
            .order_by(DecisionReview.opened_at)
        )
    )
    assert summary.opened == 2
    assert summary.superseded == 1
    assert first.state == "superseded"
    assert [review.state for review in reviews] == ["superseded", "open"]


def test_source_restoration_resolves_open_review(session):
    source, _decision = _accepted_decision(session)
    _change_source(session, source)
    refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()

    _change_source(session, source, f"{ORIGINAL}\n\nRestored editorial note.")
    summary = refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()

    review = session.scalar(select(DecisionReview))
    assert summary.resolved == 1
    assert review is not None
    assert review.state == "resolved"
    assert review.resolution == "source_restored"
    assert review.closed_at is not None


def test_refresh_updates_policy_hash_without_duplicate_review(session):
    source, _decision = _accepted_decision(session)
    _change_source(session, source)
    refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()
    review = session.scalar(select(DecisionReview))
    assert review is not None

    policy = DecisionHealthPolicy(allow_waiver=False, max_open_age_days=30)
    summary = refresh_decision_reviews(
        session,
        workspace_id=source.workspace_id,
        policy=policy,
    )
    session.commit()

    session.refresh(review)
    assert summary.updated == 1
    assert review.policy_hash == policy_sha256(policy)
    assert session.scalar(select(func.count()).select_from(DecisionReview)) == 1


def test_refresh_is_workspace_scoped_and_audited(session):
    source, _decision = _accepted_decision(session)
    _change_source(session, source)

    summary = refresh_decision_reviews(
        session,
        workspace_id=source.workspace_id,
        source_ids={source.id},
    )
    session.commit()

    assert summary.opened == 1
    event = session.scalar(select(AuditEvent).where(AuditEvent.object_type == "decision_review"))
    assert event is not None
    assert event.workspace_id == source.workspace_id
    assert event.before_json == {}
    assert event.after_json["state"] == "open"


def test_corrupt_anchor_fails_closed_without_review_mutation(session):
    source, decision = _accepted_decision(session)
    evidence = session.scalar(select(Evidence).where(Evidence.decision_id == decision.id))
    assert evidence is not None
    evidence.prefix_sha256 = "0" * 64
    session.commit()
    _change_source(session, source)

    with pytest.raises(DecisionReviewError, match="^citation_anchor_invalid$"):
        refresh_decision_reviews(session, workspace_id=source.workspace_id)

    session.rollback()
    assert session.scalar(select(func.count()).select_from(DecisionReview)) == 0
