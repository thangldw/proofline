from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ingestion import (
    IngestionConflict,
    IngestionExecutionError,
    delete_source,
    run_ingestion_job,
)
from .models import AuditEvent, Source, SourceVersion, utc_now
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


@dataclass(frozen=True)
class PreparedFile:
    relative_path: str
    uri: str
    kind: str
    content: str
    content_hash: str


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


def _prepare_file(root: Path, candidate: Path) -> PreparedFile | FolderScanFileResult:
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

    return PreparedFile(
        relative_path=relative_path,
        uri=uri,
        kind=SUPPORTED_SUFFIXES[candidate.suffix.casefold()],
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _ingest_prepared_file(session: Session, prepared: PreparedFile) -> FolderScanFileResult:
    relative_path = prepared.relative_path
    uri = prepared.uri

    existing = session.scalar(select(Source).where(Source.uri == uri))
    previous_version_id = existing.current_version_id if existing else None
    try:
        source, created, job = run_ingestion_job(
            session,
            SourceCreate(
                title=relative_path[:300],
                content=prepared.content,
                kind=prepared.kind,
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


def _rename_source(
    session: Session, source: Source, prepared: PreparedFile
) -> FolderScanFileResult:
    previous_uri = source.uri
    before = {
        "uri": source.uri,
        "title": source.title,
        "kind": source.kind,
        "current_version_id": source.current_version_id,
    }
    source.uri = prepared.uri
    source.title = prepared.relative_path[:300]
    source.kind = prepared.kind
    source.indexed_at = utc_now()
    session.add(
        AuditEvent(
            action="source.renamed",
            object_type="source",
            object_id=source.id,
            before_json=before,
            after_json={
                "uri": source.uri,
                "title": source.title,
                "kind": source.kind,
                "current_version_id": source.current_version_id,
            },
        )
    )
    session.commit()
    return FolderScanFileResult(
        relative_path=prepared.relative_path,
        uri=prepared.uri,
        previous_uri=previous_uri,
        status="renamed",
        source_id=source.id,
        source_version_id=source.current_version_id,
        job_id=None,
    )


def scan_registered_folder(
    session: Session,
    payload: FolderScanRequest,
    registered_roots: tuple[Path, ...],
) -> FolderScanResponse:
    root = _select_root(registered_roots, payload.root)
    scan_path = _select_scan_path(root, payload.path)
    candidates = _discover_files(root, scan_path)
    prepared_items = [_prepare_file(root, candidate) for candidate in candidates]
    discovered_uris = {item.uri for item in prepared_items if item.uri is not None}

    sources = list(session.scalars(select(Source).where(Source.uri.is_not(None))).all())
    sources_by_uri: dict[str, list[Source]] = {}
    missing_sources_by_hash: dict[str, list[Source]] = {}
    for source in sources:
        sources_by_uri.setdefault(source.uri, []).append(source)
        source_path = _safe_file_uri(source.uri)
        if not source_path or not _is_within(source_path, scan_path):
            continue
        if source.uri in discovered_uris:
            continue
        version = session.get(SourceVersion, source.current_version_id)
        if version:
            missing_sources_by_hash.setdefault(version.content_hash, []).append(source)

    new_files_by_hash: dict[str, list[PreparedFile]] = {}
    for item in prepared_items:
        if isinstance(item, PreparedFile) and item.uri not in sources_by_uri:
            new_files_by_hash.setdefault(item.content_hash, []).append(item)

    rename_source_by_uri: dict[str, Source] = {}
    for content_hash, new_files in new_files_by_hash.items():
        missing_sources = missing_sources_by_hash.get(content_hash, [])
        if len(new_files) == 1 and len(missing_sources) == 1:
            rename_source_by_uri[new_files[0].uri] = missing_sources[0]

    files: list[FolderScanFileResult] = []
    for item in prepared_items:
        if isinstance(item, FolderScanFileResult):
            files.append(item)
            continue
        rename_source = rename_source_by_uri.get(item.uri)
        files.append(
            _rename_source(session, rename_source, item)
            if rename_source
            else _ingest_prepared_file(session, item)
        )

    missing_source_ids: list[str] = []
    for source in sources:
        source_path = _safe_file_uri(source.uri)
        if source_path and _is_within(source_path, scan_path) and source.uri not in discovered_uris:
            missing_source_ids.append(source.id)
    missing_source_ids.sort()

    counts = {
        status: sum(item.status == status for item in files)
        for status in ("created", "updated", "unchanged", "renamed", "failed")
    }
    deletion_mode = "preview_only"
    deleted_count = 0
    confirmed_ids = payload.confirmed_missing_source_ids
    if confirmed_ids is not None:
        if not payload.delete_missing:
            raise FolderScanError(
                "missing_confirmation_without_delete",
                "Confirmed missing IDs require delete_missing=true.",
            )
        if (
            not confirmed_ids
            or any(not item for item in confirmed_ids)
            or len(set(confirmed_ids)) != len(confirmed_ids)
        ):
            raise FolderScanError(
                "missing_confirmation_invalid",
                "Confirmed missing source IDs are invalid.",
            )
        confirmed_sources = {
            source.id: source for source in sources if source.id in set(confirmed_ids)
        }
        if len(confirmed_sources) != len(confirmed_ids):
            raise FolderScanError(
                "missing_confirmation_invalid",
                "Confirmed missing source IDs are not owned by this scan.",
            )
        if any(
            not (source_path := _safe_file_uri(source.uri))
            or not _is_within(source_path, scan_path)
            for source in confirmed_sources.values()
        ):
            raise FolderScanError(
                "missing_confirmation_invalid",
                "Confirmed missing source IDs are not owned by this scan.",
            )
        if counts["failed"]:
            raise FolderScanError(
                "missing_deletion_scan_failed",
                "Missing sources were not deleted because the scan reported failures.",
            )
        if sorted(confirmed_ids) != missing_source_ids:
            raise FolderScanError(
                "missing_confirmation_mismatch",
                "The confirmed missing source set no longer matches the current scan.",
            )
        if any(
            (source_path := _safe_file_uri(source.uri)) is None or source_path.exists()
            for source in confirmed_sources.values()
        ):
            raise FolderScanError(
                "missing_confirmation_mismatch",
                "The confirmed missing source set no longer matches the current scan.",
            )
        try:
            for source_id in missing_source_ids:
                delete_source(session, confirmed_sources[source_id], commit=False)
            session.commit()
        except Exception as exc:
            session.rollback()
            raise FolderScanError(
                "missing_deletion_failed",
                "Confirmed missing sources could not be deleted.",
            ) from exc
        deletion_mode = "confirmed_delete"
        deleted_count = len(missing_source_ids)
    return FolderScanResponse(
        root=str(root),
        path=scan_path.relative_to(root).as_posix() or ".",
        delete_missing_requested=payload.delete_missing,
        deletion_mode=deletion_mode,
        deleted_count=deleted_count,
        discovered_count=len(files),
        created_count=counts["created"],
        updated_count=counts["updated"],
        unchanged_count=counts["unchanged"],
        renamed_count=counts["renamed"],
        failed_count=counts["failed"],
        missing_count=len(missing_source_ids),
        missing_source_ids=missing_source_ids,
        files=files,
    )
