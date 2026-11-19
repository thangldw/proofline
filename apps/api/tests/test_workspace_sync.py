import json

import pytest
from proofline import cli
from proofline.models import Source
from proofline.workspace_sync import WorkspaceSyncError, discover_documents, sync_folder
from sqlalchemy import select


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_sync_is_idempotent_and_versions_changes(session, tmp_path):
    write(tmp_path / "docs" / "adr.md", "# ADR\n\nDecision: Use SQLite.\n")
    first = sync_folder(session, tmp_path, uri_root="file:///original/repo")
    again = sync_folder(session, tmp_path, uri_root="file:///original/repo")
    write(tmp_path / "docs" / "adr.md", "# ADR\n\nDecision: Use Postgres.\n")
    changed = sync_folder(session, tmp_path, uri_root="file:///original/repo")

    assert (first.created, again.unchanged, changed.updated) == (1, 1, 1)
    uris = session.scalars(select(Source.uri)).all()
    assert uris == ["file:///original/repo/docs/adr.md"]


def test_sync_skips_hidden_and_vendor_directories(tmp_path):
    write(tmp_path / "keep.md", "x")
    write(tmp_path / ".git" / "a.md", "x")
    write(tmp_path / "node_modules" / "b.md", "x")
    write(tmp_path / ".hidden.md", "x")

    assert [p.name for p in discover_documents(tmp_path)] == ["keep.md"]


def test_sync_rejects_invalid_uri_root_and_missing_folder(session, tmp_path):
    with pytest.raises(WorkspaceSyncError) as bad:
        sync_folder(session, tmp_path, uri_root="https://example.com/x")
    assert bad.value.code == "uri_root_invalid"
    with pytest.raises(WorkspaceSyncError) as missing:
        sync_folder(session, tmp_path / "nope")
    assert missing.value.code == "folder_unavailable"


def test_sync_reports_unreadable_files_as_failures(session, tmp_path):
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe\x00bad")
    summary = sync_folder(session, tmp_path)
    assert summary.failed == [{"path": "bad.md", "code": "file_encoding_invalid"}]


def test_cli_sync_prints_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PROOFLINE_HOME", str(tmp_path / "home"))
    write(tmp_path / "docs" / "a.md", "Decision: keep it simple.\n")
    from proofline import database

    monkeypatch.setattr(cli, "SessionLocal", database.SessionLocal)
    monkeypatch.setattr(
        "sys.argv", ["proofline", "sync", str(tmp_path / "docs"), "--format", "json"]
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["created"] == 1


def _run(args, home):
    import os
    import subprocess
    import sys

    env = {**os.environ, "PROOFLINE_HOME": str(home), "PROOFLINE_AI_PROVIDER": "disabled"}
    return subprocess.run(
        [sys.executable, "-m", "proofline.cli", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_pr_gate_flow_snapshot_sync_check(tmp_path):
    from proofline.database import make_engine
    from proofline.models import Decision
    from sqlalchemy.orm import sessionmaker

    docs = tmp_path / "docs"
    write(docs / "adr.md", "Decision: Use SQLite for the queue.\nReason: no network.\n")
    root = "file:///original/repo/docs"
    home_a, home_b = tmp_path / "a", tmp_path / "b"

    assert _run(["sync", str(docs), "--uri-root", root], home_a).returncode == 0
    engine = make_engine(f"sqlite:///{home_a / 'proofline.db'}")
    with sessionmaker(bind=engine)() as db:
        for decision in db.scalars(select(Decision)):
            decision.status = "accepted"
        db.commit()
    engine.dispose()
    snapshot = tmp_path / "decisions.json"
    assert _run(["export", "--output", str(snapshot)], home_a).returncode == 0

    assert _run(["import", str(snapshot)], home_b).returncode == 0
    assert _run(["sync", str(docs), "--uri-root", root], home_b).returncode == 0
    assert _run(["check-decisions"], home_b).returncode == 0

    write(docs / "adr.md", "Decision: Use NATS for the queue.\nReason: network allowed.\n")
    assert _run(["sync", str(docs), "--uri-root", root], home_b).returncode == 0
    checked = _run(["check-decisions"], home_b)
    assert checked.returncode == 1
    assert "requires review" in checked.stdout
