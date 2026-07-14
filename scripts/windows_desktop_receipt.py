#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from desktop_release_receipt import sha256_file, smoke_sidecar


def artifact(path: Path) -> dict[str, str | int]:
    return {"name": path.name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--installer", type=Path, action="append", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Windows":
        raise SystemExit("Windows desktop qualification must run on a real Windows system")
    if any(not path.is_file() for path in [args.sidecar, *args.installer]):
        raise SystemExit("Windows desktop artifact is missing")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    receipt = {
        "schema": "proofline.windows-desktop-release-receipt.v1",
        "qualification": "real_windows_unsigned_installer_build",
        "observed_at": datetime.now(UTC).isoformat(),
        "proofline_revision": revision,
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "installers": [artifact(path) for path in args.installer],
        "observations": smoke_sidecar(args.sidecar, args.expected_version),
        "does_not_prove": [
            "Authenticode signing or reputation",
            "installer UI, uninstall, upgrade or rollback behavior",
            "production readiness",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
