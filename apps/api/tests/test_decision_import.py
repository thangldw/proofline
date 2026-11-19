import json

import pytest
from proofline.cli import main
from proofline.decision_import import AdrImportError, import_adrs, parse_adr
from proofline.ingestion import extract_decisions

NYGARD = """# 3. Use PostgreSQL

## Status

Accepted

## Context

We need a relational store with strong consistency.

## Decision

We will use PostgreSQL
for the primary database.

## Consequences

Operations must run backups.
"""

MADR = """---
status: "proposed"
---
# Use NATS for events

## Context and Problem Statement

Services need async messaging.

## Decision Outcome

Chosen option: NATS, because it is small.
"""


def test_parse_nygard_adr_maps_status_title_and_sections():
    adr = parse_adr(NYGARD, "0003-use-postgresql")
    assert adr.title == "Use PostgreSQL"
    assert adr.status == "accepted"
    assert adr.statement == "Use PostgreSQL: We will use PostgreSQL for the primary database."
    assert adr.rationale == "We need a relational store with strong consistency."


def test_parse_madr_front_matter_and_chosen_option():
    adr = parse_adr(MADR, "x")
    assert adr.status == "candidate"
    assert adr.statement == "Use NATS for events: NATS, because it is small."
    assert adr.rationale == "Services need async messaging."


def test_parse_rejects_adr_without_decision_section():
    with pytest.raises(AdrImportError) as caught:
        parse_adr("# Title\n\n## Context\n\nOnly context.\n", "x")
    assert caught.value.code == "no_decision_section"


def test_status_words_map_and_unknown_defaults_to_candidate():
    base = "# T\n\nStatus: {}\n\n## Decision\n\nDo it.\n"
    assert parse_adr(base.format("Superseded by ADR-9"), "t").status == "obsolete"
    assert parse_adr(base.format("**Rejected**"), "t").status == "rejected"
    assert parse_adr(base.format("who knows"), "t").status == "candidate"


def test_import_output_is_extractable_by_the_indexer(tmp_path):
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "0003.md").write_text(NYGARD)
    (adr_dir / "0004.md").write_text(MADR)
    (adr_dir / "notes.md").write_text("# Notes\n\nNo decision here.\n")
    result = import_adrs(adr_dir, tmp_path / "out")
    assert [item.output.name for item in result.imported] == ["0003.md", "0004.md"]
    assert [(item.source.name, item.reason) for item in result.skipped] == [
        ("notes.md", "no_decision_section")
    ]
    extracted = extract_decisions((tmp_path / "out" / "0003.md").read_text())
    assert len(extracted) == 1
    assert extracted[0]["status"] == "accepted"
    assert extracted[0]["rationale"] == "We need a relational store with strong consistency."
    assert "primary database" in extracted[0]["statement"]
    assert not list((tmp_path / "out").glob(".adr-*"))


def test_import_refuses_overwrite_and_same_directory(tmp_path):
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "a.md").write_text(NYGARD)
    import_adrs(adr_dir, tmp_path / "out")
    with pytest.raises(AdrImportError) as caught:
        import_adrs(adr_dir, tmp_path / "out")
    assert caught.value.code == "output_exists"
    assert import_adrs(adr_dir, tmp_path / "out", force=True).imported
    with pytest.raises(AdrImportError) as same:
        import_adrs(adr_dir, adr_dir, force=True)
    assert same.value.code == "output_is_input"
    with pytest.raises(AdrImportError) as missing:
        import_adrs(tmp_path / "nope", tmp_path / "o2")
    assert missing.value.code == "adr_dir_missing"


def test_cli_import_adr_reports_next_step(tmp_path, capsys):
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "a.md").write_text(NYGARD)
    main(["import-adr", str(adr_dir), "--output-dir", str(tmp_path / "out")])
    document = json.loads(capsys.readouterr().out)
    assert document["imported"][0]["status"] == "accepted"
    assert document["next_step"].startswith("proofline sync ")
    with pytest.raises(SystemExit) as caught:
        main(["import-adr", str(adr_dir), "--output-dir", str(tmp_path / "out")])
    assert caught.value.code == 2
