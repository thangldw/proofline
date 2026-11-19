"""Headless, deterministic sync of a document folder into the local Proofline database.

Used by CI: restore a committed snapshot, sync the checked-out documents under the URI root the
snapshot was created with, then run ``check-decisions``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from .folder_scanning import SUPPORTED_SUFFIXES, PreparedFile, _ingest_prepared_file, _prepare_file
from .schemas import DEFAULT_WORKSPACE_ID

IGNORED_DIRECTORIES = frozenset({"node_modules", "__pycache__", "venv"})


class WorkspaceSyncError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class SyncSummary:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: list[dict[str, str]] = field(default_factory=list)

    def model_dump(self) -> dict[str, object]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "failed": self.failed,
        }


def validate_uri_root(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"} or not parsed.path:
        raise WorkspaceSyncError("uri_root_invalid")
    return value


def discover_documents(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if not name.startswith(".") and name not in IGNORED_DIRECTORIES
        )
        for name in sorted(names):
            candidate = Path(current) / name
            if not name.startswith(".") and candidate.suffix.casefold() in SUPPORTED_SUFFIXES:
                files.append(candidate)
    return files


def sync_folder(
    session: Session,
    folder: Path,
    *,
    uri_root: str | None = None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> SyncSummary:
    try:
        root = folder.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceSyncError("folder_unavailable") from exc
    if not root.is_dir():
        raise WorkspaceSyncError("folder_unavailable")
    if uri_root is not None:
        uri_root = validate_uri_root(uri_root)
    summary = SyncSummary()
    for candidate in discover_documents(root):
        prepared = _prepare_file(root, candidate, uri_root=uri_root)
        if not isinstance(prepared, PreparedFile):
            summary.failed.append(
                {"path": prepared.relative_path, "code": prepared.error_code or "failed"}
            )
            continue
        result = _ingest_prepared_file(session, prepared, workspace_id)
        if result.status == "created":
            summary.created += 1
        elif result.status == "updated":
            summary.updated += 1
        elif result.status == "unchanged":
            summary.unchanged += 1
        else:
            summary.failed.append(
                {"path": result.relative_path, "code": result.error_code or "failed"}
            )
    return summary
