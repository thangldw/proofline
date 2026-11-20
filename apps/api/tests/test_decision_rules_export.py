import json
import shutil
import subprocess

import proofline.cli as cli_module
import pytest
import yaml
from proofline.cli import main
from proofline.decision_rules_export import (
    ExportedRule,
    RulesExportError,
    collect_rules,
    pcre_literal,
    render_semgrep,
)
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ADR = (
    "Decision: Core stays offline.\n"
    'Enforce: forbid "import requests" in src/**/*.py\n'
    'Enforce: require "LICENSE" in README.md\n'
    "Enforce: require file docs/**\n"
    "Enforce: forbid nonsense\n"
)


def _approve(session, content=ADR):
    source, _ = ingest_source(
        session, SourceCreate(title="adr", uri="file:///r/adr.md", content=content)
    )
    for decision in session.scalars(select(Decision).where(Decision.source_id == source.id)):
        decision.status = "accepted"
    session.commit()


def test_only_forbid_rules_are_exported_and_the_rest_reported(session):
    _approve(session)
    exported, skipped = collect_rules(session)
    assert [(r.text, r.glob) for r in exported] == [("import requests", "src/**/*.py")]
    assert sorted(item.reason for item in skipped) == ["not_expressible", "not_expressible"] + [
        "rule_invalid"
    ] * (len(skipped) - 2)


def test_literal_escaping_cannot_become_regex_syntax():
    assert pcre_literal("a.b") == r"a\x2eb"
    assert pcre_literal("(x|y)*") == r"\x28x\x7cy\x29\x2a"
    assert pcre_literal("a b") == r"a\x20b"
    assert pcre_literal("naïve_1") == "naïve_1"


def test_rendered_yaml_parses_and_quotes_hostile_text():
    evil = 'x"\n  - id: injected\n    severity: INFO'
    document = yaml.safe_load(
        render_semgrep([ExportedRule("abcdef0123456789", 1, evil, 'src/"quote/**')])
    )
    [rule] = document["rules"]
    assert rule["id"] == "proofline-abcdef01-1" and rule["severity"] == "ERROR"
    assert rule["paths"]["include"] == ['src/"quote/**']
    assert "injected" not in rule["pattern-regex"] or "\\x" in rule["pattern-regex"]
    assert len(document["rules"]) == 1
    with pytest.raises(RulesExportError, match="no_exportable_rules"):
        render_semgrep([])


@pytest.mark.skipif(shutil.which("semgrep") is None, reason="semgrep not installed")
def test_exported_rules_are_enforced_by_real_semgrep(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "bad.py").write_text('import requests\nv = "(a) $b"\n')
    (tmp_path / "src" / "ok.py").write_text("import json\n")
    (tmp_path / "rules.yml").write_text(
        render_semgrep(
            [
                ExportedRule("abcdef0123456789", 1, "import requests", "src/**/*.py"),
                ExportedRule("abcdef0123456789", 2, '"(a) $b"', "src/**/*.py"),
            ]
        )
    )
    out = subprocess.run(
        ["semgrep", "--metrics=off", "--config", "rules.yml", "--json", "--quiet", "."],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    hits = {(r["check_id"], r["path"]) for r in json.loads(out.stdout)["results"]}
    assert hits == {
        ("proofline-abcdef01-1", "src/bad.py"),
        ("proofline-abcdef01-2", "src/bad.py"),
    }


def test_cli_prints_writes_reports_skips_and_fails_without_rules(
    session, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    with pytest.raises(SystemExit):
        main(["export-rules"])
    assert "no_exportable_rules" in capsys.readouterr().err
    _approve(session)
    main(["export-rules"])
    captured = capsys.readouterr()
    assert yaml.safe_load(captured.out)["rules"][0]["languages"] == ["generic"]
    assert "not_expressible" in captured.err and "rule_invalid" in captured.err
    target = tmp_path / "semgrep.yml"
    main(["export-rules", "--output", str(target)])
    assert yaml.safe_load(target.read_text())["rules"]
    with pytest.raises(SystemExit):
        main(["export-rules", "--output", str(tmp_path / "missing" / "x.yml")])
    assert "output_unwritable" in capsys.readouterr().err
