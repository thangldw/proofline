import json
import subprocess

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_undocumented import candidates_from_diff, find_undocumented
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

DIFF = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,0 +2,4 @@
+requests>=2.31
+# a comment
+-r other.txt
+python_dateutil==2.9
diff --git a/pyproject.toml b/pyproject.toml
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -5,0 +6,3 @@
+  "sqlalchemy>=2.0,<3",
+  "License :: OSI Approved :: MIT",
+version = "9"
diff --git a/apps/web/package.json b/apps/web/package.json
--- a/apps/web/package.json
+++ b/apps/web/package.json
@@ -1,0 +2,3 @@
+    "version": "1.0.0",
+    "react-dom": "^19.3.1",
+    "@scope/widget": "~2.0.0"
diff --git a/Cargo.toml b/Cargo.toml
--- a/Cargo.toml
+++ b/Cargo.toml
@@ -1,0 +2,3 @@
+name = "x"
+serde = "1.0"
+tokio = { version = "1" }
diff --git a/go.mod b/go.mod
--- a/go.mod
+++ b/go.mod
@@ -1,0 +2 @@
+	github.com/google/uuid v1.6.0
diff --git a/deploy/Dockerfile b/deploy/Dockerfile
new file mode 100644
--- /dev/null
+++ b/deploy/Dockerfile
@@ -0,0 +1 @@
+FROM python:3.12
diff --git a/main.tf b/main.tf
new file mode 100644
--- /dev/null
+++ b/main.tf
@@ -0,0 +1 @@
+resource "x" "y" {}
"""


def _approve(session, text, uri):
    source, _ = ingest_source(session, SourceCreate(title="adr", uri=uri, content=text))
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()


def test_candidates_cover_manifests_and_new_infrastructure_files():
    names = {(c.path, c.kind, c.name) for c in candidates_from_diff(DIFF)}
    assert names == {
        ("requirements.txt", "dependency", "requests"),
        ("requirements.txt", "dependency", "python_dateutil"),
        ("pyproject.toml", "dependency", "sqlalchemy"),
        ("apps/web/package.json", "dependency", "react-dom"),
        ("apps/web/package.json", "dependency", "@scope/widget"),
        ("Cargo.toml", "dependency", "serde"),
        ("Cargo.toml", "dependency", "tokio"),
        ("go.mod", "dependency", "github.com/google/uuid"),
        ("deploy/Dockerfile", "infrastructure", "docker"),
        ("main.tf", "infrastructure", "terraform"),
    }


def test_documented_additions_are_not_reported(session):
    _approve(
        session,
        "Decision: Use SQLAlchemy and python-dateutil for storage.\n"
        "Reason: Docker images stay small; we deploy with Terraform and the widget library.",
        "file:///a.md",
    )
    missing = {(m.kind, m.name) for m in find_undocumented(session, candidates_from_diff(DIFF))}
    assert ("dependency", "sqlalchemy") not in missing
    assert ("dependency", "python_dateutil") not in missing
    assert ("infrastructure", "docker") not in missing
    assert ("infrastructure", "terraform") not in missing
    assert ("dependency", "@scope/widget") not in missing
    assert {("dependency", "requests"), ("dependency", "serde")} <= missing


def test_matching_is_whole_word_and_only_approved_decisions_count(session):
    _approve(session, "Decision: We reject requestsify.", "file:///a.md")
    source, _ = ingest_source(
        session, SourceCreate(title="b", uri="file:///b.md", content="Decision: Use requests.")
    )
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    decision.status = "candidate"
    session.commit()
    assert any(m.name == "requests" for m in find_undocumented(session, candidates_from_diff(DIFF)))
    decision.status = "accepted"
    session.commit()
    assert not any(
        m.name == "requests" for m in find_undocumented(session, candidates_from_diff(DIFF))
    )
    ignored = find_undocumented(
        session, candidates_from_diff(DIFF), ignore=frozenset({"SERDE", "tokio"})
    )
    assert not any(m.name in ("serde", "tokio") for m in ignored)


def test_cli_with_a_real_git_diff(session, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )

    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "requirements.txt").write_text("flask==3.0\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "topic")
    (tmp_path / "requirements.txt").write_text("flask==3.0\nredis==5.0\n")
    git("commit", "-qam", "add redis")
    main(["find-undocumented", "--base", "main", "--root", str(tmp_path), "--format", "json"])
    assert json.loads(capsys.readouterr().out)["undocumented"][0]["name"] == "redis"
    with pytest.raises(SystemExit) as failing:
        main(
            [
                "find-undocumented",
                "--base",
                "main",
                "--root",
                str(tmp_path),
                "--fail-on-undocumented",
            ]
        )
    assert failing.value.code == 1
    capsys.readouterr()
    main(["find-undocumented", "--base", "main", "--root", str(tmp_path), "--ignore", "redis"])
    assert "covered by an approved decision" in capsys.readouterr().out
    with pytest.raises(SystemExit) as missing:
        main(["find-undocumented", "--root", str(tmp_path)])
    assert missing.value.code == 2
