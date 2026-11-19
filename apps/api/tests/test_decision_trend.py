import json

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_trend import record_all_snapshots, render_markdown, trend
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _approved(session):
    source, _ = ingest_source(
        session,
        SourceCreate(title="adr", uri="file:///a.md", content="Decision: Use SQLite.\nReason: x."),
    )
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return source


def test_snapshots_record_counts_and_show_a_trend(session):
    source = _approved(session)
    record_all_snapshots(session)
    ingest_source(
        session,
        SourceCreate(title="adr", uri=source.uri, content="Decision: Use NATS.\nReason: net."),
    )
    record_all_snapshots(session)
    session.commit()
    points = trend(session)
    assert [p.findings for p in points] == [0, 1]
    assert points[1].approved == 2 and points[1].stale_percent == 50.0
    assert points[1].changed + points[1].deleted + points[1].moved == 1
    markdown = render_markdown(points)
    assert markdown.count("\n") == 4 and "Stale %" in markdown
    assert len(trend(session, limit=1)) == 1
    with pytest.raises(ValueError):
        trend(session, limit=0)


def test_cli_snapshot_and_trend(session, monkeypatch, capsys):
    _approved(session)
    monkeypatch.setattr(
        cli_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), expire_on_commit=False),
    )
    monkeypatch.setattr(cli_module, "engine", session.get_bind())
    main(["health-trend"])
    assert "No snapshots yet" in capsys.readouterr().out
    main(["snapshot-health"])
    assert json.loads(capsys.readouterr().out)["snapshots"]
    main(["health-trend", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["points"][0]["approved"] == 1
    main(["health-trend"])
    assert "0/1" in capsys.readouterr().out
    main(["health-trend", "--format", "markdown"])
    assert "| Taken at |" in capsys.readouterr().out
