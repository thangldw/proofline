#!/usr/bin/env python3
"""Benchmark `proofline sync` and `check-decisions` on a synthetic Markdown workspace."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from proofline.portability import PortabilityError, atomic_write_export
from proofline.workspace_benchmark import benchmark_workspace_sync


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", type=int, default=5000)
    parser.add_argument("--changed-fraction", type=float, default=0.01)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        report = benchmark_workspace_sync(args.documents, changed_fraction=args.changed_fraction)
        report["created_at"] = datetime.now(UTC).isoformat()
        report["environment"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "implementation": sys.implementation.name,
        }
        if args.output is None:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            atomic_write_export(args.output, report, force=args.force)
    except (OSError, PortabilityError, RuntimeError, ValueError) as exc:
        code = exc.code if isinstance(exc, PortabilityError) else type(exc).__name__
        raise SystemExit(f"workspace benchmark failed: {code}") from exc


if __name__ == "__main__":
    main()
