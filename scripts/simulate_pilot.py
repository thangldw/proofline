from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from proofline.pilot_simulation import run_synthetic_pilot_simulation, write_simulation_report


def _revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    revision = result.stdout.strip()
    dirty = subprocess.run(
        ["git", "diff", "--quiet", "--no-ext-diff"],
        check=False,
        capture_output=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        check=False,
        capture_output=True,
        text=True,
    )
    if dirty.returncode != 0 or untracked.stdout.strip():
        return f"{revision}+dirty"
    return revision


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a credential-free synthetic pilot simulation (not real pilot evidence)."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    report = run_synthetic_pilot_simulation(
        args.dataset,
        proofline_revision=_revision(),
        limit=args.limit,
    )
    if args.output:
        write_simulation_report(args.output, report)
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
