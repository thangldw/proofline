#!/usr/bin/env python3
from __future__ import annotations

import argparse
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from proofline.portability import PortabilityError, atomic_write_export
from proofline.provenance_benchmark import benchmark_decision_evidence_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        report = benchmark_decision_evidence_package(args.iterations)
        report["created_at"] = datetime.now(UTC).isoformat()
        report["environment"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "implementation": sys.implementation.name,
        }
        atomic_write_export(args.output, report, force=args.force)
    except (OSError, PortabilityError, RuntimeError, ValueError) as exc:
        code = exc.code if isinstance(exc, PortabilityError) else type(exc).__name__
        raise SystemExit(f"evidence package benchmark failed: {code}") from exc


if __name__ == "__main__":
    main()
