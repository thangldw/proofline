from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Decision

ENFORCE_LINE = re.compile(r"^enforce\s*:\s*(.+?)\s*$", re.I)
_FORBID = re.compile(r'^(forbid|require)\s+"([^"\n]{1,200})"\s+in\s+(\S+)$', re.I)
_REQUIRE_FILE = re.compile(r"^require\s+file\s+(\S+)$", re.I)
SKIP_DIRECTORIES = frozenset({".git", "node_modules", ".venv", "__pycache__", "dist", "build"})
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 20_000


class EnforceError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Rule:
    kind: str  # forbid | require | require_file
    pattern: str
    glob: str
    text: str


@dataclass(frozen=True)
class EnforceFinding:
    decision_id: str
    rule_index: int
    rule: str
    problem: str  # violated | missing | rule_invalid
    path: str | None = None
    line: int | None = None

    def model_dump(self) -> dict[str, str | int | None]:
        return asdict(self)

    def content_free_model_dump(self) -> dict[str, str | int | None]:
        document = self.model_dump()
        document.pop("rule")
        return document


def _safe_glob(value: str) -> bool:
    parts = value.replace("\\", "/").split("/")
    return bool(value) and not value.startswith("/") and ".." not in parts and ":" not in value


def parse_rule(text: str) -> Rule | None:
    """Parse one declarative rule; None when the syntax or the glob is not acceptable.

    Patterns are literal, case-sensitive substrings: a decision's text must never be able to
    run code or a regular expression against the repository.
    """

    text = text.strip()
    match = _FORBID.match(text)
    if match and _safe_glob(match.group(3)):
        verb = match.group(1).casefold()
        return Rule(verb, match.group(2), match.group(3), text)
    match = _REQUIRE_FILE.match(text)
    if match and _safe_glob(match.group(1)):
        return Rule("require_file", "", match.group(1), text)
    return None


def rules_in_quote(quote: str) -> list[str]:
    return [m.group(1) for line in quote.splitlines() if (m := ENFORCE_LINE.match(line.strip()))]


def _files(root: Path, pattern: str) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.glob(pattern)):
        relative = path.relative_to(root).parts
        if path.is_symlink() or not path.is_file() or any(p in SKIP_DIRECTORIES for p in relative):
            continue
        found.append(path)
        if len(found) > MAX_FILES:
            raise EnforceError("too_many_files")
    return found


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def evaluate_rule(root: Path, rule: Rule) -> list[tuple[str, str, int | None]]:
    """Return (problem, path, line) tuples; an empty list means the rule holds."""

    if rule.kind == "require_file":
        matches = _files(root, rule.glob)
        return [] if matches else [("missing", rule.glob, None)]
    outcomes: list[tuple[str, str, int | None]] = []
    present = False
    for path in _files(root, rule.glob):
        text = _read(path)
        if text is None:
            continue
        relative = path.relative_to(root).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            if rule.pattern in line:
                present = True
                if rule.kind == "forbid":
                    outcomes.append(("violated", relative, number))
    if rule.kind == "require" and not present:
        return [("missing", rule.glob, None)]
    return outcomes


def check_enforcement(session: Session, root: Path) -> list[EnforceFinding]:
    """Check declarative `Enforce:` rules of approved decisions against the files under root."""

    if not root.is_dir():
        raise EnforceError("root_not_found")
    root = root.resolve()
    decisions = session.scalars(
        select(Decision)
        .options(selectinload(Decision.evidence))
        .where(Decision.status.in_(("active", "accepted")))
        .order_by(Decision.id)
    ).all()
    findings: list[EnforceFinding] = []
    for decision in decisions:
        texts: list[str] = []
        for evidence in decision.evidence:
            if evidence.binding_state == "active":
                texts.extend(rules_in_quote(evidence.quote))
        for index, text in enumerate(dict.fromkeys(texts), start=1):
            rule = parse_rule(text)
            if rule is None:
                findings.append(EnforceFinding(decision.id, index, text, "rule_invalid"))
                continue
            findings.extend(
                EnforceFinding(decision.id, index, text, problem, path, line)
                for problem, path, line in evaluate_rule(root, rule)
            )
    return findings
