from __future__ import annotations

import subprocess
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .decision_code_refs import scan_code_refs
from .decision_enforce import _files, parse_rule, rules_in_quote
from .models import Decision

APPROVED = ("active", "accepted")
MAX_COMMITS = 20_000


class DebtError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DebtRow:
    directory: str
    commits: int
    files_changed: int
    code_refs: int
    rules_covering: int

    @property
    def undecided(self) -> bool:
        return self.commits > 0 and self.code_refs == 0 and self.rules_covering == 0

    def model_dump(self) -> dict[str, object]:
        return {**asdict(self), "undecided": self.undecided}


def directory_of(path: str, depth: int) -> str:
    parts = PurePosixPath(path).parts[:-1]
    return "/".join(parts[:depth]) or "."


def git_churn(root: Path, since_days: int) -> dict[str, int]:
    """Commits touching each file in the last `since_days` days (a file counts once per commit)."""

    if not 1 <= since_days <= 3650:
        raise DebtError("since_days_invalid")
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                f"--since={since_days}.days.ago",
                "--name-only",
                "--no-renames",
                "--pretty=format:%x00",
            ],  # fmt: skip
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DebtError("git_unavailable") from exc
    if completed.returncode != 0:
        raise DebtError("git_log_failed")
    churn: dict[str, int] = defaultdict(int)
    commits = 0
    for block in completed.stdout.split("\x00"):
        names = {line.strip() for line in block.splitlines() if line.strip()}
        if not names:
            continue
        commits += 1
        if commits > MAX_COMMITS:
            raise DebtError("too_many_commits")
        for name in names:
            churn[name] += 1
    return dict(churn)


def build_debt_map(
    session: Session, root: Path, *, since_days: int = 90, depth: int = 2
) -> list[DebtRow]:
    if not 1 <= depth <= 6:
        raise DebtError("depth_invalid")
    if not root.is_dir():
        raise DebtError("root_not_found")
    root = root.resolve()
    churn = git_churn(root, since_days)
    commits: dict[str, int] = defaultdict(int)
    files: dict[str, set[str]] = defaultdict(set)
    for path, count in churn.items():
        if not (root / path).exists():
            continue  # deleted since; not a place a decision could apply to now
        directory = directory_of(path, depth)
        commits[directory] += count
        files[directory].add(path)

    decisions = {
        item.id: item
        for item in session.scalars(
            select(Decision)
            .options(selectinload(Decision.evidence))
            .where(Decision.status.in_(APPROVED))
        )
    }
    refs: dict[str, int] = defaultdict(int)
    for ref in scan_code_refs([root]):
        if any(item.startswith(ref.reference) for item in decisions):
            relative = Path(ref.path).resolve().relative_to(root).as_posix()
            refs[directory_of(relative, depth)] += 1
    covering: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for decision in decisions.values():
        texts = [
            text
            for evidence in decision.evidence
            if evidence.binding_state == "active"
            for text in rules_in_quote(evidence.quote)
        ]
        for index, text in enumerate(dict.fromkeys(texts), start=1):
            rule = parse_rule(text)
            if rule is None or rule.kind == "require_file":
                continue
            for matched in _files(root, rule.glob):
                covering[directory_of(matched.relative_to(root).as_posix(), depth)].add(
                    (decision.id, index)
                )
    rows = [
        DebtRow(directory, commits[directory], len(files[directory]), refs[directory],
                len(covering[directory]))
        for directory in commits
    ]  # fmt: skip
    return sorted(rows, key=lambda r: (-r.commits, r.directory))


def render_markdown(rows: list[DebtRow], *, since_days: int) -> str:
    if not rows:
        return f"No tracked files changed in the last {since_days} days.\n"
    lines = [
        f"### Decision coverage of recent change (last {since_days} days)",
        "",
        "| Directory | Commits | Files | Code refs | Rules | |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        flag = "no decision" if row.undecided else ""
        lines.append(
            f"| `{row.directory}` | {row.commits} | {row.files_changed} | {row.code_refs} "
            f"| {row.rules_covering} | {flag} |"
        )
    return "\n".join(lines) + "\n"
