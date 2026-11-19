import json

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_code_refs import CodeRefError, check_code_refs, scan_code_refs
from proofline.decision_conflicts import find_conflict_candidates
from proofline.decision_export import DecisionExportError, export_adrs, slugify
from proofline.ingestion import ingest_source
from proofline.models import Decision, DecisionRelation
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _approve(session, title, content, uri):
    source, _ = ingest_source(session, SourceCreate(title=title, uri=uri, content=content))
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return source, decision


def _patch(session, monkeypatch):
    monkeypatch.setattr(
        cli_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), expire_on_commit=False),
    )


def test_export_adr_writes_one_file_per_approved_decision(session, tmp_path):
    _, decision = _approve(
        session, "adr", "Decision: Use SQLite / local!\nReason: no network.", "file:///a.md"
    )
    exported = export_adrs(session, tmp_path / "out")
    assert [item.decision_id for item in exported] == [decision.id]
    path = exported[0].path
    assert path.name == "0001-use-sqlite-local.md"
    text = path.read_text()
    assert "* Status: accepted" in text and "Citation health: current" in text
    assert "> Decision: Use SQLite" in text and "no network." in text
    with pytest.raises(DecisionExportError):
        export_adrs(session, tmp_path / "out")
    assert export_adrs(session, tmp_path / "out", force=True)
    assert not list((tmp_path / "out").glob(".adr-*"))
    assert slugify("../../etc/passwd") == "etc-passwd" and slugify("!!!") == "decision"


def test_code_refs_flag_missing_stale_and_unapproved(session, tmp_path):
    source, decision = _approve(
        session, "adr", "Decision: Use SQLite.\nReason: local.", "file:///a.md"
    )
    code = tmp_path / "src"
    code.mkdir()
    (code / "a.py").write_text(
        f"# proofline-decision: {decision.id}\n# proofline-decision: deadbeef00\n"
    )
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("// proofline-decision: deadbeef11")
    refs = scan_code_refs([tmp_path])
    assert [(r.line, r.reference[:8]) for r in refs] == [(1, decision.id[:8]), (2, "deadbeef")]
    assert [f.problem for f in check_code_refs(session, refs)] == ["missing"]
    ingest_source(
        session,
        SourceCreate(title="adr", uri=source.uri, content="Decision: Use NATS.\nReason: net."),
    )
    problems = [f.problem for f in check_code_refs(session, refs)]
    assert problems[0].startswith("stale:") and problems[1] == "missing"
    short = scan_code_refs([code / "a.py"])
    assert check_code_refs(session, short[:1])[0].decision_id == decision.id
    decision.status = "rejected"
    session.commit()
    assert check_code_refs(session, short[:1])[0].problem == "not_approved:rejected"
    with pytest.raises(CodeRefError):
        scan_code_refs([tmp_path / "missing"])


def test_conflict_candidates_skip_related_and_identical_pairs(session):
    _, one = _approve(session, "a", "Decision: Use SQLite for the local queue.", "file:///1.md")
    _, two = _approve(session, "b", "Decision: Use NATS for the local queue.", "file:///2.md")
    found = find_conflict_candidates(session, min_similarity=0.4)
    assert {(c.first_id, c.second_id) for c in found} == {tuple(sorted((one.id, two.id)))}
    assert "local" in found[0].shared_terms
    assert find_conflict_candidates(session, min_similarity=0.99) == []
    session.add(
        DecisionRelation(source_decision_id=one.id, target_decision_id=two.id, kind="supersedes")
    )
    session.commit()
    assert find_conflict_candidates(session, min_similarity=0.4) == []
    with pytest.raises(ValueError):
        find_conflict_candidates(session, min_similarity=0)


def test_cli_exports_checks_refs_and_finds_conflicts(session, monkeypatch, tmp_path, capsys):
    _, one = _approve(session, "a", "Decision: Use SQLite for the queue.", "file:///1.md")
    _approve(session, "b", "Decision: Use NATS for the queue.", "file:///2.md")
    _patch(session, monkeypatch)
    main(["export-adr", "--output-dir", str(tmp_path / "adr")])
    assert json.loads(capsys.readouterr().out)["exported"] == 2
    (tmp_path / "x.py").write_text(f"# proofline-decision: {one.id}\n")
    main(["check-code-refs", str(tmp_path / "x.py"), "--format", "json"])
    assert json.loads(capsys.readouterr().out)["valid"] is True
    (tmp_path / "y.py").write_text("# proofline-decision: 00000000\n")
    with pytest.raises(SystemExit) as caught:
        main(["check-code-refs", str(tmp_path / "y.py")])
    assert caught.value.code == 1 and "missing" in capsys.readouterr().out
    main(["find-conflicts", "--min-similarity", "0.3", "--format", "json"])
    assert len(json.loads(capsys.readouterr().out)["candidates"]) == 1
    main(["find-conflicts", "--min-similarity", "0.99"])
    assert "No conflict candidates." in capsys.readouterr().out


def test_suggest_links_ranks_related_decisions_and_skips_linked_ones(session, monkeypatch, capsys):
    from proofline.decision_conflicts import suggest_links

    _, new = _approve(
        session, "n", "Decision: Use Redis for the session cache layer.", "file:///n.md"
    )
    _, related = _approve(
        session, "r", "Decision: Cache sessions in memory for the session layer.", "file:///r.md"
    )
    _approve(session, "x", "Decision: Adopt quarterly planning.", "file:///x.md")
    found = suggest_links(session, new.id[:8], min_similarity=0.1)
    assert [item.other_id for item in found] == [related.id]
    assert "session" in found[0].shared_terms and "based_on" in found[0].kinds_to_consider
    session.add(
        DecisionRelation(source_decision_id=new.id, target_decision_id=related.id, kind="based_on")
    )
    session.commit()
    assert suggest_links(session, new.id, min_similarity=0.1) == []
    for ref, kwargs in (("short", {}), (new.id, {"limit": 0}), (new.id, {"min_similarity": 0})):
        with pytest.raises(ValueError):
            suggest_links(session, ref, **kwargs)
    _patch(session, monkeypatch)
    main(["suggest-links", new.id, "--format", "json"])
    assert json.loads(capsys.readouterr().out)["suggestions"] == []
    main(["suggest-links", new.id])
    assert "No related decisions found." in capsys.readouterr().out
