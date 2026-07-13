#!/usr/bin/env python3
"""Qualify one installed release artifact on the current local platform."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "proofline.platform-release-qualification.v1"

KEYRING_QUALIFICATION = r"""
import json
import secrets
import tempfile
from pathlib import Path

import keyring
from proofline.secret_store import OSKeyringSecretStore

with tempfile.TemporaryDirectory(prefix="proofline-keyring-qualification-") as directory:
    store = OSKeyringSecretStore(Path(directory) / "providers.json")
    account = "release_qualification"
    expected = secrets.token_urlsafe(32)
    store.set(account, expected)
    try:
        if store.get(account) != expected:
            raise RuntimeError("OS keyring round trip failed")
    finally:
        store.delete(account)
    if store.get(account) is not None:
        raise RuntimeError("OS keyring deletion failed")
    backend = keyring.get_keyring()
    print(json.dumps({
        "status": "ok",
        "backend": f"{type(backend).__module__}.{type(backend).__name__}",
        "set_read_delete": True,
    }))
"""


def run_json(command: list[str], *, env: dict[str, str] | None = None) -> dict:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict) or payload.get("status") not in {"ok", None}:
        raise RuntimeError("qualification command returned an invalid result")
    return payload


def git_revision(repository: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def artifact_identity(path: Path) -> dict[str, str | int]:
    content = path.read_bytes()
    return {
        "name": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def qualify_os_keyring(python: Path) -> dict:
    return run_json([str(python), "-c", KEYRING_QUALIFICATION])


def write_receipt(path: Path, receipt: dict, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="platform-release-", suffix=".json", dir=path.parent
    )
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proofline", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qualify-os-keyring", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    observed_version = subprocess.check_output(
        [str(args.proofline), "--version"], text=True
    ).strip()
    expected_output = f"proofline {args.expected_version}"
    if observed_version != expected_output:
        raise RuntimeError(
            "installed version mismatch: "
            f"observed {observed_version!r}, expected {expected_output!r}"
        )

    lifecycle = run_json(
        [
            str(args.python),
            str(repository / "scripts/installed_server_smoke.py"),
            "--proofline",
            str(args.proofline),
        ]
    )
    recovery = run_json([str(args.python), str(repository / "scripts/platform_smoke.py")])
    with tempfile.TemporaryDirectory(prefix="proofline-release-integrity-") as directory:
        environment = dict(os.environ)
        environment["PROOFLINE_HOME"] = str(Path(directory) / "state")
        environment["PROOFLINE_AI_PROVIDER"] = "disabled"
        environment["PROOFLINE_EMBEDDING_PROVIDER"] = "disabled"
        environment["PROOFLINE_ALLOW_REMOTE_AI"] = "false"
        subprocess.run(
            [str(args.proofline), "seed"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        integrity = run_json([str(args.proofline), "verify-integrity"], env=environment)

    system = platform.system()
    os_keyring = (
        qualify_os_keyring(args.python) if args.qualify_os_keyring else {"status": "not_run"}
    )
    receipt = {
        "schema_version": SCHEMA,
        "observed_at": datetime.now(UTC).isoformat(),
        "status": "ok",
        "proofline_version": args.expected_version,
        "proofline_revision": git_revision(repository),
        "artifact": artifact_identity(args.artifact),
        "environment": {
            "system": system,
            "release": platform.mac_ver()[0] if system == "Darwin" else platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "lifecycle": lifecycle,
        "recovery": recovery,
        "integrity": integrity,
        "os_keyring": os_keyring,
        "qualification": (
            f"Installed-release qualification for {system} {platform.machine()} only. "
            "It proves local lifecycle, bundled web, deterministic portability, backup restore/"
            "rollback and "
            + ("OS keyring set/read/delete, " if args.qualify_os_keyring else "")
            + "integrity behavior for the identified artifact; it does not qualify another OS, "
            "native installer signing, real-model quality, external pilots or production support."
        ),
    }
    write_receipt(args.output, receipt, force=args.force)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
