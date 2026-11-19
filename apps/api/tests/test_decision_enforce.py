import json

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_enforce import (
    EnforceError,
    check_enforcement,
    parse_rule,
    rules_in_quote,
)
from proofline.ingestion import extract_decisions, ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ADR = (
    "Decision: The core must stay offline.\n"
    "Reason: privacy.\n"
    'Enforce: forbid "import requests" in src/core/**/*.py\n'
    "Enforce: require file docs/offline.md\n"
    'Enforce: require "OFFLINE_MODE" in src/core/*.py\n'
)


def _approve(session, content=ADR, uri="file:///adr.md"):
    source, _ = ingest_source(session, SourceCreate(title="adr", uri=uri, content=content))
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return decision


def _tree(tmp_path, *, clean):
    core = tmp_path / "src" / "core"
    core.mkdir(parents=True)
    (core / "a.py").write_text("OFFLINE_MODE = True\n")
    (core / "b.py").write_text("import json\n" if clean else "x = 1\nimport requests\n")
    if clean:
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "offline.md").write_text("ok")
    return tmp_path


def test_enforce_lines_become_part_of_the_cited_quote():
    [extracted] = extract_decisions(ADR)
    assert extracted["quote"].count("Enforce:") == 3
    assert len(rules_in_quote(extracted["quote"])) == 3


def test_parse_rule_accepts_only_the_declarative_grammar():
    assert parse_rule('forbid "x" in src/**').kind == "forbid"
    assert parse_rule("require file a/b.md").kind == "require_file"
    for bad in (
        "run rm -rf /",
        'forbid "x" in /etc/*',
        'forbid "x" in ../secret/*',
        'forbid "" in src/*',
        "require file ../x",
        'forbid "x"',
    ):
        assert parse_rule(bad) is None, bad


def test_clean_tree_holds_and_violations_are_located(session, tmp_path):
    decision = _approve(session)
    assert check_enforcement(session, _tree(tmp_path / "ok", clean=True)) == []
    findings = check_enforcement(session, _tree(tmp_path / "bad", clean=False))
    assert {(f.problem, f.path, f.line) for f in findings} == {
        ("violated", "src/core/b.py", 2),
        ("missing", "docs/offline.md", None),
    }
    assert {f.decision_id for f in findings} == {decision.id}
    assert all("rule" not in f.content_free_model_dump() for f in findings)


def test_invalid_rules_and_unapproved_decisions(session, tmp_path):
    decision = _approve(session, "Decision: A.\nEnforce: delete everything\n")
    [finding] = check_enforcement(session, tmp_path)
    assert finding.problem == "rule_invalid" and finding.decision_id == decision.id
    decision.status = "candidate"
    session.commit()
    assert check_enforcement(session, tmp_path) == []
    with pytest.raises(EnforceError):
        check_enforcement(session, tmp_path / "missing")


def test_symlinks_and_skipped_directories_are_ignored(session, tmp_path):
    _approve(session, 'Decision: A.\nEnforce: forbid "secret" in **/*.txt\n')
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.txt").write_text("secret")
    (tmp_path / "real.txt").write_text("fine")
    (tmp_path / "link.txt").symlink_to(tmp_path / "node_modules" / "x.txt")
    assert check_enforcement(session, tmp_path) == []


def test_cli_check_enforcement(session, monkeypatch, tmp_path, capsys):
    _approve(session)
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    main(["check-enforcement", "--root", str(_tree(tmp_path / "ok", clean=True))])
    assert "hold" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "check-enforcement",
                "--root",
                str(_tree(tmp_path / "bad", clean=False)),
                "--format",
                "json",
            ]
        )
    assert caught.value.code == 1
    document = json.loads(capsys.readouterr().out)
    assert document["valid"] is False and len(document["findings"]) == 2
