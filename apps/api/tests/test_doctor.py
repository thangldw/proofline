import json
from datetime import timedelta

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_trend import record_all_snapshots
from proofline.doctor import run_doctor
from proofline.models import DecisionHealthSnapshot, utc_now
from sqlalchemy.orm import sessionmaker


def _by_name(checks):
    return {item.name: item for item in checks}


def test_doctor_reports_each_area(session, tmp_path):
    engine = session.get_bind()
    first = _by_name(run_doctor(engine, session))
    assert first["migrations"].status == "ok" and first["integrity"].status == "ok"
    assert first["snapshots"].status == "warn"
    record_all_snapshots(session)
    session.commit()
    assert _by_name(run_doctor(engine, session))["snapshots"].status == "ok"
    for row in session.query(DecisionHealthSnapshot).all():
        row.taken_at = utc_now() - timedelta(days=30)
    session.commit()
    assert _by_name(run_doctor(engine, session))["snapshots"].status == "warn"
    good = tmp_path / "p.toml"
    good.write_text('version = 1\n[decision_health]\nfail_on = ["changed"]\n')
    bad = tmp_path / "bad.toml"
    bad.write_text("version = 2\n")
    assert _by_name(run_doctor(engine, session, policy_path=good))["policy"].status == "ok"
    assert _by_name(run_doctor(engine, session, policy_path=bad))["policy"].status == "fail"


def test_doctor_flags_an_unmigrated_database(session):
    session.execute(
        __import__("sqlalchemy").text("DELETE FROM schema_migrations WHERE version = 24")
    )
    session.commit()
    checks = _by_name(run_doctor(session.get_bind(), session))
    assert checks["migrations"].status == "fail"


def test_cli_doctor_exits_non_zero_on_a_failed_check(session, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        cli_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), expire_on_commit=False),
    )
    monkeypatch.setattr(cli_module, "engine", session.get_bind())
    main(["doctor", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["ok"] is True
    bad = tmp_path / "bad.toml"
    bad.write_text("version = 2\n")
    with pytest.raises(SystemExit) as caught:
        main(["doctor", "--policy", str(bad)])
    assert caught.value.code == 1 and "[fail]" in capsys.readouterr().out
