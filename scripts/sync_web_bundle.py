#!/usr/bin/env python3
"""Synchronize the reviewed Vite build into the Python package."""

from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def relative_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


def bundles_match(source: Path, target: Path) -> bool:
    source_files = relative_files(source)
    if source_files != relative_files(target):
        return False
    return all(filecmp.cmp(source / path, target / path, shallow=False) for path in source_files)


def sync_bundle(source: Path, target: Path) -> None:
    if not (source / "index.html").is_file():
        raise SystemExit("web bundle sync failed: apps/web/dist/index.html is missing")
    temporary = target.with_name(f"{target.name}.tmp")
    shutil.rmtree(temporary, ignore_errors=True)
    shutil.copytree(source, temporary)
    if target.exists():
        shutil.rmtree(target)
    temporary.replace(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = repository_root()
    source = root / "apps" / "web" / "dist"
    target = root / "apps" / "api" / "proofline" / "web"
    if args.check:
        if not bundles_match(source, target):
            raise SystemExit(
                "bundled web UI is stale; run `make sync-web-bundle` after `npm run build:web`"
            )
        print("Bundled web UI matches apps/web/dist.")
        return
    sync_bundle(source, target)
    print(f"Synchronized {len(relative_files(target))} web files.")


if __name__ == "__main__":
    main()
