from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .decision_context import _REF_NAME
from .decision_health import check_decision_health
from .models import Decision

LEDGER_VERSION = 1
DEFAULT_LEDGER = Path(".proofline/ledger.jsonl")
MAX_LEDGER_BYTES = 8_000_000
MAX_STALE_IDS = 2000
REASONS = ("moved", "changed", "ambiguous", "deleted")


class LedgerError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LedgerEntry:
    taken_at: str
    approved: int
    findings: int
    by_reason: dict[str, int]
    stale_ids: list[str]
    prev: str
    hash: str

    def model_dump(self) -> dict[str, object]:
        return asdict(self)

    @property
    def stale_percent(self) -> float:
        return round(100 * self.findings / self.approved, 1) if self.approved else 0.0


def _payload(entry: dict[str, object]) -> bytes:
    body = {key: value for key, value in entry.items() if key != "hash"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _entry_hash(entry: dict[str, object]) -> str:
    return hashlib.sha256(_payload(entry)).hexdigest()


def current_state(session: Session) -> tuple[int, dict[str, int], list[str]]:
    findings = check_decision_health(session)
    approved = (
        session.scalar(
            select(func.count(Decision.id)).where(Decision.status.in_(("active", "accepted")))
        )
        or 0
    )
    by_reason = {reason: 0 for reason in REASONS}
    for finding in findings:
        if finding.reason in by_reason:
            by_reason[finding.reason] += 1
    stale_ids = sorted({finding.decision_id for finding in findings})
    return approved, by_reason, stale_ids


def parse_ledger(text: str) -> list[LedgerEntry]:
    """Parse and verify the hash chain; any edit, deletion or reordering raises."""

    entries: list[LedgerEntry] = []
    previous = ""
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            entry = LedgerEntry(
                taken_at=str(raw["taken_at"]),
                approved=int(raw["approved"]),
                findings=int(raw["findings"]),
                by_reason={str(k): int(v) for k, v in raw["by_reason"].items()},
                stale_ids=[str(item) for item in raw["stale_ids"]],
                prev=str(raw["prev"]),
                hash=str(raw["hash"]),
            )
            version = raw["v"]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise LedgerError(f"ledger_line_invalid:{number}") from exc
        if version != LEDGER_VERSION:
            raise LedgerError("ledger_version_unsupported")
        if entry.prev != previous:
            raise LedgerError(f"ledger_chain_broken:{number}")
        if _entry_hash(raw) != entry.hash:
            raise LedgerError(f"ledger_hash_mismatch:{number}")
        entries.append(entry)
        previous = entry.hash
    return entries


def read_ledger(path: Path) -> list[LedgerEntry]:
    try:
        if not path.exists():
            return []
        if path.stat().st_size > MAX_LEDGER_BYTES:
            raise LedgerError("ledger_too_large")
        return parse_ledger(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise LedgerError("ledger_unreadable") from exc


def append_entry(session: Session, path: Path, *, taken_at: datetime | None = None) -> LedgerEntry:
    entries = read_ledger(path)
    approved, by_reason, stale_ids = current_state(session)
    if len(stale_ids) > MAX_STALE_IDS:
        raise LedgerError("too_many_stale_decisions")
    moment = (taken_at or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    raw: dict[str, object] = {
        "v": LEDGER_VERSION,
        "taken_at": moment.isoformat().replace("+00:00", "Z"),
        "approved": approved,
        "findings": len(stale_ids),
        "by_reason": by_reason,
        "stale_ids": stale_ids,
        "prev": entries[-1].hash if entries else "",
    }
    raw["hash"] = _entry_hash(raw)
    line = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".ledger-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(existing + line + "\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return read_ledger(path)[-1]


def ledger_at_ref(root: Path, ref: str, path: Path) -> list[LedgerEntry]:
    """The verified ledger as committed at a git ref; empty when it does not exist there."""

    if not _REF_NAME.match(ref) or ".." in ref:
        raise LedgerError("base_ref_invalid")
    relative = path.as_posix().lstrip("/")
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "show", f"{ref}:{relative}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LedgerError("git_unavailable") from exc
    if completed.returncode != 0:
        return []
    if len(completed.stdout) > MAX_LEDGER_BYTES:
        raise LedgerError("ledger_too_large")
    return parse_ledger(completed.stdout)


@dataclass(frozen=True)
class LedgerComparison:
    base_taken_at: str | None
    base_approved: int
    base_findings: int
    approved: int
    findings: int
    newly_stale: list[str]
    recovered: list[str]

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


def _percent(findings: int, approved: int) -> float:
    return round(100 * findings / approved, 1) if approved else 0.0


def compare_with_base(session: Session, base: list[LedgerEntry]) -> LedgerComparison:
    approved, _by_reason, stale_ids = current_state(session)
    last = base[-1] if base else None
    before = set(last.stale_ids) if last else set()
    now = set(stale_ids)
    return LedgerComparison(
        base_taken_at=last.taken_at if last else None,
        base_approved=last.approved if last else 0,
        base_findings=last.findings if last else 0,
        approved=approved,
        findings=len(stale_ids),
        newly_stale=sorted(now - before),
        recovered=sorted(before - now),
    )


def render_comparison(result: LedgerComparison) -> str:
    if result.base_taken_at is None:
        return "No ledger entry on the base ref; nothing to compare with.\n"
    before = _percent(result.base_findings, result.base_approved)
    after = _percent(result.findings, result.approved)
    arrow = "up" if after > before else "down" if after < before else "unchanged"
    lines = [
        "### Decision health vs base",
        "",
        f"Stale decisions: {result.base_findings}/{result.base_approved} ({before}%) -> "
        f"{result.findings}/{result.approved} ({after}%), {arrow}. "
        f"Base entry taken {result.base_taken_at}.",
    ]
    if result.newly_stale:
        lines += ["", "Newly stale: " + ", ".join(f"`{i[:8]}`" for i in result.newly_stale)]
    if result.recovered:
        lines += ["", "Recovered: " + ", ".join(f"`{i[:8]}`" for i in result.recovered)]
    return "\n".join(lines) + "\n"
