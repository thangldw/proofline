import json

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_blame import blame
from proofline.decision_rebind import apply_rebind, list_pending_reviews, preview_rebind
from proofline.decision_reviews import DecisionReviewError, refresh_decision_reviews
from proofline.ingestion import ingest_source
from proofline.models import DEFAULT_WORKSPACE_ID, Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ORIGINAL = "Decision: Use SQLite for the local queue.\nReason: no network service is permitted."
EDITED = (
    "Decision: Use SQLite for the durable local queue.\nReason: no network service is permitted."
)


def _stale(session, edited=EDITED):
    source, _ = ingest_source(
        session, SourceCreate(title="adr", uri="file:///repo/adr.md", content=ORIGINAL)
    )
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    ingest_source(session, SourceCreate(title="adr", uri=source.uri, content=edited))
    refresh_decision_reviews(session, workspace_id=DEFAULT_WORKSPACE_ID)
    session.commit()
    return decision


def _review_for(session, decision):
    return next(item for item in list_pending_reviews(session) if item.decision_id == decision.id)


def test_preview_shows_a_diff_and_apply_reanchors_the_decision(session):
    decision = _stale(session)
    review = _review_for(session, decision)
    preview = preview_rebind(session, review.id)
    assert preview.can_apply and preview.candidate_text
    assert any(line.startswith("-") for line in preview.diff)
    assert any(line.startswith("+") and "durable" in line for line in preview.diff)
    applied = apply_rebind(session, review.id, actor="tester", reason="wording only")
    session.commit()
    assert applied.state == "resolved" and applied.resolution == "reanchored"
    assert all(item.id != review.id for item in list_pending_reviews(session))
    entries = [e for e in blame(session, "adr.md") if e.decision_id == decision.id]
    assert entries and entries[0].state == "unchanged"


def test_apply_requires_a_candidate_and_an_open_review(session):
    decision = _stale(session, edited="Unrelated text.")
    review = _review_for(session, decision)
    preview = preview_rebind(session, review.id)
    assert not preview.can_apply and preview.blocker == "no_candidate"
    with pytest.raises(DecisionReviewError) as caught:
        apply_rebind(session, review.id, actor="tester", reason="x")
    assert caught.value.code == "no_candidate"
    with pytest.raises(DecisionReviewError):
        preview_rebind(session, "missing")


def test_cli_rebind_lists_previews_and_applies(session, monkeypatch, capsys):
    decision = _stale(session)
    review = _review_for(session, decision)
    monkeypatch.setattr(
        cli_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), expire_on_commit=False),
    )
    main(["rebind", "--format", "json"])
    assert review.id in {item["id"] for item in json.loads(capsys.readouterr().out)["pending"]}
    main(["rebind", review.id])
    assert "--apply" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["rebind", review.id, "--apply"])
    capsys.readouterr()
    main(["rebind", review.id, "--apply", "--reason", "wording only"])
    assert json.loads(capsys.readouterr().out)["state"] == "resolved"
