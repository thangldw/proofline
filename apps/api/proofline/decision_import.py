from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

MAX_ADR_BYTES = 512_000
MAX_TEXT_CHARS = 600

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_TITLE_NUMBER = re.compile(r"^(?:adr[-\s]*)?\d+[.:)\-\s]+\s*", re.I)
_STATUS_LINE = re.compile(r"^(?:[*\-]\s*)?(?:\*\*)?status(?:\*\*)?\s*[:\-]\s*(.+)$", re.I)
_FRONT_MATTER_STATUS = re.compile(r"^status\s*:\s*(.+)$", re.I)
_DECISION_SECTIONS = ("decision", "decision outcome")
_RATIONALE_SECTIONS = (
    "rationale",
    "context",
    "context and problem statement",
    "decision drivers",
    "consequences",
)
_STATUS_MAP = {
    "accepted": "accepted",
    "approved": "accepted",
    "adopted": "accepted",
    "active": "accepted",
    "proposed": "candidate",
    "draft": "candidate",
    "pending": "candidate",
    "rejected": "rejected",
    "declined": "rejected",
    "deprecated": "obsolete",
    "superseded": "obsolete",
    "obsolete": "obsolete",
    "replaced": "obsolete",
}


class AdrImportError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ImportedAdr:
    source: Path
    output: Path
    status: str


@dataclass(frozen=True)
class SkippedAdr:
    source: Path
    reason: str


@dataclass(frozen=True)
class AdrImportResult:
    imported: list[ImportedAdr]
    skipped: list[SkippedAdr]


@dataclass(frozen=True)
class ParsedAdr:
    title: str
    status: str
    statement: str
    rationale: str | None


def _clean(text: str) -> str:
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= MAX_TEXT_CHARS:
        return text
    cut = text[:MAX_TEXT_CHARS].rsplit(" ", 1)[0].rstrip(",;:-")
    return f"{cut}..."


def _sections(lines: list[str]) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        match = _HEADING.match(line)
        if match and not line.startswith("# "):
            current = match.group(1).strip().casefold().rstrip(":")
            found.setdefault(current, [])
        elif match:
            current = None
        elif current is not None:
            found[current].append(line)
    return {key: _clean(" ".join(value)) for key, value in found.items()}


def _normalize_status(raw: str) -> str:
    word = re.split(r"[\s,;(]", re.sub(r"[*_`\[\]]", "", raw).strip().casefold(), maxsplit=1)[0]
    return _STATUS_MAP.get(word, "candidate")


def _find_status(lines: list[str], sections: dict[str, str]) -> str:
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            match = _FRONT_MATTER_STATUS.match(line.strip())
            if match:
                return _normalize_status(match.group(1))
    for line in lines:
        match = _STATUS_LINE.match(line.strip())
        if match:
            return _normalize_status(match.group(1))
    if sections.get("status"):
        return _normalize_status(sections["status"])
    return "candidate"


def _strip_front_matter(lines: list[str]) -> list[str]:
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return lines[index + 1 :]
    return lines


def parse_adr(text: str, fallback_title: str) -> ParsedAdr:
    raw_lines = text.splitlines()
    lines = _strip_front_matter(raw_lines)
    sections = _sections(lines)
    title = fallback_title
    for line in lines:
        match = re.match(r"^#\s+(.+?)\s*#*\s*$", line)
        if match:
            title = _TITLE_NUMBER.sub("", _clean(match.group(1))) or fallback_title
            break
    decision = next((sections[name] for name in _DECISION_SECTIONS if sections.get(name)), "")
    if not decision:
        raise AdrImportError("no_decision_section")
    decision = re.sub(r"^chosen option\s*[:\-]\s*", "", decision, flags=re.I)
    rationale = next((sections[name] for name in _RATIONALE_SECTIONS if sections.get(name)), None)
    statement = (
        decision if decision.casefold().startswith(title.casefold()) else (f"{title}: {decision}")
    )
    return ParsedAdr(
        title=title,
        status=_find_status(raw_lines, sections),
        statement=statement,
        rationale=rationale,
    )


def render_import(adr: ParsedAdr, source_name: str) -> str:
    lines = [
        f"# ADR: {adr.title}",
        "",
        f"Imported from {source_name} by `proofline import-adr`.",
        "",
        f"Decision: {adr.statement}",
    ]
    if adr.rationale:
        lines.append(f"Rationale: {adr.rationale}")
    lines.append(f"Status: {adr.status}")
    return "\n".join(lines) + "\n"


def import_adrs(adr_dir: Path, output_dir: Path, *, force: bool = False) -> AdrImportResult:
    """Convert Markdown ADRs into Proofline-marked Markdown. Never touches the database."""

    if not adr_dir.is_dir():
        raise AdrImportError("adr_dir_missing")
    resolved_input = adr_dir.resolve()
    if output_dir.resolve() == resolved_input:
        raise AdrImportError("output_is_input")
    plan: list[tuple[Path, Path, str]] = []
    skipped: list[SkippedAdr] = []
    for path in sorted(adr_dir.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            skipped.append(SkippedAdr(path, "not_a_regular_file"))
            continue
        if path.stat().st_size > MAX_ADR_BYTES:
            skipped.append(SkippedAdr(path, "too_large"))
            continue
        try:
            parsed = parse_adr(path.read_text(encoding="utf-8"), path.stem)
        except UnicodeDecodeError:
            skipped.append(SkippedAdr(path, "not_utf8"))
            continue
        except AdrImportError as exc:
            skipped.append(SkippedAdr(path, exc.code))
            continue
        plan.append((path, output_dir / path.name, render_import(parsed, path.name)))
    if not plan:
        return AdrImportResult([], skipped)
    if not force and any(target.exists() for _, target, _ in plan):
        raise AdrImportError("output_exists")
    output_dir.mkdir(parents=True, exist_ok=True)
    imported: list[ImportedAdr] = []
    for source, target, text in plan:
        descriptor, temporary = tempfile.mkstemp(dir=output_dir, prefix=".adr-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        status = next(
            line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Status: ")
        )
        imported.append(ImportedAdr(source, target, status))
    return AdrImportResult(imported, skipped)
