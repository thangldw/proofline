import io
import json
import subprocess
import sys
import tarfile
import tomllib
import zipfile
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
        "make audit",
        "npm audit --omit=dev --audit-level=high",
        "npm run test:e2e",
        "verify_release_artifacts.py",
        "proofline verify-package",
        "proofline verify-review-receipt",
        "proofline verify-attestation",
        "proofline check-decisions --format sarif",
        "proofline check-impacts --format sarif",
    ):
        assert command in workflow
    assert "verify-package-conformance:" in makefile
    assert "pip-audit --local --skip-editable" in makefile
    assert "spec/signed-attestation/v1/test-vectors/valid-ed25519.json" in makefile


def test_release_toolchain_pins_non_vulnerable_pip_floor():
    project = tomllib.loads((repository_root() / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pip>=26.2,<27" in project["project"]["optional-dependencies"]["dev"]


def test_pypi_distribution_uses_available_name_without_renaming_runtime():
    project = tomllib.loads((repository_root() / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["name"] == "proofline-evidence"
    assert project["project"]["scripts"]["proofline"] == "proofline.runtime:main"


def test_release_entrypoints_require_full_gates_and_both_python_artifacts():
    root = repository_root()
    local = (root / "scripts/release_local.sh").read_text(encoding="utf-8")
    windows = (root / "scripts/release_windows.ps1").read_text(encoding="utf-8")

    for script in (local, windows):
        for command in (
            "test:e2e",
            "verify_release_artifacts.py",
            "qualify_python_artifact.py",
            "publish_pypi.py",
        ):
            assert command in script
        assert ".whl" in script
        assert ".tar.gz" in script
        assert script.index("publish_pypi.py") < script.index("git tag")
    assert "make audit" in local
    assert "verify-package-conformance" in local
    assert "pip_audit" in windows
    assert "verify_attestation_vector.py" in windows
    assert 'if ($Tag -like "v0.*" -or $Tag.Contains("-"))' in windows
    assert "gh release create @ReleaseArgs" in windows


def test_trusted_publisher_workflow_separates_build_publish_and_public_verification():
    workflow = (repository_root() / ".github/workflows/publish-pypi.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "environment:" in workflow
    assert "name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@" in workflow
    assert "proofline_evidence-2.0.0-py3-none-any.whl" in workflow
    assert "proofline_evidence-2.0.0.tar.gz" in workflow
    assert "--verify-only" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow
    assert workflow.index("actions/upload-artifact@") < workflow.index(
        "pypa/gh-action-pypi-publish@"
    )


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


def test_python_release_archives_use_fail_closed_content_selection():
    root = repository_root()
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    targets = pyproject["tool"]["hatch"]["build"]["targets"]

    assert set(targets["sdist"]["include"]) == {
        "/LICENSE",
        "/README.md",
        "/pyproject.toml",
        "/apps/api/proofline",
        "/spec",
    }
    for target in (targets["wheel"], targets["sdist"]):
        assert {"**/*.key", "**/*.db", "**/*.pyc"} <= set(target["exclude"])
    assert "**/*.pem" in targets["wheel"]["exclude"]


@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
def test_release_artifact_verifier_rejects_private_key_bytes(tmp_path, archive_kind):
    marker = b"-----BEGIN PRIVATE KEY-----\nPRIVATE RELEASE MARKER\n"
    if archive_kind == "wheel":
        archive = tmp_path / "proofline_evidence-2.0.0-py3-none-any.whl"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("proofline/local-key.bin", marker)
    else:
        archive = tmp_path / "proofline_evidence-2.0.0.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            info = tarfile.TarInfo("proofline_evidence-2.0.0/local-key.bin")
            info.size = len(marker)
            handle.addfile(info, io.BytesIO(marker))

    completed = subprocess.run(
        [sys.executable, "scripts/verify_release_artifacts.py", str(archive)],
        cwd=repository_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert completed.stderr.strip() == (
        "release artifact verification failed: private_key_material"
    )
    assert "PRIVATE RELEASE MARKER" not in completed.stderr


def test_nanoid_security_override_is_locked_to_patched_compatible_version():
    root = repository_root()
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))

    assert package["overrides"]["nanoid"] == "3.3.18"
    assert lock["packages"]["node_modules/nanoid"]["version"] == "3.3.18"
