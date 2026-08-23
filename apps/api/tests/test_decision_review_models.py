import pytest
from proofline.ingestion import ingest_source
from proofline.models import Decision, DecisionReview, Evidence
from proofline.schemas import (
    DecisionReviewAction,
    DecisionReviewReanchor,
    DecisionReviewResolve,
    SourceCreate,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def _accepted_decision(session):
    source, _created = ingest_source(
        session,
        SourceCreate(
            title="ADR",
            uri="file:///adr.md",
            content="Decision: Use SQLite.\nReason: local durability.",
        ),
    )
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    assert decision is not None
    decision.status = "accepted"
    session.commit()
    evidence = session.scalar(select(Evidence).where(Evidence.decision_id == decision.id))
    assert evidence is not None
    assert evidence.anchor_version == "markdown-context-v1"
    assert evidence.binding_root_id == evidence.id
    assert evidence.binding_state == "active"
    return source, decision, evidence


def _review(source, decision, evidence, fingerprint="a" * 64):
    return DecisionReview(
        workspace_id=source.workspace_id,
        decision_id=decision.id,
        evidence_id=evidence.id,
        cited_source_version_id=evidence.source_version_id,
        current_source_version_id=source.current_version_id,
        finding_fingerprint=fingerprint,
        anchor_state="changed",
        severity="warning",
        policy_hash="b" * 64,
        state="open",
        actor="local_system",
    )


def test_review_fingerprint_is_unique(session):
    source, decision, evidence = _accepted_decision(session)
    session.add(_review(source, decision, evidence))
    session.commit()

    session.add(_review(source, decision, evidence))
    with pytest.raises(IntegrityError):
        session.commit()


def test_review_foreign_keys_are_enforced(session):
    source, decision, evidence = _accepted_decision(session)
    review = _review(source, decision, evidence, fingerprint="c" * 64)
    review.evidence_id = "00000000-0000-0000-0000-000000000099"
    session.add(review)

    with pytest.raises(IntegrityError):
        session.commit()


def test_review_action_schemas_reject_ambiguous_mutations():
    assert DecisionReviewAction(action="acknowledge").reason is None
    with pytest.raises(ValueError, match="waive requires a reason"):
        DecisionReviewAction(action="waive", reason="  ")
    with pytest.raises(ValueError, match="reanchor offsets are invalid"):
        DecisionReviewReanchor(
            expected_current_source_version_id="v" * 36,
            start_offset=10,
            end_offset=10,
            reason="Reviewed",
        )
    with pytest.raises(ValueError, match="replacement decision is required"):
        DecisionReviewResolve(action="supersede_decision", reason="Replaced")
