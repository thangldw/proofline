import json

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_blame import DecisionBlameError, blame
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ORIGINAL = "Decision: Use SQLite for the local queue.\nReason: no network service is permitted."


def _approved(session, uri="file:///repo/docs/adr.md"):
    source, _ = ingest_source(session, SourceCreate(title="adr", uri=uri, content=ORIGINAL))
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return source, decision


def test_blame_finds_decision_by_path_suffix_and_line(session):
    _, decision = _approved(session)
    entries = blame(session, "docs/adr.md", 1)
    assert [entry.decision_id for entry in entries] == [decision.id]
    assert entries[0].state == "unchanged"
    assert blame(session, "adr", 1)[0].decision_id == decision.id
    assert blame(session, "docs/adr.md", 99) == []
    assert blame(session, "docs/other.md") == []


def test_blame_follows_a_shifted_citation_and_reports_deleted(session):
    source, decision = _approved(session)
    moved = "Preface line.\n\n" + ORIGINAL
    ingest_source(session, SourceCreate(title="adr", uri=source.uri, content=moved))
    entries = [e for e in blame(session, "docs/adr.md", 3) if e.decision_id == decision.id]
    assert entries and entries[0].state in {"unchanged", "moved"}
    assert entries[0].current_start_line == 3 and entries[0].cited_start_line == 1
    assert not [e for e in blame(session, "docs/adr.md", 1) if e.decision_id == decision.id]
    ingest_source(session, SourceCreate(title="adr", uri=source.uri, content="Unrelated text."))
    gone = [e for e in blame(session, "docs/adr.md") if e.decision_id == decision.id]
    assert gone and gone[0].state == "deleted" and gone[0].current_start_line is None


def test_blame_ignores_unapproved_decisions_and_rejects_bad_input(session):
    _, decision = _approved(session)
    decision.status = "rejected"
    session.commit()
    assert blame(session, "docs/adr.md") == []
    for target, line in (("  ", None), ("docs/adr.md", 0)):
        with pytest.raises(DecisionBlameError):
            blame(session, target, line)


def test_blame_does_not_treat_like_wildcards_as_patterns(session):
    _approved(session)
    assert blame(session, "%") == []
    assert blame(session, "docs/ad_.md") == []


def test_cli_blame_parses_file_colon_line(session, monkeypatch, capsys):
    _, decision = _approved(session)
    monkeypatch.setattr(
        cli_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), expire_on_commit=False),
    )
    main(["blame", "docs/adr.md:1", "--format", "json"])
    body = json.loads(capsys.readouterr().out)
    assert body["line"] == 1 and body["entries"][0]["decision_id"] == decision.id
    main(["blame", "docs/adr.md:99"])
    assert "No approved decision" in capsys.readouterr().out
    main(["blame", "docs/adr.md"])
    assert decision.title in capsys.readouterr().out
