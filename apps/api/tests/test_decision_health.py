import json
import os
import subprocess
from pathlib import Path

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_health import DecisionHealthError, check_decision_health
from proofline.evidence_packages import EvidencePackageError
from proofline.ingestion import ingest_source
from proofline.models import Decision, Evidence, SourceVersion
from proofline.schemas import SourceCreate
from proofline.stale_decision_demo import run_stale_decision_demo
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

ORIGINAL = "Decision: Use SQLite for the local queue.\nReason: no network service is permitted."
ROOT = Path(__file__).resolve().parents[3]
PROOFLINE = ROOT / ".venv/bin/proofline"


def _approved_decision(session):
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
    return source, decision


def _provenance_counts(session):
    return tuple(
        session.scalar(select(func.count()).select_from(model))
        for model in (SourceVersion, Decision, Evidence)
    )


def test_health_check_flags_changed_exact_citation_with_provenance(session):
    source, decision = _approved_decision(session)
    cited_version_id = decision.source_version_id
    ingest_source(
        session,
        SourceCreate(
            title="requirement.md",
            uri=source.uri,
            content=(
                "Decision: Use NATS for the local queue.\n"
                "Reason: a managed network service is now permitted."
            ),
        ),
    )

    findings = check_decision_health(session)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.decision_id == decision.id
    assert finding.cited_source_version_id == cited_version_id
    assert finding.current_source_version_id == source.current_version_id
    assert finding.locator == "requirement.md:1-2"
    assert finding.cited_content_sha256 != finding.current_content_sha256


def test_health_check_allows_unrelated_revision_when_exact_citation_still_resolves(session):
    source, _decision = _approved_decision(session)
    ingest_source(
        session,
        SourceCreate(
            title="requirement.md",
            uri=source.uri,
            content=ORIGINAL + "\n\nUnrelated appendix: owner is Platform.",
        ),
    )

    assert check_decision_health(session) == []


def test_health_check_fails_closed_on_corrupt_citation(session):
    _source, decision = _approved_decision(session)
    decision.evidence[0].quote_hash = "0" * 64
    session.commit()

    with pytest.raises(DecisionHealthError, match="citation_provenance_invalid"):
        check_decision_health(session)


def test_check_decisions_cli_is_read_only_and_returns_ci_failure(session, monkeypatch, capsys):
    source, _decision = _approved_decision(session)
    ingest_source(
        session,
        SourceCreate(title="requirement.md", uri=source.uri, content="Requirement replaced."),
    )
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    before = _provenance_counts(session)

    with pytest.raises(SystemExit) as raised:
        main(["check-decisions"])

    assert raised.value.code == 1
    assert capsys.readouterr().out.splitlines() == [
        "Decision requires review",
        "requirement.md:1-2 changed after this decision was approved.",
    ]
    assert _provenance_counts(session) == before


def test_check_decisions_cli_reports_unavailable_database_without_details(monkeypatch):
    def unavailable():
        raise OperationalError("private query", {}, RuntimeError("private database detail"))

    monkeypatch.setattr(cli_module, "SessionLocal", unavailable)

    with pytest.raises(SystemExit, match="decision check failed: database_unavailable") as raised:
        main(["check-decisions"])

    assert "private" not in str(raised.value)


def test_check_decisions_entrypoint_does_not_create_missing_state_directory(tmp_path):
    home = tmp_path / "missing-state"
    environment = {**os.environ, "PROOFLINE_HOME": str(home)}
    environment.pop("PROOFLINE_DATABASE_URL", None)

    result = subprocess.run(
        [PROOFLINE, "check-decisions"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert result.stderr.strip() == "decision check failed: database_unavailable"
    assert not home.exists()


def test_check_decisions_entrypoint_preserves_database_bytes_and_mtime(tmp_path):
    home = tmp_path / "state with space"
    environment = {**os.environ, "PROOFLINE_HOME": str(home)}
    environment.pop("PROOFLINE_DATABASE_URL", None)
    seeded = subprocess.run(
        [PROOFLINE, "seed"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert seeded.returncode == 0, seeded.stderr
    database = home / "proofline.db"
    before_bytes = database.read_bytes()
    before_mtime = database.stat().st_mtime_ns
    before_entries = sorted(path.name for path in home.iterdir())

    checked = subprocess.run(
        [PROOFLINE, "check-decisions"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert checked.returncode == 0, checked.stderr
    assert checked.stdout.strip() == "All approved decision citations resolve in current sources."
    assert database.read_bytes() == before_bytes
    assert database.stat().st_mtime_ns == before_mtime
    assert sorted(path.name for path in home.iterdir()) == before_entries


def test_stale_decision_demo_creates_offline_package_html_and_receipt(tmp_path):
    output = tmp_path / "demo"

    result = run_stale_decision_demo(output)

    assert result["verification"]["valid"] is True
    assert result["finding"].locator == "requirement.md:42-48"
    assert (output / "evidence.zip").is_file()
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "Decision requires review" in html
    assert "requirement.md:42-48 changed" in html
    assert "proofline verify-package evidence.zip" in html
    receipt = json.loads((output / "decision-health.json").read_text(encoding="utf-8"))
    assert receipt["package_root"] == result["verification"]["root_hash"]

    with pytest.raises(EvidencePackageError, match="output_exists"):
        run_stale_decision_demo(output)

    replacement = run_stale_decision_demo(output, force=True)
    assert replacement["verification"]["valid"] is True

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("user data", encoding="utf-8")
    with pytest.raises(EvidencePackageError, match="output_directory_not_demo"):
        run_stale_decision_demo(unrelated, force=True)
    assert (unrelated / "keep.txt").read_text(encoding="utf-8") == "user data"
