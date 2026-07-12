from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from .folder_scanning import FolderScanCoordinator, FolderScanError
from .models import utc_now
from .schemas import FolderScanRequest, FolderScanResponse


@dataclass(frozen=True)
class FolderWatchSnapshot:
    enabled: bool
    running: bool
    scan_in_progress: bool
    interval_seconds: int
    registered_root_count: int
    completed_cycles: int
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_error_code: str | None
    last_root_error_count: int
    last_discovered_count: int
    last_created_count: int
    last_updated_count: int
    last_unchanged_count: int
    last_renamed_count: int
    last_failed_count: int
    last_missing_count: int


class FolderWatcher:
    """Single-process, sequential polling for explicitly registered roots."""

    def __init__(
        self,
        database_engine: Engine,
        registered_roots: tuple[Path, ...],
        interval_seconds: int,
        scan_coordinator: FolderScanCoordinator | None = None,
    ) -> None:
        self._engine = database_engine
        self._roots = registered_roots
        self._interval_seconds = interval_seconds
        self._scan_coordinator = scan_coordinator or FolderScanCoordinator()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._lock = Lock()
        self._state = FolderWatchSnapshot(
            enabled=interval_seconds > 0,
            running=False,
            scan_in_progress=False,
            interval_seconds=interval_seconds,
            registered_root_count=len(registered_roots),
            completed_cycles=0,
            last_started_at=None,
            last_completed_at=None,
            last_error_code=None,
            last_root_error_count=0,
            last_discovered_count=0,
            last_created_count=0,
            last_updated_count=0,
            last_unchanged_count=0,
            last_renamed_count=0,
            last_failed_count=0,
            last_missing_count=0,
        )

    def snapshot(self) -> FolderWatchSnapshot:
        with self._lock:
            return self._state

    def _update(self, **changes: object) -> None:
        with self._lock:
            values = asdict(self._state)
            values.update(changes)
            self._state = FolderWatchSnapshot(**values)

    async def start(self) -> None:
        if not self.snapshot().enabled or self._task is not None:
            return
        self._stop.clear()
        self._update(running=True)
        self._task = asyncio.create_task(self._run(), name="proofline-folder-watcher")

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._stop.set()
        await task
        self._task = None

    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                await self._scan_cycle()
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._interval_seconds)
                except TimeoutError:
                    pass
        finally:
            self._update(running=False, scan_in_progress=False)

    async def _scan_cycle(self) -> None:
        self._update(scan_in_progress=True, last_started_at=utc_now(), last_error_code=None)
        totals = {
            "last_discovered_count": 0,
            "last_created_count": 0,
            "last_updated_count": 0,
            "last_unchanged_count": 0,
            "last_renamed_count": 0,
            "last_failed_count": 0,
            "last_missing_count": 0,
        }
        error_code: str | None = None
        root_error_count = 0
        try:
            if not self._roots:
                error_code = "import_roots_disabled"
                root_error_count = 1
            for root in self._roots:
                try:
                    report = await asyncio.to_thread(self._scan_root, root)
                except FolderScanError as exc:
                    error_code = error_code or exc.code
                    root_error_count += 1
                    continue
                except Exception:
                    # Never expose exception text, file contents, or registered paths.
                    error_code = error_code or "folder_watch_scan_failed"
                    root_error_count += 1
                    continue
                totals["last_discovered_count"] += report.discovered_count
                totals["last_created_count"] += report.created_count
                totals["last_updated_count"] += report.updated_count
                totals["last_unchanged_count"] += report.unchanged_count
                totals["last_renamed_count"] += report.renamed_count
                totals["last_failed_count"] += report.failed_count
                totals["last_missing_count"] += report.missing_count
        finally:
            current = self.snapshot()
            self._update(
                **totals,
                completed_cycles=current.completed_cycles + 1,
                last_completed_at=utc_now(),
                last_error_code=error_code,
                last_root_error_count=root_error_count,
                scan_in_progress=False,
            )

    def _scan_root(self, root: Path) -> FolderScanResponse:
        # A watcher cycle never confirms deletion. Missing files stay visible as a preview.
        payload = FolderScanRequest(root=str(root), delete_missing=False)
        with Session(self._engine) as session:
            return self._scan_coordinator.scan(session, payload, self._roots)
