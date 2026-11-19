import json
from datetime import date

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_report import build_report, render_report_html, render_report_markdown
from proofline.decision_trend import record_snapshot
from proofline.ingestion import ingest_source
from proofline.models import Decision, Workspace
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _approve(session, title, content, uri):
    source, _ = ingest_source(session, SourceCreate(title=title, uri=uri, content=content))
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return source, decision


def _seed(session):
    _approve(
        session, "a", "Decision: Use SQLite for the queue.\nReview by: 2020-01-01", "file:///1.md"
    )
    _approve(session, "b", "Decision: Use NATS for the queue.", "file:///2.md")
    for workspace in session.scalars(select(Workspace)):
        record_snapshot(session, workspace.id)
    record_snapshot(session, session.scalar(select(Workspace.id)))
    session.commit()


def test_report_lists_due_reviews_conflicts_and_trend(session):
    _seed(session)
    report = build_report(session, as_of=date(2026, 1, 1), min_similarity=0.3)
    assert [e.state for e in report.expiring] == ["overdue"]
    assert len(report.conflicts) == 1 and len(report.points) == 2
    markdown = render_report_markdown(report)
    assert "Use SQLite for the queue" in markdown and "overdue" in markdown
    html = render_report_html(report)
    assert html.startswith("<!doctype html>") and "<svg" in html
    assert "http://" not in html and "https://" not in html


def test_report_escapes_markup_in_titles(session):
    _approve(session, "<script>alert(1)</script>", "Decision: <b>x</b> y z.", "file:///x.md")
    html = render_report_html(build_report(session, as_of=date(2026, 1, 1)))
    assert "<script>alert" not in html


def test_no_titles_withholds_text(session):
    _seed(session)
    report = build_report(session, as_of=date(2026, 1, 1), include_titles=False, min_similarity=0.3)
    for text in (render_report_markdown(report), render_report_html(report)):
        assert "SQLite" not in text and "NATS" not in text and "title withheld" in text


def test_cli_report_writes_file_or_prints(session, monkeypatch, tmp_path, capsys):
    _seed(session)
    monkeypatch.setattr(
        cli_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), expire_on_commit=False),
    )
    out = tmp_path / "report.html"
    main(["report", "--output", str(out), "--as-of", "2026-01-01"])
    assert json.loads(capsys.readouterr().out)["format"] == "html"
    assert "Decision health report" in out.read_text()
    main(["report", "--format", "markdown", "--as-of", "2026-01-01", "--no-titles"])
    assert "# Decision health report (2026-01-01)" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        main(["report", "--as-of", "nope"])
    assert caught.value.code == 2
