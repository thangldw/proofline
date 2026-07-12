from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import Chunk, Decision, Evidence, Source
from .schemas import SourceCreate


@dataclass(frozen=True)
class TextSpan:
    text: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int


DECISION_PREFIX = re.compile(
    r"^(?:decision|quy(?:ế|e)t định|we (?:will|chose|choose|decided to))\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
DECISION_HEADING = re.compile(r"^#{1,6}\s+(?:decision|quy(?:ế|e)t định)\s*[:\-]?\s*(.*)$", re.I)
RATIONALE_PREFIX = re.compile(r"^(?:rationale|reason|because|lý do)\s*[:\-]\s*(.+)$", re.I)
STATUS_PREFIX = re.compile(r"^(?:status|trạng thái)\s*[:\-]\s*(.+)$", re.I)


def line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def chunk_markdown(content: str, max_chars: int = 1600) -> list[TextSpan]:
    paragraphs = list(re.finditer(r"\S(?:.|\n)*?(?=\n\s*\n|\Z)", content))
    spans: list[TextSpan] = []
    current_start: int | None = None
    current_end = 0

    def flush() -> None:
        nonlocal current_start, current_end
        if current_start is None:
            return
        raw = content[current_start:current_end]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        start = current_start + left
        end = current_start + right
        if end > start:
            spans.append(
                TextSpan(
                    content[start:end],
                    start,
                    end,
                    line_number(content, start),
                    line_number(content, max(start, end - 1)),
                )
            )
        current_start = None

    for paragraph in paragraphs:
        if current_start is None:
            current_start, current_end = paragraph.start(), paragraph.end()
        elif paragraph.end() - current_start <= max_chars:
            current_end = paragraph.end()
        else:
            flush()
            current_start, current_end = paragraph.start(), paragraph.end()
    flush()
    return spans


def extract_decisions(content: str) -> list[dict]:
    lines = content.splitlines(keepends=True)
    results: list[dict] = []
    cursor = 0
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        heading = DECISION_HEADING.match(stripped)
        prefix = DECISION_PREFIX.match(stripped)
        if not heading and not prefix:
            cursor += len(raw)
            index += 1
            continue

        statement = (heading or prefix).group(1).strip()
        title = statement or "Recorded decision"
        start = cursor + len(raw) - len(raw.lstrip())
        end = cursor + len(raw.rstrip("\r\n"))
        rationale = None
        status = "active"
        lookahead_cursor = cursor + len(raw)

        for next_index in range(index + 1, min(index + 5, len(lines))):
            candidate = lines[next_index].strip()
            if not candidate or candidate.startswith("#") or DECISION_PREFIX.match(candidate):
                break
            rationale_match = RATIONALE_PREFIX.match(candidate)
            status_match = STATUS_PREFIX.match(candidate)
            if rationale_match:
                rationale = rationale_match.group(1).strip()
                end = lookahead_cursor + len(lines[next_index].rstrip("\r\n"))
            if status_match:
                normalized = status_match.group(1).strip().lower()
                status = (
                    "superseded"
                    if normalized in {"superseded", "replaced", "obsolete"}
                    else normalized
                )
                end = lookahead_cursor + len(lines[next_index].rstrip("\r\n"))
            lookahead_cursor += len(lines[next_index])

        quote = content[start:end]
        results.append(
            {
                "title": title[:300],
                "statement": statement or title,
                "rationale": rationale,
                "status": status[:30],
                "quote": quote,
                "start_offset": start,
                "end_offset": end,
                "start_line": line_number(content, start),
                "end_line": line_number(content, max(start, end - 1)),
            }
        )
        cursor += len(raw)
        index += 1
    return results


def ingest_source(session: Session, payload: SourceCreate) -> tuple[Source, bool]:
    digest = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
    existing = session.query(Source).filter(Source.content_hash == digest).one_or_none()
    if existing:
        return existing, False

    source = Source(
        title=payload.title,
        kind=payload.kind,
        uri=payload.uri,
        content=payload.content,
        content_hash=digest,
    )
    session.add(source)
    session.flush()

    for ordinal, span in enumerate(chunk_markdown(payload.content)):
        chunk = Chunk(
            source_id=source.id,
            ordinal=ordinal,
            content=span.text,
            start_offset=span.start_offset,
            end_offset=span.end_offset,
            start_line=span.start_line,
            end_line=span.end_line,
        )
        session.add(chunk)
        session.flush()
        session.execute(
            text(
                "INSERT INTO chunk_search(chunk_id, source_id, content) "
                "VALUES (:chunk, :source, :content)"
            ),
            {"chunk": chunk.id, "source": source.id, "content": chunk.content},
        )

    for extracted in extract_decisions(payload.content):
        quote = extracted.pop("quote")
        span_fields = {
            key: extracted.pop(key)
            for key in ("start_offset", "end_offset", "start_line", "end_line")
        }
        decision = Decision(source_id=source.id, **extracted)
        session.add(decision)
        session.flush()
        session.add(
            Evidence(decision_id=decision.id, source_id=source.id, quote=quote, **span_fields)
        )

    session.commit()
    session.refresh(source)
    return source, True


def delete_source(session: Session, source: Source) -> None:
    session.execute(
        text("DELETE FROM chunk_search WHERE source_id = :source"), {"source": source.id}
    )
    session.delete(source)
    session.commit()
