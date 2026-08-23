import json
import subprocess
import sys
import tomllib
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


def test_ci_workflow_runs_release_critical_commands():
    root = repository_root()
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    makefile = (root / "Makefile").read_text(encoding="utf-8")

    for command in (
        "npm ci",
        "make test",
        "make check",
        "npm audit --omit=dev --audit-level=high",
        "proofline verify-package",
        "proofline verify-review-receipt",
        "proofline verify-attestation",
        "proofline check-decisions --format sarif",
        "proofline check-impacts --format sarif",
    ):
        assert command in workflow
    assert "verify-package-conformance:" in makefile
    assert "spec/signed-attestation/v1/test-vectors/valid-ed25519.json" in makefile


def test_release_check_covers_public_plugin_version_surfaces():
    root = repository_root()
    release_check = (root / "scripts/release_check.py").read_text(encoding="utf-8")

    for manifest in (
        ".codex-plugin/plugin.json",
        ".claude-plugin/plugin.json",
        ".kimi-plugin/plugin.json",
    ):
        assert manifest in release_check


def test_source_distribution_excludes_local_build_and_test_state():
    root = repository_root()
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    excluded = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"])

    assert {
        "/.hypothesis",
        "/.pytest_cache",
        "/.ruff_cache",
        "/.venv",
        "/.worktrees",
        "/apps/web/dist",
        "**/__pycache__",
        "**/node_modules",
        "**/*.db",
        "**/*.pyc",
        "**/*.tsbuildinfo",
    } <= excluded


def test_nanoid_security_override_is_locked_to_patched_compatible_version():
    root = repository_root()
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))

    assert package["overrides"]["nanoid"] == "3.3.18"
    assert lock["packages"]["node_modules/nanoid"]["version"] == "3.3.18"
