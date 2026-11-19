import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_ledger import (
    LedgerError,
    append_entry,
    compare_with_base,
    ledger_at_ref,
    parse_ledger,
    read_ledger,
    render_comparison,
)
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ORIGINAL = "Decision: Use SQLite for the queue.\nReason: local.\n"
CHANGED = "Decision: Use NATS for the queue.\nReason: scale.\n"


def _put(session, content):
    return ingest_source(session, SourceCreate(title="a", uri="file:///a.md", content=content))[0]


def _approve(session):
    source = _put(session, ORIGINAL)
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    decision.status = "accepted"
    session.commit()
    return decision


def _stamp(day):
    return datetime(2026, 1, day, 12, tzinfo=UTC)


def test_append_builds_a_verifiable_chain_without_any_content(session, tmp_path):
    decision = _approve(session)
    path = tmp_path / "l" / "ledger.jsonl"
    first = append_entry(session, path, taken_at=_stamp(1))
    _put(session, CHANGED)
    second = append_entry(session, path, taken_at=_stamp(2))
    assert first.prev == "" and second.prev == first.hash and second.stale_ids == [decision.id]
    text = path.read_text()
    assert "SQLite" not in text and "queue" not in text
    entries = read_ledger(path)
    assert [e.findings for e in entries] == [0, 1] and entries[1].stale_percent >= 50


def test_any_tampering_breaks_verification(session, tmp_path):
    _approve(session)
    path = tmp_path / "ledger.jsonl"
    for day in (1, 2, 3):
        append_entry(session, path, taken_at=_stamp(day))
    lines = path.read_text().splitlines()
    assert len(parse_ledger("\n".join(lines))) == 3
    edited = lines[1].replace('"approved":1', '"approved":9')
    cases = {
        "edited": [lines[0], edited, lines[2]],
        "deleted": [lines[0], lines[2]],
        "reordered": [lines[1], lines[0], lines[2]],
        "garbage": [lines[0], "not json"],
        "version": [lines[0].replace('"v":1', '"v":2')],
    }
    for content in cases.values():
        with pytest.raises(LedgerError):
            parse_ledger("\n".join(content))
    with pytest.raises(LedgerError):
        path.write_text("\n".join(cases["edited"]) + "\n")
        append_entry(session, path)


def test_compare_reports_newly_stale_and_recovered_against_a_git_ref(session, tmp_path):
    decision = _approve(session)

    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    ledger = tmp_path / ".proofline" / "ledger.jsonl"
    append_entry(session, ledger, taken_at=_stamp(1))
    git("add", ".")
    git("commit", "-q", "-m", "ledger")
    git("checkout", "-q", "-b", "topic")
    _put(session, CHANGED)

    base = ledger_at_ref(tmp_path, "main", ledger.relative_to(tmp_path))
    result = compare_with_base(session, base)
    assert result.newly_stale == [decision.id] and result.recovered == []
    text = render_comparison(result)
    assert "0/1 (0.0%) -> 1/2 (50.0%), up" in text and decision.id[:8] in text

    stale_base = ledger_at_ref(tmp_path, "main", ledger.relative_to(tmp_path))
    _put(session, ORIGINAL)
    recovered = compare_with_base(session, stale_base)
    # the original decision is healthy again; the one extracted from the reverted text is stale
    assert decision.id not in recovered.newly_stale and recovered.findings == 1
    assert ledger_at_ref(tmp_path, "main", Path("nope.jsonl")) == []
    assert "nothing to compare" in render_comparison(compare_with_base(session, []))
    with pytest.raises(LedgerError):
        ledger_at_ref(tmp_path, "--output=x", ledger)


def test_cli_ledger(session, monkeypatch, tmp_path, capsys):
    _approve(session)
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    path = tmp_path / "ledger.jsonl"
    main(["ledger", "append", "--file", str(path)])
    assert json.loads(capsys.readouterr().out)["approved"] == 1
    main(["ledger", "verify", "--file", str(path)])
    assert json.loads(capsys.readouterr().out) == {"entries": 1, "valid": True}
    path.write_text(path.read_text().replace('"approved":1', '"approved":2'))
    with pytest.raises(SystemExit) as caught:
        main(["ledger", "verify", "--file", str(path)])
    assert caught.value.code == 2
