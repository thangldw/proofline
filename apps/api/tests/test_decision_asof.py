import json
from datetime import datetime

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_asof import AsOfError, decisions_as_of, parse_as_of
from proofline.ingestion import ingest_source
from proofline.models import AuditEvent, Decision, SourceVersion
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ORIGINAL = "Decision: Use SQLite for the queue.\nReason: local.\n"
CHANGED = "Decision: Use NATS for the queue.\nReason: scale.\n"


def d(text):
    return datetime.fromisoformat(text)


def _timeline(session):
    """v1 on 01-01 (candidate), approved 01-02, v2 on 01-10, reverted 01-20, obsolete 02-01."""

    def put(content):
        return ingest_source(
            session, SourceCreate(title="adr", uri="file:///a.md", content=content)
        )[0]

    source = put(ORIGINAL)
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    first = session.scalar(select(SourceVersion).where(SourceVersion.source_id == source.id))
    put(CHANGED)
    second = session.scalars(
        select(SourceVersion)
        .where(SourceVersion.source_id == source.id)
        .order_by(SourceVersion.version_number)
    ).all()[1]
    put(ORIGINAL)
    restore = session.scalar(
        select(AuditEvent).where(AuditEvent.action == "source.version_restored")
    )
    assert restore is not None and restore.after_json["version_id"] == first.id
    decision.status = "obsolete"
    decision.created_at = d("2026-01-01T09:00:00")
    first.created_at = d("2026-01-01T09:00:00")
    second.created_at = d("2026-01-10T09:00:00")
    restore.created_at = d("2026-01-20T09:00:00")
    session.add_all(
        [
            AuditEvent(
                object_type="decision",
                object_id=decision.id,
                action="decision.updated",
                before_json={"status": "candidate"},
                after_json={"status": "accepted"},
                created_at=d("2026-01-02T09:00:00"),
            ),
            AuditEvent(
                object_type="decision",
                object_id=decision.id,
                action="decision.updated",
                before_json={"status": "accepted"},
                after_json={"status": "obsolete"},
                created_at=d("2026-02-01T09:00:00"),
            ),
        ]
    )
    session.commit()
    return decision


def test_parse_as_of_forms_and_errors():
    assert parse_as_of("2026-01-05") == d("2026-01-05T23:59:59.999999")
    assert parse_as_of("2026-01-05T10:00:00+02:00") == d("2026-01-05T08:00:00")
    assert parse_as_of("2026-01-05T10:00:00") == d("2026-01-05T10:00:00")
    with pytest.raises(AsOfError):
        parse_as_of("yesterday")


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        ("2025-12-31", None),
        ("2026-01-01", None),
        ("2026-01-05", "current"),
        ("2026-01-15", "changed"),
        ("2026-01-25", "current"),
        ("2026-02-05", None),
    ],
)
def test_decision_history_is_reconstructed_from_versions_and_audit(session, moment, expected):
    decision = _timeline(session)
    answers = decisions_as_of(session, parse_as_of(moment))
    if expected is None:
        assert answers == []
    else:
        [answer] = answers
        assert answer.decision_id == decision.id and answer.health == expected


def test_question_filter_and_content_free_dump(session):
    _timeline(session)
    moment = parse_as_of("2026-01-05")
    assert len(decisions_as_of(session, moment, question="sqlite")) == 1
    assert decisions_as_of(session, moment, question="kubernetes") == []
    with pytest.raises(AsOfError):
        decisions_as_of(session, moment, question="   ")
    [answer] = decisions_as_of(session, moment)
    assert "decision_title" not in answer.content_free_model_dump()


def test_cli_asof(session, monkeypatch, capsys):
    decision = _timeline(session)
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    main(["asof", "2026-01-15"])
    assert "WARNING: citation changed" in capsys.readouterr().out
    main(["asof", "2026-01-05", "--format", "json", "--no-titles"])
    document = json.loads(capsys.readouterr().out)
    assert document["decisions"][0]["decision_id"] == decision.id
    assert "decision_title" not in document["decisions"][0]
    main(["asof", "2025-12-31"])
    assert "none" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        main(["asof", "nonsense"])
    assert caught.value.code == 2
