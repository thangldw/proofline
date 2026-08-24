#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from desktop_release_receipt import sha256_file, smoke_sidecar


def artifact(path: Path) -> dict[str, str | int]:
    return {"name": path.name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def windows_release_qualification(*, release_grade: bool, statuses: list[str]) -> str:
    if release_grade:
        if not statuses or any(status != "Valid" for status in statuses):
            raise RuntimeError("windows_release_qualification_failed")
        return "release_grade_windows_authenticode_signed"
    if statuses and all(status == "NotSigned" for status in statuses):
        return "experimental_windows_unsigned_not_for_distribution"
    return "experimental_windows_signature_present_not_release_qualified"


def authenticode_status(path: Path) -> str:
    powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if powershell is None:
        raise RuntimeError("authenticode_probe_powershell_missing")
    environment = dict(os.environ)
    environment["PROOFLINE_SIGNATURE_PATH"] = str(path)
    completed = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-AuthenticodeSignature -LiteralPath "
            "$env:PROOFLINE_SIGNATURE_PATH).Status.ToString()",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "no stderr"
        raise RuntimeError(f"authenticode_probe_failed:{path.name}:{detail}")
    status = completed.stdout.strip()
    if not status:
        raise RuntimeError(f"authenticode_probe_empty_status:{path.name}")
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--signed-executable", type=Path, required=True)
    parser.add_argument("--installer", type=Path, action="append", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-grade", action="store_true")
    args = parser.parse_args()
    if platform.system() != "Windows":
        raise SystemExit("Windows desktop qualification must run on a real Windows system")
    if any(not path.is_file() for path in [args.sidecar, args.signed_executable, *args.installer]):
        raise SystemExit("Windows desktop artifact is missing")
    signature_statuses = {
        path.name: authenticode_status(path) for path in [args.signed_executable, *args.installer]
    }
    qualification = windows_release_qualification(
        release_grade=args.release_grade,
        statuses=list(signature_statuses.values()),
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    receipt = {
        "schema": "proofline.windows-desktop-release-receipt.v1",
        "qualification": qualification,
        "observed_at": datetime.now(UTC).isoformat(),
        "proofline_revision": revision,
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "executable": artifact(args.signed_executable),
        "installers": [artifact(path) for path in args.installer],
        "authenticode": signature_statuses,
        "observations": smoke_sidecar(args.sidecar, args.expected_version),
        "does_not_prove": (
            ([] if args.release_grade else ["Authenticode signing"])
            + [
                "Microsoft SmartScreen reputation",
                "installer UI, uninstall, upgrade or rollback behavior",
                "production readiness",
            ]
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
