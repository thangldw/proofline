from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import func, text, update
from sqlalchemy.orm import Session

from .models import (
    Chunk,
    Decision,
    Evidence,
    IngestionJob,
    Source,
    SourceVersion,
    new_id,
    utc_now,
)
from .schemas import SourceCreate


@dataclass(frozen=True)
class TextSpan:
    text: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class SourceDeletionImpact:
    versions: int
    chunks: int
    embeddings: int
    decisions: int
    evidence: int
    ingestion_jobs_to_detach: int
    audit_events_to_delete: int
    fts_rows: int


class IngestionConflict(ValueError):
    """Raised when a stable source identity cannot be resolved safely."""


class IngestionExecutionError(RuntimeError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"ingestion job {job_id} failed")


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


def _index_version(session: Session, source: Source, version: SourceVersion, content: str) -> None:
    for ordinal, span in enumerate(chunk_markdown(content)):
        chunk = Chunk(
            source_id=source.id,
            source_version_id=version.id,
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

    for extracted in extract_decisions(content):
        quote = extracted.pop("quote")
        span_fields = {
            key: extracted.pop(key)
            for key in ("start_offset", "end_offset", "start_line", "end_line")
        }
        decision = Decision(source_id=source.id, source_version_id=version.id, **extracted)
        session.add(decision)
        session.flush()
        session.add(
            Evidence(
                decision_id=decision.id,
                source_id=source.id,
                source_version_id=version.id,
                quote=quote,
                quote_hash=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
                **span_fields,
            )
        )


def ingest_source(session: Session, payload: SourceCreate) -> tuple[Source, bool]:
    digest = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
    source = None
    if payload.uri:
        matches = session.query(Source).filter(Source.uri == payload.uri).all()
        if len(matches) > 1:
            raise IngestionConflict(
                "multiple sources already use this URI; resolve the duplicate identity first"
            )
        source = matches[0] if matches else None
        if source:
            current = session.get(SourceVersion, source.current_version_id)
            if current and current.content_hash == digest:
                return source, False
    if source is None:
        duplicate = (
            session.query(Source)
            .join(SourceVersion, Source.current_version_id == SourceVersion.id)
            .filter(Source.uri.is_(None), SourceVersion.content_hash == digest)
            .one_or_none()
        )
        if duplicate:
            return duplicate, False

    created = source is None
    if created:
        source_id = new_id()
        source = Source(
            id=source_id,
            title=payload.title,
            kind=payload.kind,
            uri=payload.uri,
            content=payload.content,
            content_hash=hashlib.sha256(f"source:{source_id}".encode()).hexdigest(),
        )
        session.add(source)
        session.flush()
    else:
        source.title = payload.title
        source.kind = payload.kind
        source.content = payload.content
        source.status = "indexed"
        source.indexed_at = utc_now()

    version_number = (
        session.query(func.max(SourceVersion.version_number))
        .filter(SourceVersion.source_id == source.id)
        .scalar()
        or 0
    ) + 1
    version = SourceVersion(
        source_id=source.id,
        content_hash=digest,
        content=payload.content,
        version_number=version_number,
        content_length=len(payload.content),
        status="indexed",
        parser_version="deterministic-v1",
    )
    session.add(version)
    session.flush()
    source.current_version_id = version.id
    _index_version(session, source, version, payload.content)

    session.commit()
    session.refresh(source)
    return source, created


def run_ingestion_job(session: Session, payload: SourceCreate) -> tuple[Source, bool, IngestionJob]:
    """Run synchronous ingestion while persisting terminal success or failure."""
    job = IngestionJob(state="running", stage="accepted", attempts=1, retryable=False)
    session.add(job)
    session.commit()
    job_id = job.id
    try:
        job.stage = "indexing"
        session.commit()
        source, created = ingest_source(session, payload)
    except Exception as exc:
        session.rollback()
        failed_job = session.get(IngestionJob, job_id)
        failed_job.state = "failed"
        failed_job.stage = "failed"
        failed_job.error_code = (
            "source_identity_conflict" if isinstance(exc, IngestionConflict) else "ingestion_error"
        )
        failed_job.error_detail = (
            str(exc)
            if isinstance(exc, IngestionConflict)
            else f"ingestion failed with {type(exc).__name__}"
        )
        failed_job.updated_at = utc_now()
        session.commit()
        if isinstance(exc, IngestionConflict):
            raise
        raise IngestionExecutionError(job_id) from exc

    succeeded_job = session.get(IngestionJob, job_id)
    succeeded_job.source_id = source.id
    succeeded_job.source_version_id = source.current_version_id
    succeeded_job.state = "succeeded"
    succeeded_job.stage = "ready"
    succeeded_job.updated_at = utc_now()
    session.commit()
    return source, created, succeeded_job


def source_deletion_impact(session: Session, source: Source) -> SourceDeletionImpact:
    """Count records affected by deleting a source without loading content-bearing rows."""
    row = (
        session.execute(
            text(
                """SELECT
                (SELECT count(*) FROM source_versions WHERE source_id = :source) AS versions,
                (SELECT count(*) FROM chunks WHERE source_id = :source) AS chunks,
                (SELECT count(*) FROM chunk_embeddings WHERE source_id = :source) AS embeddings,
                (SELECT count(*) FROM decisions WHERE source_id = :source) AS decisions,
                (SELECT count(*) FROM evidence WHERE source_id = :source) AS evidence,
                (SELECT count(*) FROM ingestion_jobs WHERE source_id = :source)
                    AS ingestion_jobs_to_detach,
                (SELECT count(*) FROM audit_events
                   WHERE (object_type = 'source' AND object_id = :source)
                      OR (object_type = 'decision' AND object_id IN
                          (SELECT id FROM decisions WHERE source_id = :source)))
                    AS audit_events_to_delete,
                (SELECT count(*) FROM chunk_search WHERE source_id = :source) AS fts_rows"""
            ),
            {"source": source.id},
        )
        .mappings()
        .one()
    )
    return SourceDeletionImpact(**dict(row))


def delete_source(session: Session, source: Source) -> None:
    session.execute(
        update(IngestionJob)
        .where(IngestionJob.source_id == source.id)
        .values(source_id=None, source_version_id=None)
    )
    session.execute(
        text(
            """DELETE FROM audit_events
               WHERE object_type = 'decision'
                 AND object_id IN (SELECT id FROM decisions WHERE source_id = :source)"""
        ),
        {"source": source.id},
    )
    session.execute(
        text("DELETE FROM audit_events WHERE object_type = 'source' AND object_id = :source"),
        {"source": source.id},
    )
    session.execute(
        text("DELETE FROM chunk_search WHERE source_id = :source"), {"source": source.id}
    )
    session.delete(source)
    session.commit()
