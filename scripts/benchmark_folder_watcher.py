#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import tempfile
import time
import tracemalloc
from pathlib import Path

from proofline.database import initialize_database, make_engine
from proofline.folder_scanning import FolderScanCoordinator
from proofline.schemas import FolderScanRequest
from sqlalchemy.orm import Session


def timed_scan(engine, coordinator: FolderScanCoordinator, root: Path) -> tuple[float, object]:
    started = time.perf_counter()
    with Session(engine) as session:
        report = coordinator.scan(session, FolderScanRequest(root=str(root)), (root,))
    return (time.perf_counter() - started) * 1000, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=1_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.files < 1:
        raise SystemExit("--files must be positive")

    with tempfile.TemporaryDirectory(prefix="proofline-watcher-benchmark-") as temporary:
        root = Path(temporary) / "sources"
        root.mkdir()
        root = root.resolve()
        for index in range(args.files):
            (root / f"adr-{index:05d}.md").write_text(
                f"# ADR {index}\n\nDecision: Keep watcher fixture {index} local.\n",
                encoding="utf-8",
            )
        database = Path(temporary) / "benchmark.db"
        engine = make_engine(f"sqlite:///{database}")
        initialize_database(engine)
        coordinator = FolderScanCoordinator()
        tracemalloc.start()
        initial_ms, initial = timed_scan(engine, coordinator, root)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        no_op_samples = [timed_scan(engine, coordinator, root) for _index in range(3)]
        no_op_ms = sorted(sample[0] for sample in no_op_samples)[1]
        no_op = no_op_samples[1][1]
        (root / "adr-00000.md").write_text(
            "# ADR 0\n\nDecision: Keep updated watcher fixture zero local.\n",
            encoding="utf-8",
        )
        update_ms, update = timed_scan(engine, coordinator, root)
        receipt = {
            "schema": "proofline-folder-watcher-benchmark-v1",
            "dataset": "synthetic-generated-no-private-source-content",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "file_count": args.files,
            "initial_latency_ms": initial_ms,
            "initial_created_count": initial.created_count,
            "no_op_latency_ms": no_op_ms,
            "no_op_latency_samples_ms": [sample[0] for sample in no_op_samples],
            "no_op_unchanged_count": no_op.unchanged_count,
            "single_update_latency_ms": update_ms,
            "single_update_count": update.updated_count,
            "peak_python_memory_bytes": peak,
            "database_bytes": database.stat().st_size,
            "decision_rule": (
                "retain polling when a 1000-file no-op cycle remains below 1000 ms; "
                "otherwise evaluate native notifications"
            ),
            "qualification": (
                "synthetic local benchmark; does not establish Windows behavior, network "
                "filesystem behavior, or production scale"
            ),
        }
        engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
