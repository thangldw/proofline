import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

repository_root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "publish_pypi", repository_root / "scripts/publish_pypi.py"
)
assert spec and spec.loader
publish_pypi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_pypi)


def test_public_release_targets_available_distribution_name():
    assert publish_pypi.DISTRIBUTION_NAME == "proofline-evidence"
    assert publish_pypi.PYPI_JSON == "https://pypi.org/pypi/proofline-evidence/{version}/json"


def test_release_artifacts_require_exact_wheel_and_sdist(tmp_path: Path):
    wheel = tmp_path / "proofline_evidence-2.0.0-py3-none-any.whl"
    sdist = tmp_path / "proofline_evidence-2.0.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")

    assert publish_pypi.release_artifacts(tmp_path, "2.0.0") == (wheel, sdist)


def test_release_artifacts_fail_closed_when_either_artifact_is_missing(tmp_path: Path):
    (tmp_path / "proofline_evidence-2.0.0-py3-none-any.whl").write_bytes(b"wheel")

    with pytest.raises(ValueError, match="exact_release_artifacts_missing"):
        publish_pypi.release_artifacts(tmp_path, "2.0.0")


def test_public_release_verification_binds_filenames_and_sha256(tmp_path: Path):
    wheel = tmp_path / "proofline_evidence-2.0.0-py3-none-any.whl"
    sdist = tmp_path / "proofline_evidence-2.0.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    metadata = {
        "info": {"version": "2.0.0"},
        "urls": [
            {
                "filename": artifact.name,
                "digests": {"sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()},
            }
            for artifact in (wheel, sdist)
        ],
    }

    publish_pypi.verify_public_release(metadata, "2.0.0", (wheel, sdist))


def test_public_release_verification_rejects_digest_mismatch(tmp_path: Path):
    wheel = tmp_path / "proofline_evidence-2.0.0-py3-none-any.whl"
    sdist = tmp_path / "proofline_evidence-2.0.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    metadata = {
        "info": {"version": "2.0.0"},
        "urls": [
            {"filename": wheel.name, "digests": {"sha256": "0" * 64}},
            {"filename": sdist.name, "digests": {"sha256": "1" * 64}},
        ],
    }

    with pytest.raises(ValueError, match="public_release_digest_mismatch"):
        publish_pypi.verify_public_release(metadata, "2.0.0", (wheel, sdist))


def test_partial_public_release_uploads_only_missing_artifact(tmp_path: Path):
    wheel = tmp_path / "proofline_evidence-2.0.0-py3-none-any.whl"
    sdist = tmp_path / "proofline_evidence-2.0.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    metadata = {
        "info": {"version": "2.0.0"},
        "urls": [
            {
                "filename": wheel.name,
                "digests": {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()},
            }
        ],
    }

    assert publish_pypi.artifacts_to_upload(metadata, "2.0.0", (wheel, sdist)) == (sdist,)


def test_public_install_smoke_isolated_from_worktree_and_ambient_python(monkeypatch):
    calls = []

    def fake_run(command, *, cwd, env):
        calls.append((command, cwd, env))
        stdout = "proofline 2.0.0\n" if command[-1] == "--version" else ""
        return SimpleNamespace(stdout=stdout)

    monkeypatch.setenv("PYTHONPATH", "/ambient/source")
    monkeypatch.setenv("PROOFLINE_HOME", "/ambient/home")
    monkeypatch.setattr(publish_pypi, "_run_smoke", fake_run)

    publish_pypi.qualify_public_install("2.0.0")

    roots = {cwd for _command, cwd, _env in calls}
    assert len(roots) == 1
    root = roots.pop()
    assert all("PYTHONPATH" not in env for _command, _cwd, env in calls)
    assert all(env["PROOFLINE_HOME"] == str(root / "proofline-home") for _c, _d, env in calls)
    demo = next(command for command, _cwd, _env in calls if "stale-decision" in command)
    assert demo[-2:] == ["--output-dir", str(root / "demo")]
    install = next(command for command, _cwd, _env in calls if "install" in command)
    assert "proofline-evidence==2.0.0" in install


def test_publish_recovery_tolerates_stale_public_metadata():
    source = (repository_root / "scripts/publish_pypi.py").read_text(encoding="utf-8")

    assert '"--skip-existing"' in source


def test_verify_only_never_attempts_an_upload(tmp_path: Path, monkeypatch, capsys):
    wheel = tmp_path / "proofline_evidence-2.0.0-py3-none-any.whl"
    sdist = tmp_path / "proofline_evidence-2.0.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    run_calls = []
    wait_calls = []
    qualify_calls = []

    monkeypatch.setattr(publish_pypi, "_run", lambda command: run_calls.append(command))
    monkeypatch.setattr(
        publish_pypi,
        "wait_for_public_release",
        lambda version, artifacts, timeout: wait_calls.append((version, artifacts, timeout)),
    )
    monkeypatch.setattr(
        publish_pypi,
        "qualify_public_install",
        lambda version: qualify_calls.append(version),
    )

    publish_pypi.main(
        [
            "--version",
            "2.0.0",
            "--dist-dir",
            str(tmp_path),
            "--timeout-seconds",
            "7",
            "--verify-only",
        ]
    )

    assert len(run_calls) == 1
    assert run_calls[0][2:4] == ["twine", "check"]
    assert wait_calls == [("2.0.0", (wheel, sdist), 7)]
    assert qualify_calls == ["2.0.0"]
    assert '"status": "published_and_verified"' in capsys.readouterr().out
