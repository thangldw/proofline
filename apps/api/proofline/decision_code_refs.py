from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .decision_health import check_decision_health
from .models import Decision

REF_PATTERN = re.compile(r"proofline-decision\s*[:=]\s*([0-9a-fA-F][0-9a-fA-F-]{7,35})")
SKIP_DIRECTORIES = frozenset({".git", "node_modules", ".venv", "__pycache__", "dist", "build"})
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 50_000


class CodeRefError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CodeRef:
    path: str
    line: int
    reference: str

    def model_dump(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True)
class CodeRefFinding:
    path: str
    line: int
    reference: str
    problem: str
    decision_id: str | None

    def model_dump(self) -> dict[str, str | int | None]:
        return asdict(self)


def scan_code_refs(paths: list[Path]) -> list[CodeRef]:
    """Find `proofline-decision: <id>` markers in text files under the given paths."""

    refs: list[CodeRef] = []
    seen = 0
    for root in paths:
        if not root.exists():
            raise CodeRefError("path_not_found")
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in candidates:
            if any(part in SKIP_DIRECTORIES for part in path.parts) or not path.is_file():
                continue
            seen += 1
            if seen > MAX_FILES:
                raise CodeRefError("too_many_files")
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                refs.extend(
                    CodeRef(path=str(path), line=number, reference=match.group(1).lower())
                    for match in REF_PATTERN.finditer(line)
                )
    return refs


def check_code_refs(session: Session, refs: list[CodeRef]) -> list[CodeRefFinding]:
    """Report references to decisions that are missing, ambiguous, unapproved or stale."""

    decisions = list(session.scalars(select(Decision).order_by(Decision.id)).all())
    stale = {finding.decision_id: finding.reason for finding in check_decision_health(session)}
    findings: list[CodeRefFinding] = []
    for ref in refs:
        matches = [item for item in decisions if item.id.startswith(ref.reference)]
        if not matches:
            problem, decision_id = "missing", None
        elif len(matches) > 1:
            problem, decision_id = "ambiguous_reference", None
        else:
            decision = matches[0]
            decision_id = decision.id
            if decision.status not in {"active", "accepted"}:
                problem = f"not_approved:{decision.status}"
            elif decision.id in stale:
                problem = f"stale:{stale[decision.id]}"
            else:
                continue
        findings.append(
            CodeRefFinding(
                path=ref.path,
                line=ref.line,
                reference=ref.reference,
                problem=problem,
                decision_id=decision_id,
            )
        )
    return findings
