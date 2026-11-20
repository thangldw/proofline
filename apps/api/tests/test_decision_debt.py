import json
import subprocess

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_debt import DebtError, build_debt_map, directory_of, git_churn
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _repo(tmp_path):
    tmp_path = tmp_path / "repo"
    tmp_path.mkdir()
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    for name in ("src/core", "src/api", "docs"):
        (tmp_path / name).mkdir(parents=True)
    return tmp_path


def _commit(root, files, message):
    for name, text in files.items():
        (root / name).write_text(text)
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", message)


def _approve(session, text):
    source, _ = ingest_source(session, SourceCreate(title="a", uri="file:///a.md", content=text))
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    decision.status = "accepted"
    session.commit()
    return decision


def test_directory_grouping():
    assert directory_of("src/core/a.py", 2) == "src/core"
    assert directory_of("src/core/deep/a.py", 2) == "src/core"
    assert directory_of("src/core/a.py", 1) == "src"
    assert directory_of("README.md", 2) == "."


def test_churn_counts_a_file_once_per_commit_and_validates_days(tmp_path):
    root = _repo(tmp_path)
    _commit(root, {"src/core/a.py": "1", "src/api/b.py": "1"}, "one")
    _commit(root, {"src/core/a.py": "2"}, "two")
    assert git_churn(root, 30) == {"src/core/a.py": 2, "src/api/b.py": 1}
    with pytest.raises(DebtError):
        git_churn(root, 0)
    with pytest.raises(DebtError):
        git_churn(tmp_path / "nope", 30)


def test_covered_and_undecided_directories(session, tmp_path):
    root = _repo(tmp_path)
    decision = _approve(
        session, 'Decision: Core is offline.\nEnforce: forbid "import requests" in src/core/*.py\n'
    )
    _commit(root, {"src/core/a.py": "x = 1\n", "src/api/b.py": "x = 1\n"}, "one")
    _commit(root, {"src/api/b.py": f"# proofline-decision: {decision.id[:8]}\n"}, "two")
    _commit(root, {"docs/c.md": "x"}, "three")
    rows = {r.directory: r for r in build_debt_map(session, root)}
    assert rows["src/core"].rules_covering == 1 and not rows["src/core"].undecided
    assert rows["src/api"].code_refs == 1 and rows["src/api"].commits == 2
    assert rows["docs"].undecided and rows["docs"].commits == 1
    ordered = [r.directory for r in build_debt_map(session, root)]
    assert ordered[0] == "src/api"
    with pytest.raises(DebtError):
        build_debt_map(session, root, depth=0)


def test_deleted_files_are_ignored_and_cli(session, monkeypatch, tmp_path, capsys):
    root = _repo(tmp_path)
    _commit(root, {"docs/gone.md": "x", "src/api/b.py": "x"}, "one")
    (root / "docs" / "gone.md").unlink()
    _git(root, "commit", "-qam", "remove")
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    main(["debt", "--root", str(root), "--format", "json", "--only-gaps"])
    document = json.loads(capsys.readouterr().out)
    assert [d["directory"] for d in document["directories"]] == ["src/api"]
    main(["debt", "--root", str(root)])
    assert "no decision" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        main(["debt", "--root", str(root), "--since", "0"])
    assert caught.value.code == 2
