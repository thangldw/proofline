from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .decision_blame import blame
from .decision_code_refs import MAX_FILE_BYTES, REF_PATTERN
from .decision_enforce import evaluate_rule, parse_rule, rules_in_quote
from .decision_health import check_decision_health
from .models import Decision

APPROVED = ("active", "accepted")
_REF_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/~^-]{0,99}$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
MAX_FILES = 500


class ContextError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ContextItem:
    path: str
    via: str  # code_ref | document_edit | enforce_rule
    decision_id: str
    status: str
    health: str
    detail: str
    decision_title: str

    def model_dump(self) -> dict[str, str]:
        return asdict(self)

    def content_free_model_dump(self) -> dict[str, str]:
        document = self.model_dump()
        document.pop("decision_title")
        return document

    @property
    def needs_attention(self) -> bool:
        return self.health not in ("current", "applies")


def parse_unified_diff(text: str) -> dict[str, list[tuple[int, int]]]:
    """Changed line ranges per file (new-file numbering) from a `git diff -U0` style diff."""

    changes: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("+++ "):
            name = line[4:].strip()
            current = None if name == "/dev/null" else name.removeprefix("b/")
            if current is not None:
                changes.setdefault(current, [])
            continue
        match = _HUNK.match(line)
        if match and current is not None:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) is not None else 1
            changes[current].append((start, max(start, start + count - 1)))
    if len(changes) > MAX_FILES:
        raise ContextError("too_many_files")
    return changes


def git_diff(root: Path, base: str) -> str:
    if not _REF_NAME.match(base) or ".." in base:
        raise ContextError("base_ref_invalid")
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "diff", "-U0", "--no-color", f"{base}...HEAD", "--"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContextError("git_unavailable") from exc
    if completed.returncode != 0:
        raise ContextError("git_diff_failed")
    return completed.stdout


def _glob_regex(pattern: str) -> re.Pattern[str]:
    out = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(out) + r"\Z")


def _near(line: int, ranges: list[tuple[int, int]], radius: int) -> bool:
    return any(start - radius <= line <= end + radius for start, end in ranges)


def _overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= r_end and r_start <= end for r_start, r_end in ranges)


def build_context(
    session: Session,
    root: Path,
    changes: dict[str, list[tuple[int, int]]],
    *,
    radius: int = 10,
) -> list[ContextItem]:
    if radius < 0 or radius > 1000:
        raise ContextError("radius_invalid")
    root = root.resolve()
    decisions = list(
        session.scalars(
            select(Decision).options(selectinload(Decision.evidence)).order_by(Decision.id)
        ).all()
    )
    by_id = {item.id: item for item in decisions}
    stale = {finding.decision_id: finding.reason for finding in check_decision_health(session)}

    def health_of(decision: Decision) -> str:
        return stale.get(decision.id, "current")

    rules = []
    for decision in decisions:
        if decision.status not in APPROVED:
            continue
        texts = [
            text
            for evidence in decision.evidence
            if evidence.binding_state == "active"
            for text in rules_in_quote(evidence.quote)
        ]
        for index, text in enumerate(dict.fromkeys(texts), start=1):
            rule = parse_rule(text)
            if rule is not None:
                rules.append((decision, index, rule, _glob_regex(rule.glob)))

    items: list[ContextItem] = []
    for path, ranges in sorted(changes.items()):
        file_path = (root / path).resolve()
        if root not in file_path.parents:
            continue
        if file_path.is_file() and file_path.stat().st_size <= MAX_FILE_BYTES:
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                lines = []
            for number, text in enumerate(lines, start=1):
                if not _near(number, ranges, radius):
                    continue
                for match in REF_PATTERN.finditer(text):
                    found = [d for d in decisions if d.id.startswith(match.group(1).lower())]
                    if len(found) == 1:
                        decision = found[0]
                        items.append(
                            ContextItem(
                                path,
                                "code_ref",
                                decision.id,
                                decision.status,
                                health_of(decision),
                                f"line {number}",
                                decision.title,
                            )
                        )
        for entry in blame(session, path):
            start = entry.current_start_line or entry.cited_start_line
            end = entry.current_end_line or entry.cited_end_line
            if _overlaps(start, end, ranges):
                decision = by_id[entry.decision_id]
                items.append(
                    ContextItem(
                        path,
                        "document_edit",
                        decision.id,
                        decision.status,
                        entry.state,
                        f"lines {start}-{end}",
                        decision.title,
                    )
                )
        for decision, index, rule, pattern in rules:
            if not pattern.match(path):
                continue
            broken = any(
                outcome_path == path or rule.kind == "require_file"
                for _, outcome_path, _ in evaluate_rule(root, rule)
            )
            items.append(
                ContextItem(
                    path,
                    "enforce_rule",
                    decision.id,
                    decision.status,
                    "violated" if broken else "applies",
                    f"rule {index}",
                    decision.title,
                )
            )
    return sorted(set(items), key=lambda i: (i.path, i.via, i.decision_id, i.detail))


def render_markdown(items: list[ContextItem], *, include_titles: bool) -> str:
    if not items:
        return "No approved decision is attached to the changed files.\n"
    lines = [
        "### Decisions touched by this change",
        "",
        "| File | Via | Decision | Status | Health | Where |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        label = f"`{item.decision_id[:8]}`"
        if include_titles:
            label = f"{item.decision_title.replace('|', '/')} ({label})"
        lines.append(
            f"| `{item.path}` | {item.via} | {label} | {item.status} | {item.health} "
            f"| {item.detail} |"
        )
    return "\n".join(lines) + "\n"
