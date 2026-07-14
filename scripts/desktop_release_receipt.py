#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import plistlib
import subprocess
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def wait_for_json(path: Path, process: subprocess.Popen[str]) -> dict[str, object]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError("frozen_sidecar_exited_before_readiness")
        time.sleep(0.05)
    raise RuntimeError("frozen_sidecar_readiness_timeout")


def smoke_sidecar(sidecar: Path, expected_version: str) -> dict[str, object]:
    observed_version = subprocess.run(
        [str(sidecar), "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if observed_version != f"proofline {expected_version}":
        raise RuntimeError("frozen_sidecar_version_mismatch")
    with tempfile.TemporaryDirectory(prefix="proofline-desktop-receipt-") as directory:
        root = Path(directory)
        ready_file = root / "ready.json"
        shutdown_file = root / "shutdown"
        process = subprocess.Popen(
            [
                str(sidecar),
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--data-dir",
                str(root / "state"),
                "--ready-file",
                str(ready_file),
                "--shutdown-file",
                str(shutdown_file),
                "--log-level",
                "warning",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            ready = wait_for_json(ready_file, process)
            if ready.get("host") != "127.0.0.1" or ready.get("version") != expected_version:
                raise RuntimeError("frozen_sidecar_readiness_mismatch")
            with urllib.request.urlopen(
                f"http://127.0.0.1:{ready['port']}/health", timeout=5
            ) as response:
                health = json.load(response)
            shutdown_file.write_text("shutdown\n", encoding="utf-8")
            process.wait(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        if process.returncode != 0:
            raise RuntimeError("frozen_sidecar_nonzero_shutdown")
        if ready_file.exists() or shutdown_file.exists():
            raise RuntimeError("frozen_sidecar_marker_cleanup_failed")
        return {
            "version": observed_version,
            "loopback_readiness": True,
            "health": health,
            "graceful_shutdown": True,
            "marker_cleanup": True,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    info_path = args.app / "Contents" / "Info.plist"
    sidecar = args.app / "Contents" / "MacOS" / "proofline-sidecar"
    if not info_path.is_file() or not sidecar.is_file() or not args.dmg.is_file():
        raise SystemExit("desktop bundle is incomplete")
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)
    if info.get("CFBundleShortVersionString") != args.expected_version:
        raise SystemExit("desktop bundle version mismatch")
    signature = subprocess.run(
        ["codesign", "-dv", "--verbose=4", str(args.app)],
        check=True,
        capture_output=True,
        text=True,
    ).stderr
    signature_kind = "adhoc" if "Signature=adhoc" in signature else "developer_id_or_other"
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    receipt = {
        "schema": "proofline.desktop-release-receipt.v1",
        "qualification": "experimental_macos_package_not_notarized",
        "observed_at": datetime.now(UTC).isoformat(),
        "proofline_revision": revision,
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
        },
        "bundle": {
            "identifier": info.get("CFBundleIdentifier"),
            "version": info.get("CFBundleShortVersionString"),
            "signature": signature_kind,
        },
        "artifact": {
            "name": args.dmg.name,
            "sha256": sha256_file(args.dmg),
        },
        "observations": smoke_sidecar(sidecar, args.expected_version),
        "does_not_prove": [
            "Apple notarization or trusted distribution signing",
            "native webview interaction or uninstall behavior",
            "Windows packaging or lifecycle behavior",
            "production readiness",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
