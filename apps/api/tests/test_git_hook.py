import json
import os
import subprocess

import pytest
from proofline.cli import main
from proofline.git_hook import HOOK_MARKER, HookError, install_hook, render_hook, uninstall_hook


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_install_writes_executable_marked_hook_and_uninstall_removes_it(tmp_path):
    repo = _repo(tmp_path)
    result = install_hook(repo)
    assert result.action == "installed"
    assert result.path.name == "pre-commit" and os.access(result.path, os.X_OK)
    text = result.path.read_text()
    assert HOOK_MARKER in text and "check-code-refs" in text and "check-decisions" not in text
    assert install_hook(repo, with_decisions=True).action == "installed"
    assert "check-decisions" in result.path.read_text()
    assert uninstall_hook(repo).action == "removed"
    assert not result.path.exists()
    assert uninstall_hook(repo).action == "absent"


def test_foreign_hook_is_never_overwritten_or_removed_without_force(tmp_path):
    repo = _repo(tmp_path)
    path = install_hook(repo).path
    path.write_text("#!/bin/sh\necho mine\n")
    with pytest.raises(HookError) as exists:
        install_hook(repo)
    assert exists.value.code == "hook_exists"
    with pytest.raises(HookError) as unmanaged:
        uninstall_hook(repo)
    assert unmanaged.value.code == "hook_not_managed"
    assert path.read_text().startswith("#!/bin/sh\necho mine")
    install_hook(repo, force=True)
    assert HOOK_MARKER in path.read_text()


def test_not_a_repository_and_custom_hooks_path(tmp_path):
    with pytest.raises(HookError) as caught:
        install_hook(tmp_path / "missing")
    assert caught.value.code == "not_a_git_repository"
    (tmp_path / "r").mkdir()
    repo = _repo(tmp_path / "r")
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"], check=True)
    assert install_hook(repo).path == repo / ".githooks" / "pre-commit"


def test_hook_script_runs_checks_and_skips_without_proofline(tmp_path):
    repo = _repo(tmp_path)
    path = install_hook(repo).path
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "a.py"], check=True)
    empty_path = {**os.environ, "PATH": "/usr/bin:/bin"}
    ran = subprocess.run([str(path)], cwd=repo, env=empty_path, capture_output=True, text=True)
    assert ran.returncode == 0 and "skipping" in ran.stderr
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "proofline").write_text('#!/bin/sh\necho "$@" >> "$0.log"\nexit 3\n')
    (stub / "proofline").chmod(0o755)
    with_stub = {**os.environ, "PATH": f"{stub}:/usr/bin:/bin"}
    failed = subprocess.run([str(path)], cwd=repo, env=with_stub, capture_output=True, text=True)
    assert failed.returncode == 1
    assert "check-code-refs a.py" in (stub / "proofline.log").read_text()
    assert render_hook(with_decisions=True).count("exit 1") == 3


def test_cli_hook_install_and_uninstall(tmp_path, capsys):
    repo = _repo(tmp_path)
    main(["hook", "install", "--repo", str(repo)])
    assert json.loads(capsys.readouterr().out)["action"] == "installed"
    main(["hook", "uninstall", "--repo", str(repo)])
    assert json.loads(capsys.readouterr().out)["action"] == "removed"
    with pytest.raises(SystemExit) as caught:
        main(["hook", "install", "--repo", str(repo / "nope")])
    assert caught.value.code == 2
