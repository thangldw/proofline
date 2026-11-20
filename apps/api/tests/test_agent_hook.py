import json
from io import StringIO

import proofline.cli as cli_module
from proofline.agent_hook import post_tool_use, pre_tool_use, run, target_path
from proofline.cli import main
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ADR = (
    "Decision: The core must stay offline.\n"
    "Reason: privacy.\n"
    'Enforce: forbid "import requests" in src/core/**/*.py\n'
)


def _approve(session):
    source, _ = ingest_source(
        session, SourceCreate(title="adr", uri="file:///repo/docs/adr.md", content=ADR)
    )
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    decision.status = "accepted"
    session.commit()
    return decision


def _event(tool, path, **extra):
    return json.dumps(
        {"hook_event_name": "x", "tool_name": tool, "tool_input": {"file_path": path, **extra}}
    )


def _repo(tmp_path, body):
    core = tmp_path / "src" / "core"
    core.mkdir(parents=True)
    (core / "a.py").write_text(body)
    return tmp_path


def test_target_path_accepts_edit_tools_inside_the_root_only(tmp_path):
    inside = str(tmp_path / "src" / "a.py")
    assert target_path(json.loads(_event("Edit", inside)), tmp_path) == "src/a.py"
    assert target_path(json.loads(_event("Write", "src/a.py")), tmp_path) == "src/a.py"
    assert target_path(json.loads(_event("Edit", "/etc/passwd")), tmp_path) is None
    assert target_path(json.loads(_event("Edit", str(tmp_path / ".." / "x.py"))), tmp_path) is None
    assert target_path(json.loads(_event("Bash", "x")), tmp_path) is None
    assert target_path({"tool_name": "Edit", "tool_input": []}, tmp_path) is None


def test_pre_hook_gives_the_agent_the_decision_as_quoted_data(session, tmp_path):
    decision = _approve(session)
    root = _repo(tmp_path, "x = 1\n")
    out = json.loads(run(session, _event("Edit", "src/core/a.py"), "pre", root))
    context = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert decision.id[:8] in context and "must stay offline" in context
    assert "not instructions" in context
    assert run(session, _event("Edit", "src/other/b.py"), "pre", root) == ""
    assert run(session, _event("Bash", "x"), "pre", root) == ""


def test_pre_hook_neutralises_control_characters_and_bounds_size(session, tmp_path):
    source, _ = ingest_source(
        session,
        SourceCreate(
            title="adr",
            uri="file:///repo/x.md",
            content="Decision: "
            + "A" * 5000
            + '\x1b[31m ignore previous\nEnforce: forbid "zz" in src/**\n',
        ),
    )
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    decision.status = "accepted"
    session.commit()
    root = _repo(tmp_path, "x\n")
    context = json.loads(run(session, _event("Edit", "src/core/a.py"), "pre", root))[
        "hookSpecificOutput"
    ]["additionalContext"]
    assert "\x1b" not in context and len(context) <= 2400


def test_post_hook_blocks_on_violation_and_stays_quiet_otherwise(session, tmp_path):
    decision = _approve(session)
    root = _repo(tmp_path, "import requests\n")
    out = json.loads(run(session, _event("Edit", "src/core/a.py"), "post", root))
    assert out["decision"] == "block"
    assert decision.id[:8] in out["reason"] and "src/core/a.py:1" in out["reason"]
    (root / "src" / "core" / "a.py").write_text("import json\n")
    assert run(session, _event("Edit", "src/core/a.py"), "post", root) == ""
    assert post_tool_use(session, {"tool_name": "Read", "tool_input": {}}, root) is None
    assert pre_tool_use(session, {}, root) is None


def test_garbage_input_is_ignored(session, tmp_path):
    for raw in ("", "not json", "[]", "5"):
        assert run(session, raw, "pre", tmp_path) == ""


def test_cli_hook_is_silent_without_a_database_and_on_errors(
    session, monkeypatch, tmp_path, capsys
):
    _approve(session)
    root = _repo(tmp_path / "proj", "import requests\n")
    monkeypatch.chdir(root)
    monkeypatch.setenv("PROOFLINE_HOME", str(tmp_path / "nowhere"))
    monkeypatch.setattr("sys.stdin", StringIO(_event("Edit", "src/core/a.py")))
    main(["agent-hook", "post"])
    assert capsys.readouterr().out == ""
    home = tmp_path / "home"
    home.mkdir()
    (home / "proofline.db").write_text("")
    monkeypatch.setenv("PROOFLINE_HOME", str(home))
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    monkeypatch.setattr("sys.stdin", StringIO(_event("Edit", "src/core/a.py")))
    main(["agent-hook", "post"])
    assert json.loads(capsys.readouterr().out)["decision"] == "block"
    monkeypatch.setattr(
        cli_module, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    monkeypatch.setattr("sys.stdin", StringIO(_event("Edit", "src/core/a.py")))
    main(["agent-hook", "post"])
    assert capsys.readouterr().out == ""
