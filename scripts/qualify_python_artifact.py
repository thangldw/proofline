#!/usr/bin/env python3
"""Install and qualify one Proofline wheel or sdist outside the repository."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def _ephemeral_windows_key(
    python: Path,
    private_key: Path,
    public_key: Path,
    cwd: Path,
    env: dict[str, str],
) -> None:
    program = """
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import sys
key = Ed25519PrivateKey.generate()
Path(sys.argv[1]).write_bytes(key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
))
Path(sys.argv[2]).write_bytes(key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
))
"""
    _run([str(python), "-c", program, str(private_key), str(public_key)], cwd=cwd, env=env)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--python", default=sys.executable, type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix="proofline-artifact-qualification.") as temporary:
        root = Path(temporary)
        venv = root / "venv"
        subprocess.run([str(args.python), "-m", "venv", str(venv)], check=True)
        scripts = venv / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        proofline = scripts / ("proofline.exe" if os.name == "nt" else "proofline")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PROOFLINE_HOME"] = str(root / "home")
        _run([str(python), "-m", "pip", "install", "--quiet", str(artifact)], cwd=root, env=env)
        _run([str(python), "-m", "pip", "check"], cwd=root, env=env)
        version = _run([str(proofline), "--version"], cwd=root, env=env).stdout.strip()
        if version != f"proofline {args.expected_version}":
            raise SystemExit("artifact qualification failed: version_mismatch")

        demo = root / "demo"
        _run(
            [str(proofline), "demo", "stale-decision", "--output-dir", str(demo)],
            cwd=root,
            env=env,
        )
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        if hasattr(os, "fchmod"):
            _run(
                [
                    str(proofline),
                    "generate-attestation-key",
                    "--private-key",
                    str(private_key),
                    "--public-key",
                    str(public_key),
                ],
                cwd=root,
                env=env,
            )
            keygen_mode = "proofline-owner-mode"
        else:
            unsupported = subprocess.run(
                [
                    str(proofline),
                    "generate-attestation-key",
                    "--private-key",
                    str(private_key),
                    "--public-key",
                    str(public_key),
                ],
                cwd=root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if (
                unsupported.returncode == 0
                or "secure_permissions_unsupported" not in unsupported.stderr
                or private_key.exists()
                or public_key.exists()
            ):
                raise SystemExit("artifact qualification failed: insecure_keygen_contract")
            _ephemeral_windows_key(python, private_key, public_key, root, env)
            keygen_mode = "expected-unsupported-then-ephemeral-platform-key"
        attestation = root / "attestation.json"
        _run(
            [
                str(proofline),
                "attest",
                "--package",
                str(demo / "evidence.zip"),
                "--review-receipt",
                str(demo / "decision-review.json"),
                "--private-key",
                str(private_key),
                "--output",
                str(attestation),
            ],
            cwd=root,
            env=env,
        )
        verified = _run(
            [
                str(proofline),
                "verify-attestation",
                str(attestation),
                "--public-key",
                str(public_key),
                "--package",
                str(demo / "evidence.zip"),
                "--review-receipt",
                str(demo / "decision-review.json"),
            ],
            cwd=root,
            env=env,
        )
        if json.loads(verified.stdout)["valid"] is not True:
            raise SystemExit("artifact qualification failed: attestation_invalid")
        print(
            json.dumps(
                {
                    "artifact": artifact.name,
                    "keygen_mode": keygen_mode,
                    "status": "qualified",
                    "version": args.expected_version,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
