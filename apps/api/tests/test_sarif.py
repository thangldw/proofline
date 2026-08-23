import json

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_health import check_decision_health
from proofline.decision_policy import DecisionHealthPolicy, policy_sha256
from proofline.ingestion import ingest_source
from proofline.models import Decision, DecisionReview
from proofline.sarif import build_decision_health_sarif
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ORIGINAL = "Decision: Use SQLite.\nReason: local durability."
CHANGED = "Decision: Use NATS.\nReason: shared workload."


def _finding(session):
    source, _created = ingest_source(
        session,
        SourceCreate(title="requirement.md", uri="file:///requirement.md", content=ORIGINAL),
    )
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    assert decision is not None
    decision.status = "accepted"
    session.commit()
    ingest_source(
        session,
        SourceCreate(title="requirement.md", uri=source.uri, content=CHANGED),
    )
    findings = check_decision_health(session)
    assert len(findings) == 1
    return findings[0]


def test_sarif_is_deterministic_content_free_and_uses_exact_region(session):
    finding = _finding(session)
    policy = DecisionHealthPolicy()

    first = build_decision_health_sarif([finding], policy)
    second = build_decision_health_sarif([finding], policy)

    assert first == second
    assert first["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
    assert first["version"] == "2.1.0"
    run = first["runs"][0]
    assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == [
        "proofline/ambiguous",
        "proofline/changed",
        "proofline/deleted",
        "proofline/moved",
    ]
    assert run["properties"]["policySha256"] == policy_sha256(policy)
    result = run["results"][0]
    assert result["ruleId"] == "proofline/changed"
    assert result["level"] == "warning"
    assert len(result["partialFingerprints"]["prooflineFinding/v1"]) == 64
    location = result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "file:///requirement.md"
    assert location["region"]["startLine"] >= 1
    assert location["region"]["endLine"] >= location["region"]["startLine"]
    serialized = json.dumps(first, sort_keys=True)
    assert "SQLite" not in serialized
    assert "NATS" not in serialized
    assert "snippet" not in serialized


def test_check_decisions_writes_sarif_atomically_and_refuses_overwrite(
    session, monkeypatch, tmp_path, capsys
):
    _finding(session)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    output = tmp_path / "decision-health.sarif"

    with pytest.raises(SystemExit) as blocked:
        main(["check-decisions", "--format", "sarif", "--output", str(output)])

    assert blocked.value.code == 1
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["version"] == "2.1.0"
    assert capsys.readouterr().out == ""
    with pytest.raises(SystemExit) as invalid:
        main(["check-decisions", "--format", "sarif", "--output", str(output)])
    assert invalid.value.code == 2
    assert capsys.readouterr().err.strip() == "decision check failed: output_exists"


def test_policy_is_loaded_before_database_and_controls_exit_code(monkeypatch, tmp_path, capsys):
    invalid_policy = tmp_path / "invalid.toml"
    invalid_policy.write_text("version = 99\n", encoding="utf-8")

    def database_must_not_open():
        raise AssertionError("database opened before policy validation")

    monkeypatch.setattr(cli_module, "SessionLocal", database_must_not_open)
    with pytest.raises(SystemExit) as invalid:
        main(["check-decisions", "--policy", str(invalid_policy)])

    assert invalid.value.code == 2
    assert capsys.readouterr().err.strip() == "decision check failed: policy_version_unsupported"


def test_nonblocking_policy_returns_zero_but_preserves_finding(
    session, monkeypatch, tmp_path, capsys
):
    _finding(session)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    policy = tmp_path / "proofline.toml"
    policy.write_text(
        'version = 1\n[decision_health]\nfail_on = ["deleted"]\n',
        encoding="utf-8",
    )

    main(["check-decisions", "--format", "json", "--policy", str(policy)])

    document = json.loads(capsys.readouterr().out)
    assert document["valid"] is True
    assert document["finding_count"] == 1
    assert document["blocking_count"] == 0


def test_refresh_reviews_persists_content_free_summary(session, monkeypatch, capsys):
    _finding(session)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    monkeypatch.setattr(cli_module, "engine", session.get_bind())

    main(["refresh-reviews"])

    document = json.loads(capsys.readouterr().out)
    assert document["valid"] is True
    assert document["opened"] == 1
    assert "quote" not in document
    assert session.scalar(select(DecisionReview)) is not None
