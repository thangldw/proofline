import json
import subprocess
import sys
from pathlib import Path

import pytest
from proofline import __version__
from proofline.cli import main


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_release_metadata_matches_current_prerelease(capsys):
    web = json.loads((repository_root() / "apps/web/package.json").read_text(encoding="utf-8"))
    tag = f"v{web['version']}"

    completed = subprocess.run(
        [sys.executable, "scripts/release_check.py", "--tag", tag],
        cwd=repository_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"status": "ready", "tag": tag}

    with pytest.raises(SystemExit, match="0"):
        main(["--version"])
    assert capsys.readouterr().out.strip() == f"proofline {__version__}"


def test_release_check_rejects_a_tag_that_does_not_match_metadata():
    completed = subprocess.run(
        [sys.executable, "scripts/release_check.py", "--tag", "v9.9.9"],
        cwd=repository_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert "release check failed" in completed.stderr


@pytest.mark.parametrize(
    "message",
    [
        "release: local build [skip ci]",
        "release: local build [CI SKIP]",
        "release: local build [no ci]",
        "release: local build [skip actions]",
        "release: local build [actions skip]",
        "release: local build\n\nskip-checks: true",
    ],
)
def test_ci_skip_check_accepts_github_instructions(message):
    completed = subprocess.run(
        [sys.executable, "scripts/check_ci_skip.py", "--message", message],
        cwd=repository_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_ci_skip_check_rejects_an_ordinary_commit_message():
    completed = subprocess.run(
        [sys.executable, "scripts/check_ci_skip.py", "--message", "release: local build"],
        cwd=repository_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert "must contain a GitHub CI skip instruction" in completed.stderr
