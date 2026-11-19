import os

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_watch import folder_fingerprint, watch_folder
from proofline.models import Decision
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _factory(session):
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False)


def test_fingerprint_changes_on_edit_and_ignores_hidden_and_unsupported(tmp_path):
    (tmp_path / "a.md").write_text("one")
    (tmp_path / ".hidden.md").write_text("x")
    (tmp_path / "b.bin").write_text("x")
    first = folder_fingerprint(tmp_path)
    assert {item[0] for item in first} == {"a.md"}
    (tmp_path / "a.md").write_text("two!")
    assert folder_fingerprint(tmp_path) != first


def test_watch_reports_stale_then_recovered_and_syncs_only_on_change(session, tmp_path):
    doc = tmp_path / "adr.md"
    doc.write_text("Decision: Use SQLite for the queue.\nReason: local.\n")
    factory = _factory(session)
    lines: list[str] = []
    steps = iter(["approve", "edit", "restore", "noop"])

    def sleep(_seconds):
        step = next(steps)
        if step == "approve":
            with factory() as other:
                for decision in other.scalars(select(Decision)):
                    decision.status = "accepted"
                other.commit()
            doc.write_text(doc.read_text())
            os.utime(doc, ns=(1, 2_000_000_000))
        elif step == "edit":
            doc.write_text("Decision: Use NATS now.\nReason: scale.\n\nOther text.\n")
        elif step == "restore":
            doc.write_text("Decision: Use SQLite for the queue.\nReason: local.\n")

    syncs = watch_folder(
        factory, tmp_path, interval=0, max_cycles=5, sleep=sleep, emit=lines.append
    )
    assert syncs == 4
    assert any(line.startswith("STALE (") for line in lines)
    assert any(line.startswith("recovered (") for line in lines), lines
    assert lines[0].startswith("synced: 1 created")


def test_watch_with_no_changes_syncs_once(session, tmp_path):
    (tmp_path / "a.md").write_text("Decision: Use X.\n")
    lines: list[str] = []
    assert (
        watch_folder(
            _factory(session),
            tmp_path,
            interval=0,
            max_cycles=3,
            sleep=lambda _: None,
            emit=lines.append,
        )
        == 1
    )
    assert len(lines) == 1


def test_cli_watch_validates_interval_and_runs_bounded(session, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "SessionLocal", _factory(session))
    monkeypatch.setattr(cli_module, "initialize_database", lambda *a, **k: None)
    (tmp_path / "a.md").write_text("Decision: Use X.\n")
    main(["watch", str(tmp_path), "--interval", "0.01", "--max-cycles", "2"])
    assert "synced: 1 created" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        main(["watch", str(tmp_path), "--interval", "0"])
    assert caught.value.code == 2
    with pytest.raises(SystemExit):
        main(["watch", str(tmp_path / "missing"), "--max-cycles", "1"])
