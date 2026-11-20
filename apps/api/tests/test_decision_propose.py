import json

import proofline.cli as cli_module
import pytest
from proofline.agent_hook import run
from proofline.cli import main
from proofline.decision_propose import ProposeError, render_proposal, write_proposals
from proofline.decision_undocumented import Candidate, candidates_from_lines
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _extract(session, text):
    source, _ = ingest_source(
        session, SourceCreate(title="p", uri="file:///repo/p.md", content=text)
    )
    return session.scalars(select(Decision).where(Decision.source_id == source.id)).all()


def test_proposal_is_a_candidate_the_extractor_reads_and_the_rule_is_inactive(session):
    text = render_proposal(Candidate("requirements.txt", "dependency", "httpx"), "fast client")
    [decision] = _extract(session, text)
    assert decision.status == "candidate"
    assert "httpx" in decision.statement and "fast client" in (decision.rationale or "")
    assert not any(line.startswith("Enforce:") for line in text.splitlines())
    assert 'Enforce: require "httpx" in requirements.txt' in text
    infra = render_proposal(Candidate("deploy/Dockerfile", "infrastructure", "docker"))
    assert "Enforce: require file deploy/Dockerfile" in infra and "TODO" in infra


def test_hostile_names_cannot_inject_lines_or_paths(tmp_path):
    evil = Candidate("a\nStatus: accepted\n.md", "dependency", "x\nStatus: accepted ../../y")
    text = render_proposal(evil)
    assert [line for line in text.splitlines() if line.startswith("Status:")] == [
        "Status: candidate"
    ]
    [written] = write_proposals([evil], tmp_path / "out")
    assert written.output.parent == tmp_path / "out" and ".." not in written.output.name


def test_write_never_overwrites_and_empty_is_a_noop(tmp_path):
    candidate = Candidate("requirements.txt", "dependency", "httpx")
    assert write_proposals([], tmp_path / "o") == []
    write_proposals([candidate], tmp_path / "o")
    with pytest.raises(ProposeError) as caught:
        write_proposals([candidate], tmp_path / "o")
    assert caught.value.code == "proposal_exists"
    assert len(list((tmp_path / "o").iterdir())) == 1


def test_candidates_from_lines_dependency_only_in_edits_infra_only_whole_file():
    assert [
        c.name for c in candidates_from_lines("requirements.txt", ["httpx>=1"], whole_file=False)
    ] == ["httpx"]
    assert candidates_from_lines("requirements.txt", ["httpx>=1"], whole_file=True) == []
    [infra] = candidates_from_lines("deploy/Dockerfile", [], whole_file=True)
    assert infra.kind == "infrastructure"
    assert candidates_from_lines("deploy/Dockerfile", ["FROM x"], whole_file=False) == []


def _event(tool, path, **tool_input):
    return json.dumps({"tool_name": tool, "tool_input": {"file_path": path, **tool_input}})


def test_post_hook_nudges_for_new_dependencies_but_not_existing_ones(session, tmp_path):
    edit = _event(
        "Edit", "requirements.txt", old_string="requests>=2\n", new_string="requests>=2\nhttpx>=1\n"
    )
    out = json.loads(run(session, edit, "post", tmp_path))["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    assert "httpx" in out["additionalContext"] and "requests" not in out["additionalContext"]
    assert "proofline propose" in out["additionalContext"]
    multi = json.dumps(
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "requirements.txt",
                "edits": [
                    {"old_string": "", "new_string": "rich>=13\n"},
                    "junk",
                    {"new_string": 5},
                ],
            },
        }
    )
    assert "rich" in run(session, multi, "post", tmp_path)
    write = _event("Write", "deploy/Dockerfile", content="FROM python:3.12\n")
    assert "docker" in run(session, write, "post", tmp_path)
    assert (
        run(session, _event("Write", "requirements.txt", content="httpx\n"), "post", tmp_path) == ""
    )
    assert run(session, _event("Edit", "x.py", new_string="import httpx"), "post", tmp_path) == ""
    bad = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "requirements.txt"}})
    assert run(session, bad, "post", tmp_path) == ""


def test_post_hook_stays_quiet_when_a_decision_mentions_it(session, tmp_path):
    for decision in _extract(session, "Decision: Use httpx for every outbound call.\n"):
        decision.status = "accepted"
    session.commit()
    edit = _event("Edit", "requirements.txt", old_string="", new_string="httpx>=1\n")
    assert run(session, edit, "post", tmp_path) == ""


def test_propose_cli_from_name_and_diff_and_errors(session, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    out = tmp_path / "drafts"
    main(["propose", "--name", "httpx", "--path", "requirements.txt", "--output-dir", str(out)])
    assert "status: candidate" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["propose", "--name", "httpx", "--path", "requirements.txt", "--output-dir", str(out)])
    assert "proposal_exists" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["propose"])
    assert "base_or_name_and_path_required" in capsys.readouterr().err
    header = "diff --git a/requirements.txt b/requirements.txt\n--- a/requirements.txt\n"
    diff = header + "+++ b/requirements.txt\n@@ -0,0 +1 @@\n+rich>=13\n"
    monkeypatch.setattr(cli_module, "git_diff", lambda root, base: diff)
    main(["propose", "--base", "main", "--output-dir", str(out), "--format", "json"])
    assert json.loads(capsys.readouterr().out)["proposals"][0].endswith("dependency-rich.md")
    for decision in _extract(session, "Decision: Use rich for output.\n"):
        decision.status = "accepted"
    session.commit()
    main(["propose", "--base", "main", "--output-dir", str(out)])
    assert "Nothing to propose" in capsys.readouterr().out
