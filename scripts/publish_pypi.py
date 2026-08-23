#!/usr/bin/env python3
"""Publish exact Proofline artifacts and verify the immutable public release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PYPI_JSON = "https://pypi.org/pypi/proofline/{version}/json"


class PublicReleaseIncomplete(ValueError):
    pass


def release_artifacts(dist_dir: Path, version: str) -> tuple[Path, Path]:
    artifacts = (
        dist_dir / f"proofline-{version}-py3-none-any.whl",
        dist_dir / f"proofline-{version}.tar.gz",
    )
    if not all(path.is_file() for path in artifacts):
        raise ValueError("exact_release_artifacts_missing")
    return artifacts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_public_release(
    metadata: dict[str, Any], version: str, artifacts: tuple[Path, Path]
) -> None:
    if metadata.get("info", {}).get("version") != version:
        raise ValueError("public_release_version_mismatch")
    public_digests = {
        item.get("filename"): item.get("digests", {}).get("sha256")
        for item in metadata.get("urls", [])
    }
    for artifact in artifacts:
        if artifact.name not in public_digests:
            raise PublicReleaseIncomplete("public_release_incomplete")
        if public_digests[artifact.name] != _sha256(artifact):
            raise ValueError("public_release_digest_mismatch")


def artifacts_to_upload(
    metadata: dict[str, Any] | None,
    version: str,
    artifacts: tuple[Path, Path],
) -> tuple[Path, ...]:
    if metadata is None:
        return artifacts
    if metadata.get("info", {}).get("version") != version:
        raise ValueError("public_release_version_mismatch")
    public_digests = {
        item.get("filename"): item.get("digests", {}).get("sha256")
        for item in metadata.get("urls", [])
    }
    pending: list[Path] = []
    for artifact in artifacts:
        public_digest = public_digests.get(artifact.name)
        if public_digest is None:
            pending.append(artifact)
        elif public_digest != _sha256(artifact):
            raise ValueError("public_release_digest_mismatch")
    return tuple(pending)


def _fetch_public_release(version: str) -> dict[str, Any]:
    request = urllib.request.Request(
        PYPI_JSON.format(version=version), headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _fetch_public_release_if_present(version: str) -> dict[str, Any] | None:
    try:
        return _fetch_public_release(version)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def wait_for_public_release(
    version: str, artifacts: tuple[Path, Path], timeout_seconds: int
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            metadata = _fetch_public_release(version)
            verify_public_release(metadata, version, artifacts)
            return
        except PublicReleaseIncomplete:
            if time.monotonic() >= deadline:
                raise TimeoutError("public_release_incomplete") from None
        except urllib.error.HTTPError as exc:
            if exc.code != 404 or time.monotonic() >= deadline:
                raise
        if time.monotonic() >= deadline:
            raise TimeoutError("public_release_not_visible")
        time.sleep(5)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _run_smoke(
    command: list[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def qualify_public_install(version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="proofline-pypi-verify-") as temporary:
        root = Path(temporary)
        venv = root / "venv"
        env = os.environ.copy()
        for name in ("PROOFLINE_HOME", "PYTHONHOME", "PYTHONPATH"):
            env.pop(name, None)
        env["PROOFLINE_HOME"] = str(root / "proofline-home")
        _run_smoke([sys.executable, "-m", "venv", str(venv)], cwd=root, env=env)
        if os.name == "nt":
            python = venv / "Scripts/python.exe"
            proofline = venv / "Scripts/proofline.exe"
        else:
            python = venv / "bin/python"
            proofline = venv / "bin/proofline"
        _run_smoke(
            [
                str(python),
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-cache-dir",
                "--index-url",
                "https://pypi.org/simple",
                f"proofline=={version}",
            ],
            cwd=root,
            env=env,
        )
        observed = _run_smoke([str(proofline), "--version"], cwd=root, env=env)
        if observed.stdout.strip() != f"proofline {version}":
            raise ValueError("public_install_version_mismatch")
        _run_smoke(
            [
                str(proofline),
                "demo",
                "stale-decision",
                "--output-dir",
                str(root / "demo"),
            ],
            cwd=root,
            env=env,
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)

    artifacts = release_artifacts(args.dist_dir.resolve(), args.version)
    _run([sys.executable, "-m", "twine", "check", *(str(path) for path in artifacts)])
    pending = artifacts_to_upload(
        _fetch_public_release_if_present(args.version), args.version, artifacts
    )
    if pending:
        _run(
            [
                sys.executable,
                "-m",
                "twine",
                "upload",
                "--non-interactive",
                *(str(path) for path in pending),
            ]
        )
    wait_for_public_release(args.version, artifacts, args.timeout_seconds)
    qualify_public_install(args.version)
    print(
        json.dumps(
            {
                "artifacts": {path.name: _sha256(path) for path in artifacts},
                "status": "published_and_verified",
                "version": args.version,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
