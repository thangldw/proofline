import json

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_why import DecisionWhyError, why
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ORIGINAL = "Decision: Use SQLite for the local queue.\nReason: no network service is permitted."


def _approved(session):
    source, _ = ingest_source(
        session, SourceCreate(title="adr", uri="file:///adr.md", content=ORIGINAL)
    )
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return source, decision


def test_why_ranks_decisions_and_reports_a_current_citation(session):
    _, decision = _approved(session)
    (answer,) = why(session, "Why do we use SQLite for the queue?")
    assert answer.decision_id == decision.id and answer.health == "current"
    assert "sqlite" in answer.matched_terms and "queue" in answer.matched_terms
    assert answer.quote.startswith("Decision:") and answer.rationale
    assert why(session, "kubernetes") == []
    assert "quote" not in answer.content_free_model_dump()


def test_why_flags_a_decision_whose_citation_no_longer_resolves(session):
    source, decision = _approved(session)
    ingest_source(
        session,
        SourceCreate(title="adr", uri=source.uri, content="Decision: Use NATS.\nReason: network."),
    )
    answers = {a.decision_id: a for a in why(session, "SQLite queue")}
    assert answers[decision.id].health in {"changed", "deleted", "moved", "ambiguous"}


def test_why_validates_input(session):
    for question in ("  ", "x" * 501):
        with pytest.raises(DecisionWhyError):
            why(session, question)
    with pytest.raises(DecisionWhyError):
        why(session, "sqlite", limit=0)


def test_cli_why_prints_a_cited_answer(session, monkeypatch, capsys):
    _, decision = _approved(session)
    monkeypatch.setattr(
        cli_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), expire_on_commit=False),
    )
    main(["why", "SQLite queue", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["answers"][0]["decision_id"] == decision.id
    main(["why", "SQLite queue"])
    assert "adr:1-2" in capsys.readouterr().out
    main(["why", "kubernetes"])
    assert "No approved decision" in capsys.readouterr().out
