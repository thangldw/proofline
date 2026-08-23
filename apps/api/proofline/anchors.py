from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

ANCHOR_VERSION = "markdown-context-v1"
MIN_CHANGED_SIMILARITY = 0.60
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

AnchorState = Literal["current", "unchanged", "moved", "ambiguous", "changed", "deleted"]

_HEADING = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class EvidenceAnchor:
    version: str
    section_path: tuple[str, ...]
    prefix_sha256: str
    suffix_sha256: str


@dataclass(frozen=True)
class AnchorCandidate:
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    section_path: tuple[str, ...]
    similarity: float


@dataclass(frozen=True)
class AnchorResolution:
    state: AnchorState
    candidates: tuple[AnchorCandidate, ...]


@dataclass(frozen=True)
class _Line:
    text: str
    start: int
    end: int


def _lines(content: str) -> list[_Line]:
    records: list[_Line] = []
    cursor = 0
    for raw in content.splitlines(keepends=True):
        text = raw.rstrip("\r\n")
        records.append(_Line(text=text, start=cursor, end=cursor + len(text)))
        cursor += len(raw)
    if not records or cursor < len(content):
        records.append(_Line(text=content[cursor:], start=cursor, end=len(content)))
    return records


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).strip().split())


def _hash_lines(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _section_paths(lines: list[_Line]) -> list[tuple[str, ...]]:
    path: list[str] = []
    result: list[tuple[str, ...]] = []
    for line in lines:
        match = _HEADING.match(line.text)
        if match:
            level = len(match.group(1))
            heading = _normalize(match.group(2))
            path = path[: level - 1]
            path.append(heading)
        result.append(tuple(path))
    return result


def _line_index(lines: list[_Line], offset: int) -> int:
    for index, line in enumerate(lines):
        if line.start <= offset <= line.end:
            return index
    return len(lines) - 1


def build_evidence_anchor(content: str, start_offset: int, end_offset: int) -> EvidenceAnchor:
    if not 0 <= start_offset < end_offset <= len(content):
        raise ValueError("anchor_span_invalid")
    lines = _lines(content)
    start_index = _line_index(lines, start_offset)
    end_index = _line_index(lines, end_offset - 1)
    paths = _section_paths(lines)

    prefix: list[str] = []
    for line in reversed(lines[:start_index]):
        normalized = _normalize(line.text)
        if normalized:
            prefix.append(normalized)
        if len(prefix) == 2:
            break
    prefix.reverse()

    suffix: list[str] = []
    for line in lines[end_index + 1 :]:
        normalized = _normalize(line.text)
        if normalized:
            suffix.append(normalized)
        if len(suffix) == 2:
            break

    return EvidenceAnchor(
        version=ANCHOR_VERSION,
        section_path=paths[start_index],
        prefix_sha256=_hash_lines(prefix),
        suffix_sha256=_hash_lines(suffix),
    )


def _candidate(content: str, start: int, end: int, similarity: float) -> AnchorCandidate:
    anchor = build_evidence_anchor(content, start, end)
    return AnchorCandidate(
        start_offset=start,
        end_offset=end,
        start_line=content.count("\n", 0, start) + 1,
        end_line=content.count("\n", 0, end - 1) + 1,
        section_path=anchor.section_path,
        similarity=similarity,
    )


def _exact_occurrences(content: str, quote: str) -> list[int]:
    offsets: list[int] = []
    cursor = 0
    while True:
        found = content.find(quote, cursor)
        if found < 0:
            return offsets
        offsets.append(found)
        cursor = found + 1


def _context_matches(cited: EvidenceAnchor, current: EvidenceAnchor) -> bool:
    return (
        cited.section_path == current.section_path
        and (cited.prefix_sha256 == EMPTY_SHA256 or cited.prefix_sha256 == current.prefix_sha256)
        and (cited.suffix_sha256 == EMPTY_SHA256 or cited.suffix_sha256 == current.suffix_sha256)
    )


def _changed_candidates(
    *, quote: str, cited_anchor: EvidenceAnchor, current_content: str
) -> tuple[AnchorCandidate, ...]:
    lines = _lines(current_content)
    paths = _section_paths(lines)
    quote_line_count = max(1, len(quote.splitlines()))
    normalized_quote = _normalize(quote)
    candidates: list[AnchorCandidate] = []
    terminal_heading = cited_anchor.section_path[-1:] or ()

    for index in range(0, len(lines) - quote_line_count + 1):
        window = lines[index : index + quote_line_count]
        if terminal_heading and paths[index][-1:] != terminal_heading:
            continue
        start = window[0].start
        end = window[-1].end
        if end <= start:
            continue
        similarity = SequenceMatcher(
            None,
            normalized_quote,
            _normalize(current_content[start:end]),
            autojunk=False,
        ).ratio()
        if similarity < MIN_CHANGED_SIMILARITY:
            continue
        candidates.append(_candidate(current_content, start, end, similarity))

    return tuple(sorted(candidates, key=lambda item: (-item.similarity, item.start_offset)))


def resolve_evidence_anchor(
    *, quote: str, cited_anchor: EvidenceAnchor, current_content: str
) -> AnchorResolution:
    if not quote:
        raise ValueError("anchor_quote_invalid")
    if cited_anchor.version != ANCHOR_VERSION:
        raise ValueError("anchor_version_unsupported")

    occurrences = _exact_occurrences(current_content, quote)
    exact = tuple(
        _candidate(current_content, start, start + len(quote), 1.0) for start in occurrences
    )
    if len(exact) > 1:
        return AnchorResolution(state="ambiguous", candidates=exact)
    if len(exact) == 1:
        current_anchor = build_evidence_anchor(
            current_content, exact[0].start_offset, exact[0].end_offset
        )
        state: AnchorState = (
            "unchanged" if _context_matches(cited_anchor, current_anchor) else "moved"
        )
        return AnchorResolution(state=state, candidates=exact)

    candidates = _changed_candidates(
        quote=quote,
        cited_anchor=cited_anchor,
        current_content=current_content,
    )
    return AnchorResolution(
        state="changed" if candidates else "deleted",
        candidates=candidates,
    )
