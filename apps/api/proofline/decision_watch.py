from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from .decision_health import check_decision_health
from .workspace_sync import discover_documents, sync_folder

Fingerprint = frozenset[tuple[str, int, int]]


def folder_fingerprint(root: Path) -> Fingerprint:
    """Cheap change detector: (relative path, mtime_ns, size) for every indexable document."""

    resolved = root.resolve()
    entries: set[tuple[str, int, int]] = set()
    for path in discover_documents(resolved):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.add((str(path.relative_to(resolved)), stat.st_mtime_ns, stat.st_size))
    return frozenset(entries)


def watch_folder(
    session_factory: Callable[[], Session],
    folder: Path,
    *,
    uri_root: str | None = None,
    interval: float = 2.0,
    max_cycles: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    emit: Callable[[str], None] = print,
) -> int:
    """Re-sync when documents change and report decisions that became stale or recovered.

    Returns the number of syncs performed. Stops after `max_cycles` polls (None = forever).
    """

    previous: Fingerprint | None = None
    known: set[tuple[str, str]] = set()
    syncs = 0
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        cycle += 1
        current = folder_fingerprint(folder)
        if current != previous:
            with session_factory() as session:
                summary = sync_folder(session, folder, uri_root=uri_root)
                session.commit()
                findings = check_decision_health(session)
            syncs += 1
            emit(
                f"synced: {summary.created} created, {summary.updated} updated, "
                f"{summary.unchanged} unchanged, {len(summary.failed)} failed"
            )
            now = {(item.decision_id, item.reason) for item in findings}
            by_key = {(item.decision_id, item.reason): item for item in findings}
            for key in sorted(now - known):
                item = by_key[key]
                emit(f"STALE ({item.reason}): {item.decision_title} at {item.locator}")
            for decision_id, reason in sorted(known - now):
                emit(f"recovered ({reason}): {decision_id[:8]}")
            known = now
            previous = current
        if max_cycles is None or cycle < max_cycles:
            sleep(interval)
    return syncs
