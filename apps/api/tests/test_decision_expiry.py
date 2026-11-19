import json
from datetime import date

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_expiry import check_expiry, review_by_date
from proofline.ingestion import extract_memories, ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

TEXT = "Decision: Use SQLite.\nReason: local.\nReview by: 2027-03-01"


def _approved(session, content=TEXT):
    source, _ = ingest_source(
        session, SourceCreate(title="adr", uri="file:///adr.md", content=content)
    )
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return decision


def test_review_by_line_is_part_of_the_extracted_quote():
    (item,) = extract_memories(TEXT)
    assert item["quote"].endswith("Review by: 2027-03-01")
    assert item["rationale"] == "local."
    assert review_by_date(item["quote"]) == date(2027, 3, 1)


def test_review_by_date_ignores_invalid_dates_and_picks_the_earliest():
    assert review_by_date("Review by: 2027-13-40") is None
    assert review_by_date("nothing here") is None
    assert review_by_date("Review by: 2027-05-01\nreview by: 2027-02-01") == date(2027, 2, 1)


def test_check_expiry_reports_overdue_and_due_soon(session):
    decision = _approved(session)
    assert check_expiry(session, as_of=date(2027, 2, 1)) == []
    soon = check_expiry(session, as_of=date(2027, 2, 20), warn_within_days=30)
    assert [(f.decision_id, f.state) for f in soon] == [(decision.id, "due_soon")]
    late = check_expiry(session, as_of=date(2027, 3, 11))
    assert late[0].state == "overdue" and late[0].days_overdue == 10
    assert "decision_title" not in late[0].content_free_model_dump()
    with pytest.raises(ValueError):
        check_expiry(session, as_of=date(2027, 1, 1), warn_within_days=-1)


def test_check_expiry_skips_unapproved_decisions(session):
    decision = _approved(session)
    decision.status = "rejected"
    session.commit()
    assert check_expiry(session, as_of=date(2030, 1, 1)) == []


def test_cli_check_expiry_exits_non_zero_when_overdue(session, monkeypatch, capsys):
    _approved(session)
    monkeypatch.setattr(
        cli_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), expire_on_commit=False),
    )
    main(["check-expiry", "--as-of", "2027-01-01", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["valid"] is True
    with pytest.raises(SystemExit) as caught:
        main(["check-expiry", "--as-of", "2027-04-01"])
    assert caught.value.code == 1
    assert "overdue" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["check-expiry", "--as-of", "nope"])
