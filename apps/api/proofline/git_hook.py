from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

HOOK_MARKER = "# proofline-managed pre-commit hook"

_BASE = f"""#!/bin/sh
{HOOK_MARKER} (remove with `proofline hook uninstall`)
if ! command -v proofline >/dev/null 2>&1; then
  echo "proofline not on PATH; skipping decision checks" >&2
  exit 0
fi
files=$(git diff --cached --name-only --diff-filter=ACM)
if [ -n "$files" ]; then
  git diff --cached --name-only -z --diff-filter=ACM | xargs -0 proofline check-code-refs || exit 1
fi
"""

_DECISIONS = """proofline sync "$(git rev-parse --show-toplevel)" --format json >/dev/null || exit 1
proofline check-decisions || exit 1
"""


class HookError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class HookResult:
    path: Path
    action: str


def render_hook(*, with_decisions: bool) -> str:
    return _BASE + (_DECISIONS if with_decisions else "")


def hook_path(repo: Path) -> Path:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-path", "hooks/pre-commit"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HookError("git_unavailable") from exc
    if completed.returncode != 0 or not completed.stdout.strip():
        raise HookError("not_a_git_repository")
    path = Path(completed.stdout.strip())
    return path if path.is_absolute() else repo / path


def _ours(path: Path) -> bool:
    try:
        return HOOK_MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False


def install_hook(repo: Path, *, with_decisions: bool = False, force: bool = False) -> HookResult:
    path = hook_path(repo)
    if path.exists() and not _ours(path) and not force:
        raise HookError("hook_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_hook(with_decisions=with_decisions), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return HookResult(path, "installed")


def uninstall_hook(repo: Path) -> HookResult:
    path = hook_path(repo)
    if not path.exists():
        return HookResult(path, "absent")
    if not _ours(path):
        raise HookError("hook_not_managed")
    os.remove(path)
    return HookResult(path, "removed")
