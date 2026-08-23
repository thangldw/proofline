#!/usr/bin/env python3
"""Fail-closed inspection for Python release archives."""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

MAX_MEMBER_BYTES = 64 * 1024 * 1024
FORBIDDEN_COMPONENTS = {
    ".hypothesis",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".worktrees",
    "__pycache__",
    "node_modules",
}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".key",
    ".pyc",
    ".sqlite",
    ".sqlite3",
    ".tsbuildinfo",
}
FORBIDDEN_NAMES = {".env", "proofline.db"}
FORBIDDEN_DATABASE_ENDINGS = (
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".sqlite-journal",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3-journal",
    ".sqlite3-shm",
    ".sqlite3-wal",
)
PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"-----BEGIN PGP PRIVATE KEY BLOCK-----",
)


class ReleaseArtifactError(RuntimeError):
    pass


def _validate_member(name: str, data: bytes) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ReleaseArtifactError("archive_path_invalid")
    if any(part in FORBIDDEN_COMPONENTS for part in path.parts):
        raise ReleaseArtifactError("local_build_state")
    lower_name = path.name.lower()
    if (
        lower_name in FORBIDDEN_NAMES
        or lower_name.startswith(".env.")
        or path.suffix.lower() in FORBIDDEN_SUFFIXES
        or lower_name.endswith(FORBIDDEN_DATABASE_ENDINGS)
    ):
        raise ReleaseArtifactError("local_build_state")
    if path.suffix.lower() == ".pem" and "public" not in path.name.lower():
        raise ReleaseArtifactError("key_file_forbidden")
    if any(marker in data for marker in PRIVATE_KEY_MARKERS):
        raise ReleaseArtifactError("private_key_material")


def _zip_members(path: Path) -> Iterator[tuple[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            if member.file_size > MAX_MEMBER_BYTES:
                raise ReleaseArtifactError("archive_member_too_large")
            yield member.filename, archive.read(member)


def _tar_members(path: Path) -> Iterator[tuple[str, bytes]]:
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise ReleaseArtifactError("archive_link_forbidden")
            if not member.isfile():
                continue
            if member.size > MAX_MEMBER_BYTES:
                raise ReleaseArtifactError("archive_member_too_large")
            handle = archive.extractfile(member)
            if handle is None:
                raise ReleaseArtifactError("archive_unreadable")
            yield member.name, handle.read()


def verify_artifact(path: Path) -> int:
    if path.suffix == ".whl":
        members = _zip_members(path)
    elif path.name.endswith(".tar.gz"):
        members = _tar_members(path)
    else:
        raise ReleaseArtifactError("archive_type_unsupported")
    count = 0
    try:
        for name, data in members:
            _validate_member(name, data)
            count += 1
    except ReleaseArtifactError:
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ReleaseArtifactError("archive_unreadable") from exc
    if count == 0:
        raise ReleaseArtifactError("archive_empty")
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        counts = {path.name: verify_artifact(path) for path in args.artifacts}
    except ReleaseArtifactError as exc:
        print(f"release artifact verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps({"status": "valid", "files": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
