import json

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_whatif import WhatIfError, render_text, what_if_superseded
from proofline.ingestion import ingest_source
from proofline.models import Decision, DecisionRelation
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _approve(session, text, uri):
    source, _ = ingest_source(session, SourceCreate(title=uri, uri=uri, content=text))
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    decision.status = "accepted"
    session.commit()
    return decision


def _world(session, tmp_path):
    root = _approve(
        session,
        'Decision: Use SQLite.\nEnforce: forbid "psycopg" in src/**/*.py\n',
        "file:///root.md",
    )
    child = _approve(session, "Decision: Cache in SQLite.", "file:///child.md")
    grand = _approve(session, "Decision: Index the cache.", "file:///grand.md")
    peer = _approve(session, "Decision: Use Postgres instead.", "file:///peer.md")
    add = session.add
    add(DecisionRelation(source_decision_id=child.id, target_decision_id=root.id, kind="based_on"))
    add(
        DecisionRelation(
            source_decision_id=grand.id, target_decision_id=child.id, kind="implements"
        )
    )
    add(
        DecisionRelation(source_decision_id=peer.id, target_decision_id=root.id, kind="contradicts")
    )
    session.commit()
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text(f"# proofline-decision: {root.id[:8]}\n")
    (src / "b.py").write_text("x = 1\n")
    return root, child, grand, peer


def test_blast_radius_is_transitive_and_lists_refs_rules_and_other_relations(session, tmp_path):
    root, child, grand, peer = _world(session, tmp_path)
    result = what_if_superseded(session, root.id[:8], tmp_path)
    assert [(d.decision_id, d.depth, d.kinds) for d in result.dependents] == [
        (child.id, 1, ["based_on"]),
        (grand.id, 2, ["based_on", "implements"]),
    ]
    assert result.code_refs == [{"path": str(tmp_path / "src" / "a.py"), "line": 1}]
    assert result.rules[0]["files_covered"] == 2
    assert result.other_relations == [
        {"relation": "contradicts", "direction": "incoming", "other_decision_id": peer.id}
    ]
    text = render_text(result)
    assert "2 dependent decision(s)" in text and "stop being checked" in text
    assert "SQLite" not in render_text(result, include_titles=False)
    assert "title" not in result.content_free_model_dump()


def test_leaf_decision_has_no_dependents_and_bad_references_are_rejected(session, tmp_path):
    _, _, grand, _ = _world(session, tmp_path)
    assert what_if_superseded(session, grand.id, tmp_path).dependents == []
    for reference, code in (
        ("abc", "decision_reference_invalid"),
        ("ffffffff", "decision_not_found"),
    ):
        with pytest.raises(WhatIfError) as caught:
            what_if_superseded(session, reference, tmp_path)
        assert caught.value.code == code
    with pytest.raises(WhatIfError):
        what_if_superseded(session, grand.id, tmp_path / "missing")


def test_unapproved_target_gets_a_note(session, tmp_path):
    root, *_ = _world(session, tmp_path)
    root.status = "candidate"
    session.commit()
    assert any(
        "not currently approved" in n for n in what_if_superseded(session, root.id, tmp_path).notes
    )


def test_cli_what_if(session, monkeypatch, tmp_path, capsys):
    root, *_ = _world(session, tmp_path)
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    main(["what-if", root.id[:8], "--root", str(tmp_path)])
    assert "were superseded" in capsys.readouterr().out
    main(["what-if", root.id[:8], "--root", str(tmp_path), "--format", "json", "--no-titles"])
    document = json.loads(capsys.readouterr().out)
    assert len(document["dependents"]) == 2 and "title" not in document
    with pytest.raises(SystemExit) as caught:
        main(["what-if", "nope1234", "--root", str(tmp_path)])
    assert caught.value.code == 2
