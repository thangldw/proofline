"""Measure folder sync and decision checks on a synthetic Markdown workspace."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from .database import initialize_database, make_engine
from .decision_health import check_decision_health
from .models import Decision
from .workspace_sync import sync_folder

URI_ROOT = "file:///benchmark/docs"


def _document(index: int, revision: int) -> str:
    return (
        f"# Service {index:06d}\n\n"
        f"Decision: use queue profile {index % 97:02d} revision {revision}.\n"
        f"Reason: synthetic load bucket {index % 211:03d}.\n"
    )


def _write_documents(root: Path, count: int, *, revision: int, only: range | None = None) -> None:
    for index in only if only is not None else range(count):
        directory = root / f"group-{index // 500:04d}"
        directory.mkdir(exist_ok=True)
        (directory / f"doc-{index:06d}.md").write_text(_document(index, revision), encoding="utf-8")


def _timed(function: Any) -> tuple[Any, float]:
    started = time.perf_counter()
    result = function()
    return result, round(time.perf_counter() - started, 4)


def benchmark_workspace_sync(documents: int, *, changed_fraction: float = 0.01) -> dict[str, Any]:
    if isinstance(documents, bool) or documents < 1:
        raise ValueError("documents must be a positive integer")
    if not 0 < changed_fraction <= 1:
        raise ValueError("changed_fraction must be in (0, 1]")
    changed = max(1, int(documents * changed_fraction))
    with tempfile.TemporaryDirectory(prefix="proofline-workspace-bench-") as temporary:
        base = Path(temporary)
        docs = base / "docs"
        docs.mkdir()
        _write_documents(docs, documents, revision=1)
        engine = make_engine(f"sqlite:///{base / 'bench.db'}")
        try:
            initialize_database(engine)
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            with factory() as session:
                first, initial_seconds = _timed(
                    lambda: sync_folder(session, docs, uri_root=URI_ROOT)
                )
                session.execute(update(Decision).values(status="accepted"))
                session.commit()
            with factory() as session:
                _, unchanged_seconds = _timed(lambda: sync_folder(session, docs, uri_root=URI_ROOT))
            _write_documents(docs, documents, revision=2, only=range(changed))
            with factory() as session:
                _, changed_seconds = _timed(lambda: sync_folder(session, docs, uri_root=URI_ROOT))
            with factory() as session:
                findings, check_seconds = _timed(lambda: check_decision_health(session))
        finally:
            engine.dispose()
    return {
        "documents": documents,
        "changed_documents": changed,
        "initial_sync_seconds": initial_seconds,
        "unchanged_resync_seconds": unchanged_seconds,
        "changed_resync_seconds": changed_seconds,
        "check_decisions_seconds": check_seconds,
        "documents_per_second_initial": round(documents / max(initial_seconds, 1e-9), 1),
        "findings": len(findings),
        "created": first.created,
    }
