from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "apps" / "desktop"


def rust_host_triple() -> str:
    commands: list[list[str]] = [["rustc", "-vV"]]
    try:
        rustc_path = subprocess.run(
            ["rustup", "which", "rustc"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    else:
        commands.append([rustc_path, "-vV"])
    for command in commands:
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        for line in result.stdout.splitlines():
            if line.startswith("host: "):
                return line.removeprefix("host: ").strip()
    raise RuntimeError("rust_host_triple_unavailable")


def sidecar_destination(target_triple: str) -> Path:
    suffix = ".exe" if "windows" in target_triple else ""
    return DESKTOP / "src-tauri" / "binaries" / f"proofline-sidecar-{target_triple}{suffix}"


def build_sidecar(target_triple: str) -> Path:
    build_root = ROOT / "build" / "desktop-sidecar" / target_triple
    dist_dir = build_root / "dist"
    work_dir = build_root / "work"
    spec_dir = build_root / "spec"
    shutil.rmtree(build_root, ignore_errors=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "proofline-sidecar",
        "--paths",
        str(ROOT / "apps" / "api"),
        "--collect-data",
        "proofline",
        "--collect-submodules",
        "keyring.backends",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        str(DESKTOP / "sidecar_entry.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    built_name = "proofline-sidecar.exe" if os.name == "nt" else "proofline-sidecar"
    built = dist_dir / built_name
    if not built.is_file():
        raise RuntimeError("pyinstaller_sidecar_missing")
    destination = sidecar_destination(target_triple)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, destination)
    destination.chmod(destination.stat().st_mode | 0o111)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the current-platform Tauri sidecar")
    parser.add_argument("--target", help="Rust target triple; defaults to the active Rust host")
    args = parser.parse_args()
    target = args.target or rust_host_triple()
    if ("windows" in target) != (os.name == "nt"):
        raise SystemExit("sidecar build must run on the target operating system")
    destination = build_sidecar(target)
    print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
