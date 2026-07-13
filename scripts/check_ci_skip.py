#!/usr/bin/env python3
"""Require a GitHub-supported CI skip instruction on the release commit."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

BRACKETED_SKIP = re.compile(
    r"\[(?:skip ci|ci skip|no ci|skip actions|actions skip)\]", re.IGNORECASE
)
SKIP_TRAILER = re.compile(r"^skip-checks:\s*true\s*$", re.IGNORECASE | re.MULTILINE)


def contains_ci_skip(message: str) -> bool:
    return bool(BRACKETED_SKIP.search(message) or SKIP_TRAILER.search(message))


def head_message() -> str:
    return subprocess.check_output(
        ["git", "log", "-1", "--pretty=%B"], text=True, stderr=subprocess.DEVNULL
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", help="check this message instead of the current HEAD")
    args = parser.parse_args()
    message = args.message if args.message is not None else head_message()
    if contains_ci_skip(message):
        return 0
    print(
        "release commit must contain a GitHub CI skip instruction, for example [skip ci]",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
