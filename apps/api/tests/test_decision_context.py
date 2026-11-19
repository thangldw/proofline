import json
import subprocess

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_context import (
    ContextError,
    build_context,
    git_diff,
    parse_unified_diff,
    render_markdown,
)
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

DIFF = """diff --git a/src/core/a.py b/src/core/a.py
--- a/src/core/a.py
+++ b/src/core/a.py
@@ -3,0 +4,2 @@ def f():
+x = 1
+y = 2
@@ -10 +12 @@
-old
+new
diff --git a/gone.py b/gone.py
--- a/gone.py
+++ /dev/null
@@ -1,3 +0,0 @@
"""

ADR = (
    "Decision: The core must stay offline.\n"
    "Reason: privacy.\n"
    'Enforce: forbid "import requests" in src/core/**/*.py\n'
)


def _approve(session, content, uri):
    source, _ = ingest_source(session, SourceCreate(title="adr", uri=uri, content=content))
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return decision


def test_parse_unified_diff_ranges_and_deleted_files():
    assert parse_unified_diff(DIFF) == {"src/core/a.py": [(4, 5), (12, 12)]}
    assert parse_unified_diff("") == {}


def test_code_refs_near_a_change_enforce_rules_and_edited_documents(session, tmp_path):
    decision = _approve(session, ADR, "file:///repo/docs/adr.md")
    core = tmp_path / "src" / "core"
    core.mkdir(parents=True)
    (core / "a.py").write_text(
        f"# proofline-decision: {decision.id[:8]}\nimport requests\n" + "x = 1\n" * 40
    )
    (core / "far.py").write_text("x = 1\n" * 40 + f"# proofline-decision: {decision.id[:8]}\n")
    changes = {
        "src/core/a.py": [(2, 2)],
        "src/core/far.py": [(1, 1)],
        "docs/adr.md": [(3, 3)],
        "src/other/b.py": [(1, 1)],
    }
    items = build_context(session, tmp_path, changes, radius=3)
    seen = {(i.path, i.via, i.health, i.detail) for i in items}
    assert ("src/core/a.py", "code_ref", "current", "line 1") in seen
    assert ("src/core/a.py", "enforce_rule", "violated", "rule 1") in seen
    assert ("docs/adr.md", "document_edit", "unchanged", "lines 1-3") in seen
    assert not any(
        i.path in ("src/core/far.py", "src/other/b.py") and i.via == "code_ref" for i in items
    )
    assert not any(i.path == "src/other/b.py" for i in items)
    assert any(i.needs_attention for i in items)


def test_markdown_is_content_free_unless_titles_are_requested(session, tmp_path):
    decision = _approve(session, ADR, "file:///repo/docs/adr.md")
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "a.py").write_text("x = 1\n")
    items = build_context(session, tmp_path, {"src/core/a.py": [(1, 1)]})
    plain = render_markdown(items, include_titles=False)
    assert decision.id[:8] in plain and "offline" not in plain
    assert "offline" in render_markdown(items, include_titles=True)
    assert "No approved decision" in render_markdown([], include_titles=False)


def test_ref_and_radius_validation(tmp_path):
    for bad in ("--upload-pack=x", "a..b", "", "-x"):
        with pytest.raises(ContextError):
            git_diff(tmp_path, bad)


def test_cli_with_a_real_git_diff(session, monkeypatch, tmp_path, capsys):
    decision = _approve(session, ADR, "file:///repo/docs/adr.md")
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )

    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    core = tmp_path / "src" / "core"
    core.mkdir(parents=True)
    (core / "a.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "topic")
    (core / "a.py").write_text("x = 1\nimport requests\n")
    git("commit", "-qam", "change")
    main(["code-context", "--base", "main", "--root", str(tmp_path), "--format", "json"])
    document = json.loads(capsys.readouterr().out)
    assert document["attention"] == 1
    assert document["items"][0]["decision_id"] == decision.id
    assert "decision_title" not in document["items"][0]
    with pytest.raises(SystemExit) as failing:
        main(["code-context", "--base", "main", "--root", str(tmp_path), "--fail-on-attention"])
    assert failing.value.code == 1
    diff_file = tmp_path / "d.diff"
    diff_file.write_text(DIFF)
    main(["code-context", "--diff-file", str(diff_file), "--root", str(tmp_path)])
    assert "Decisions touched" in capsys.readouterr().out
    with pytest.raises(SystemExit) as missing:
        main(["code-context", "--root", str(tmp_path)])
    assert missing.value.code == 2
