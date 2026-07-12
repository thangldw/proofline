from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ingestion import IngestionConflict, IngestionExecutionError, run_ingestion_job
from .models import Source
from .schemas import (
    FolderScanFileResult,
    FolderScanRequest,
    FolderScanResponse,
    SourceCreate,
)

SUPPORTED_SUFFIXES = {".md": "markdown", ".markdown": "markdown", ".txt": "text"}
MAX_IMPORT_BYTES = 5_000_000


class FolderScanError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _select_root(registered_roots: tuple[Path, ...], requested: str | None) -> Path:
    if not registered_roots:
        raise FolderScanError(
            "import_roots_disabled",
            "No import roots are registered. Configure PROOFLINE_IMPORT_ROOTS first.",
        )
    if requested is None:
        if len(registered_roots) != 1:
            raise FolderScanError(
                "import_root_required",
                "Select one of the registered import roots.",
            )
        root = registered_roots[0]
    else:
        try:
            root = Path(requested).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise FolderScanError(
                "import_root_not_registered", "The requested root is not registered."
            ) from exc
        if root not in registered_roots:
            raise FolderScanError(
                "import_root_not_registered",
                "The requested root is not registered.",
            )
    if not root.is_dir():
        raise FolderScanError(
            "import_root_unavailable", "The registered import root is unavailable."
        )
    return root


def _select_scan_path(root: Path, requested: str | None) -> Path:
    relative = Path(requested or ".")
    if relative.is_absolute():
        raise FolderScanError("scan_path_invalid", "The scan path must be relative to its root.")
    try:
        scan_path = (root / relative).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FolderScanError("scan_path_unavailable", "The scan path is unavailable.") from exc
    if not _is_within(scan_path, root):
        raise FolderScanError("scan_path_escape", "The scan path escapes its registered root.")
    if not scan_path.is_dir():
        raise FolderScanError("scan_path_not_directory", "The scan path must be a directory.")
    return scan_path


def _safe_file_uri(uri: str | None) -> Path | None:
    if not uri:
        return None
    try:
        parsed = urlparse(uri)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            return None
        return Path(unquote(parsed.path)).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _discover_files(root: Path, scan_path: Path) -> list[Path]:
    files: list[Path] = []
    for current, directories, names in os.walk(scan_path, followlinks=False):
        directories.sort()
        names.sort()
        current_path = Path(current)
        for name in names:
            candidate = current_path / name
            if candidate.suffix.casefold() in SUPPORTED_SUFFIXES:
                files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _failed_file(relative_path: str, code: str, *, uri: str | None = None) -> FolderScanFileResult:
    return FolderScanFileResult(
        relative_path=relative_path,
        uri=uri,
        status="failed",
        error_code=code,
    )


def _ingest_file(session: Session, root: Path, candidate: Path) -> FolderScanFileResult:
    relative_path = candidate.relative_to(root).as_posix()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return _failed_file(relative_path, "file_unavailable")
    if not _is_within(resolved, root):
        return _failed_file(relative_path, "file_symlink_escape")
    if not resolved.is_file():
        return _failed_file(relative_path, "file_not_regular")

    uri = resolved.as_uri()
    try:
        if resolved.stat().st_size > MAX_IMPORT_BYTES:
            return _failed_file(relative_path, "file_too_large", uri=uri)
        raw_content = resolved.read_bytes()
    except OSError:
        return _failed_file(relative_path, "file_read_failed", uri=uri)
    if len(raw_content) > MAX_IMPORT_BYTES:
        return _failed_file(relative_path, "file_too_large", uri=uri)
    try:
        content = raw_content.decode("utf-8")
    except UnicodeDecodeError:
        return _failed_file(relative_path, "file_encoding_invalid", uri=uri)
    if not content:
        return _failed_file(relative_path, "file_empty", uri=uri)

    existing = session.scalar(select(Source).where(Source.uri == uri))
    previous_version_id = existing.current_version_id if existing else None
    try:
        source, created, job = run_ingestion_job(
            session,
            SourceCreate(
                title=relative_path[:300],
                content=content,
                kind=SUPPORTED_SUFFIXES[candidate.suffix.casefold()],
                uri=uri,
            ),
        )
    except IngestionConflict as exc:
        result = _failed_file(relative_path, "source_identity_conflict", uri=uri)
        return result.model_copy(update={"job_id": exc.job_id})
    except IngestionExecutionError as exc:
        result = _failed_file(relative_path, "ingestion_error", uri=uri)
        return result.model_copy(update={"job_id": exc.job_id})

    file_status = (
        "created"
        if created
        else "unchanged"
        if source.current_version_id == previous_version_id
        else "updated"
    )
    return FolderScanFileResult(
        relative_path=relative_path,
        uri=uri,
        status=file_status,
        source_id=source.id,
        source_version_id=source.current_version_id,
        job_id=job.id,
    )


def scan_registered_folder(
    session: Session,
    payload: FolderScanRequest,
    registered_roots: tuple[Path, ...],
) -> FolderScanResponse:
    root = _select_root(registered_roots, payload.root)
    scan_path = _select_scan_path(root, payload.path)
    candidates = _discover_files(root, scan_path)
    files = [_ingest_file(session, root, candidate) for candidate in candidates]
    discovered_uris = {item.uri for item in files if item.uri is not None}

    missing_source_ids: list[str] = []
    sources = session.scalars(select(Source).where(Source.uri.is_not(None))).all()
    for source in sources:
        source_path = _safe_file_uri(source.uri)
        if source_path and _is_within(source_path, scan_path) and source.uri not in discovered_uris:
            missing_source_ids.append(source.id)
    missing_source_ids.sort()

    counts = {
        status: sum(item.status == status for item in files)
        for status in ("created", "updated", "unchanged", "failed")
    }
    return FolderScanResponse(
        root=str(root),
        path=scan_path.relative_to(root).as_posix() or ".",
        delete_missing_requested=payload.delete_missing,
        discovered_count=len(files),
        created_count=counts["created"],
        updated_count=counts["updated"],
        unchanged_count=counts["unchanged"],
        failed_count=counts["failed"],
        missing_count=len(missing_source_ids),
        missing_source_ids=missing_source_ids,
        files=files,
    )
