from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from dataclasses import dataclass

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    Chunk,
    Decision,
    Evidence,
    IngestionJob,
    IngestionJobInput,
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
    vector_index_rows: int
    decisions: int
    memories: int
    evidence: int
    decision_relations: int
    study_cards: int
    study_reviews: int
    ingestion_jobs_to_detach: int
    audit_events_to_delete: int
    fts_rows: int


class IngestionConflict(ValueError):
    """Raised when a stable source identity cannot be resolved safely."""

    def __init__(self, message: str, job_id: str | None = None) -> None:
        self.job_id = job_id
        super().__init__(message)


class IngestionExecutionError(RuntimeError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"ingestion job {job_id} failed")


class IngestionJobNotFound(LookupError):
    pass


class IngestionRetryConflict(RuntimeError):
    def __init__(self, job_id: str, reason: str) -> None:
        self.job_id = job_id
        self.reason = reason
        super().__init__(reason)


class IngestionIdempotencyConflict(IngestionConflict):
    def __init__(self, job_id: str, reason: str) -> None:
        self.reason = reason
        super().__init__(reason, job_id=job_id)


SAFE_ERROR_DETAILS = {
    "source_identity_conflict": "source identity conflicts with existing records",
    "ingestion_error": "ingestion failed during deterministic processing",
    "ingestion_interrupted": "ingestion was interrupted before reaching a terminal state",
    "ingestion_input_missing": "staged ingestion input is unavailable",
    "ingestion_input_invalid": "staged ingestion input failed integrity validation",
}
DEFAULT_MAX_ATTEMPTS = 3


MEMORY_MARKERS = {
    "decision": r"(?:decision|quy(?:ế|e)t định|we (?:will|chose|choose|decided to))",
    "assumption": r"(?:assumption|giả định|gia dinh)",
    "constraint": r"(?:constraint|ràng buộc|rang buoc)",
    "alternative": r"(?:alternative|phương án|phuong an)",
}
MEMORY_PATTERNS = {
    kind: (
        re.compile(rf"^(?:{marker})\s*[:\-]\s*(.+)$", re.I),
        re.compile(rf"^#{{1,6}}\s+(?:{marker})\s*[:\-]?\s*(.*)$", re.I),
    )
    for kind, marker in MEMORY_MARKERS.items()
}
DECISION_PREFIX, DECISION_HEADING = MEMORY_PATTERNS["decision"]
RATIONALE_PREFIX = re.compile(r"^(?:rationale|reason|because|lý do)\s*[:\-]\s*(.+)$", re.I)
STATUS_PREFIX = re.compile(r"^(?:status|trạng thái)\s*[:\-]\s*(.+)$", re.I)


def line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def chunk_markdown(content: str, max_chars: int = 1600) -> list[TextSpan]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    paragraphs = list(re.finditer(r"\S(?:.|\n)*?(?=\n\s*\n|\Z)", content))
    newline_offsets = [index for index, value in enumerate(content) if value == "\n"]
    spans: list[TextSpan] = []
    current_start: int | None = None
    current_end = 0

    def append_span(raw_start: int, raw_end: int) -> None:
        raw = content[raw_start:raw_end]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        start = raw_start + left
        end = raw_start + right
        if end <= start:
            return
        spans.append(
            TextSpan(
                content[start:end],
                start,
                end,
                bisect_right(newline_offsets, start - 1) + 1,
                bisect_right(newline_offsets, max(start, end - 1)) + 1,
            )
        )

    def flush() -> None:
        nonlocal current_start, current_end
        if current_start is None:
            return
        append_span(current_start, current_end)
        current_start = None

    for paragraph in paragraphs:
        if paragraph.end() - paragraph.start() > max_chars:
            flush()
            for start in range(paragraph.start(), paragraph.end(), max_chars):
                append_span(start, min(start + max_chars, paragraph.end()))
        elif current_start is None:
            current_start, current_end = paragraph.start(), paragraph.end()
        elif paragraph.end() - current_start <= max_chars:
            current_end = paragraph.end()
        else:
            flush()
            current_start, current_end = paragraph.start(), paragraph.end()
    flush()
    return spans


def _match_memory_marker(value: str) -> tuple[str, re.Match[str]] | None:
    for kind, (prefix, heading) in MEMORY_PATTERNS.items():
        match = heading.match(value) or prefix.match(value)
        if match:
            return kind, match
    return None


def extract_memories(content: str) -> list[dict]:
    lines = content.splitlines(keepends=True)
    results: list[dict] = []
    cursor = 0
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        marker = _match_memory_marker(stripped)
        if not marker:
            cursor += len(raw)
            index += 1
            continue

        kind, match = marker
        statement = match.group(1).strip()
        title = statement or f"Recorded {kind}"
        start = cursor + len(raw) - len(raw.lstrip())
        end = cursor + len(raw.rstrip("\r\n"))
        rationale = None
        status = "active"
        lookahead_cursor = cursor + len(raw)
        found_metadata = False

        for next_index in range(index + 1, min(index + 7, len(lines))):
            candidate = lines[next_index].strip()
            if not candidate:
                lookahead_cursor += len(lines[next_index])
                if found_metadata:
                    break
                continue
            if candidate.startswith("#") or _match_memory_marker(candidate):
                break
            rationale_match = RATIONALE_PREFIX.match(candidate)
            status_match = STATUS_PREFIX.match(candidate)
            if rationale_match:
                found_metadata = True
                rationale = rationale_match.group(1).strip()
                end = lookahead_cursor + len(lines[next_index].rstrip("\r\n"))
            elif status_match:
                found_metadata = True
                normalized = status_match.group(1).strip().lower()
                if normalized in {"superseded", "replaced", "obsolete"}:
                    status = "obsolete"
                elif normalized in {"candidate", "active", "accepted", "rejected"}:
                    status = normalized
                else:
                    status = "candidate"
                end = lookahead_cursor + len(lines[next_index].rstrip("\r\n"))
            else:
                break
            lookahead_cursor += len(lines[next_index])

        quote = content[start:end]
        results.append(
            {
                "kind": kind,
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


def extract_decisions(content: str) -> list[dict]:
    """Compatibility view for callers that only consume deterministic decisions."""
    return [item for item in extract_memories(content) if item["kind"] == "decision"]


def index_source_version_chunks(
    session: Session, source: Source, version: SourceVersion, content: str
) -> None:
    """Build deterministic chunk and FTS rows without deriving governed memories."""
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


def _index_version(session: Session, source: Source, version: SourceVersion, content: str) -> None:
    index_source_version_chunks(session, source, version, content)
    for extracted in extract_memories(content):
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


def ingest_source(
    session: Session, payload: SourceCreate, *, commit: bool = True
) -> tuple[Source, bool]:
    digest = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
    source = None
    if payload.uri:
        matches = (
            session.query(Source)
            .filter(Source.workspace_id == payload.workspace_id, Source.uri == payload.uri)
            .all()
        )
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
            .filter(
                Source.workspace_id == payload.workspace_id,
                Source.uri.is_(None),
                SourceVersion.content_hash == digest,
            )
            .one_or_none()
        )
        if duplicate:
            return duplicate, False

    created = source is None
    if created:
        source_id = new_id()
        source = Source(
            id=source_id,
            workspace_id=payload.workspace_id,
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
        parser_version="deterministic-v2",
    )
    session.add(version)
    session.flush()
    source.current_version_id = version.id
    _index_version(session, source, version, payload.content)

    if commit:
        session.commit()
        session.refresh(source)
    return source, created


def ingestion_request_hash(payload: SourceCreate) -> tuple[str, str]:
    content_hash = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
    canonical = json.dumps(
        {
            "content_hash": content_hash,
            "kind": payload.kind,
            "title": payload.title,
            "uri": payload.uri,
            "workspace_id": payload.workspace_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), content_hash


def _existing_idempotent_result(
    session: Session,
    idempotency_key: str,
    request_hash: str,
) -> tuple[Source, bool, IngestionJob]:
    job = session.scalar(
        select(IngestionJob).where(IngestionJob.idempotency_key == idempotency_key)
    )
    if not job:
        raise IngestionIdempotencyConflict("unknown", "idempotency key could not be resolved")
    if job.request_hash != request_hash:
        raise IngestionIdempotencyConflict(
            job.id, "idempotency key was already used for a different request"
        )
    if job.state != "succeeded" or not job.source_id:
        raise IngestionIdempotencyConflict(
            job.id, "idempotent request has no reusable succeeded result; inspect or retry its job"
        )
    source = session.get(Source, job.source_id)
    if not source:
        raise IngestionIdempotencyConflict(
            job.id, "idempotent request result is no longer available"
        )
    return source, False, job


def _stage_ingestion_job(
    session: Session,
    payload: SourceCreate,
    *,
    idempotency_key: str | None,
    max_attempts: int,
) -> tuple[IngestionJob, bool]:
    request_hash, content_hash = ingestion_request_hash(payload)
    normalized_key = idempotency_key.strip() if idempotency_key else None
    if normalized_key:
        existing = session.scalar(
            select(IngestionJob).where(IngestionJob.idempotency_key == normalized_key)
        )
        if existing:
            _existing_idempotent_result(session, normalized_key, request_hash)
            return existing, True
    now = utc_now()
    job = IngestionJob(
        workspace_id=payload.workspace_id,
        state="running",
        stage="accepted",
        attempts=1,
        request_hash=request_hash,
        idempotency_key=normalized_key,
        max_attempts=max_attempts,
        retryable=False,
        started_at=now,
        updated_at=now,
    )
    session.add(job)
    session.flush()
    session.add(
        IngestionJobInput(
            job_id=job.id,
            workspace_id=payload.workspace_id,
            title=payload.title,
            kind=payload.kind,
            uri=payload.uri,
            content=payload.content,
            content_hash=content_hash,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        if normalized_key:
            _existing_idempotent_result(session, normalized_key, request_hash)
            existing = session.scalar(
                select(IngestionJob).where(IngestionJob.idempotency_key == normalized_key)
            )
            return existing, True
        raise
    return job, False


def _record_ingestion_failure(
    session: Session,
    job_id: str,
    error_code: str,
    *,
    force_dead_letter: bool = False,
    permanent: bool = False,
) -> IngestionJob:
    session.rollback()
    job = session.get(IngestionJob, job_id)
    if not job:
        raise IngestionJobNotFound(job_id)
    staged_input = session.get(IngestionJobInput, job_id)
    exhausted = (
        force_dead_letter or permanent or job.attempts >= job.max_attempts or staged_input is None
    )
    job.state = "dead_letter" if exhausted else "failed"
    job.error_code = "ingestion_input_missing" if staged_input is None else error_code
    job.error_detail = SAFE_ERROR_DETAILS[job.error_code]
    job.retryable = not exhausted
    job.finished_at = utc_now()
    job.updated_at = job.finished_at
    if exhausted and staged_input is not None:
        session.delete(staged_input)
    session.commit()
    return job


def _execute_staged_ingestion(session: Session, job_id: str) -> tuple[Source, bool, IngestionJob]:
    job = session.get(IngestionJob, job_id)
    staged_input = session.get(IngestionJobInput, job_id)
    if not job:
        raise IngestionJobNotFound(job_id)
    if not staged_input:
        _record_ingestion_failure(session, job_id, "ingestion_input_missing")
        raise IngestionRetryConflict(job_id, "staged ingestion input is unavailable")
    staged_content_hash = hashlib.sha256(staged_input.content.encode("utf-8")).hexdigest()
    if staged_content_hash != staged_input.content_hash:
        _record_ingestion_failure(
            session,
            job_id,
            "ingestion_input_invalid",
            force_dead_letter=True,
        )
        raise IngestionRetryConflict(job_id, "staged ingestion input failed integrity validation")

    job.stage = "indexing"
    job.updated_at = utc_now()
    session.commit()
    try:
        payload = SourceCreate(
            title=staged_input.title,
            kind=staged_input.kind,
            uri=staged_input.uri,
            content=staged_input.content,
            workspace_id=staged_input.workspace_id,
        )
        source, created = ingest_source(session, payload, commit=False)
        job = session.get(IngestionJob, job_id)
        staged_input = session.get(IngestionJobInput, job_id)
        job.source_id = source.id
        job.source_version_id = source.current_version_id
        job.state = "succeeded"
        job.stage = "ready"
        job.retryable = False
        job.error_code = None
        job.error_detail = None
        job.finished_at = utc_now()
        job.updated_at = job.finished_at
        session.delete(staged_input)
        session.commit()
    except Exception as exc:
        error_code = (
            "source_identity_conflict" if isinstance(exc, IngestionConflict) else "ingestion_error"
        )
        _record_ingestion_failure(
            session,
            job_id,
            error_code,
            permanent=isinstance(exc, IngestionConflict),
        )
        if isinstance(exc, IngestionConflict):
            raise IngestionConflict(
                SAFE_ERROR_DETAILS["source_identity_conflict"], job_id=job_id
            ) from exc
        raise IngestionExecutionError(job_id) from exc
    session.refresh(source)
    session.refresh(job)
    return source, created, job


def run_ingestion_job(
    session: Session,
    payload: SourceCreate,
    *,
    idempotency_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[Source, bool, IngestionJob]:
    """Stage input, then atomically commit domain writes with terminal job success."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    request_hash, _content_hash = ingestion_request_hash(payload)
    normalized_key = idempotency_key.strip() if idempotency_key else None
    if normalized_key:
        existing = session.scalar(
            select(IngestionJob).where(IngestionJob.idempotency_key == normalized_key)
        )
        if existing:
            return _existing_idempotent_result(session, normalized_key, request_hash)
    job, reused = _stage_ingestion_job(
        session,
        payload,
        idempotency_key=normalized_key,
        max_attempts=max_attempts,
    )
    if reused:
        return _existing_idempotent_result(session, normalized_key, request_hash)
    return _execute_staged_ingestion(session, job.id)


def retry_ingestion_job(session: Session, job_id: str) -> IngestionJob:
    job = session.get(IngestionJob, job_id)
    if not job:
        raise IngestionJobNotFound(job_id)
    expected_attempts = job.attempts
    now = utc_now()
    claimed = session.execute(
        update(IngestionJob)
        .where(
            IngestionJob.id == job_id,
            IngestionJob.state == "failed",
            IngestionJob.retryable.is_(True),
            IngestionJob.attempts == expected_attempts,
            IngestionJob.attempts < IngestionJob.max_attempts,
        )
        .values(
            state="running",
            stage="accepted",
            attempts=expected_attempts + 1,
            retryable=False,
            error_code=None,
            error_detail=None,
            started_at=now,
            finished_at=None,
            updated_at=now,
        )
    )
    if claimed.rowcount != 1:
        session.rollback()
        raise IngestionRetryConflict(job_id, "ingestion job is not claimable for retry")
    session.commit()
    _source, _created, completed_job = _execute_staged_ingestion(session, job_id)
    return completed_job


def recover_orphaned_ingestion_jobs(session: Session) -> int:
    jobs = list(session.scalars(select(IngestionJob).where(IngestionJob.state == "running")).all())
    for job in jobs:
        staged_input = session.get(IngestionJobInput, job.id)
        exhausted = job.attempts >= job.max_attempts or staged_input is None
        input_invalid = (
            staged_input is not None
            and hashlib.sha256(staged_input.content.encode("utf-8")).hexdigest()
            != staged_input.content_hash
        )
        job.error_code = (
            "ingestion_input_missing"
            if staged_input is None
            else "ingestion_input_invalid"
            if input_invalid
            else "ingestion_interrupted"
        )
        exhausted = exhausted or input_invalid
        job.state = "dead_letter" if exhausted else "failed"
        job.retryable = not exhausted
        job.error_detail = SAFE_ERROR_DETAILS[job.error_code]
        job.finished_at = utc_now()
        job.updated_at = job.finished_at
        if exhausted and staged_input is not None:
            session.delete(staged_input)
    session.commit()
    return len(jobs)


def source_deletion_impact(session: Session, source: Source) -> SourceDeletionImpact:
    """Count records affected by deleting a source without loading content-bearing rows."""
    row = (
        session.execute(
            text(
                """SELECT
                (SELECT count(*) FROM source_versions WHERE source_id = :source) AS versions,
                (SELECT count(*) FROM chunks WHERE source_id = :source) AS chunks,
                (SELECT count(*) FROM chunk_embeddings WHERE source_id = :source) AS embeddings,
                (SELECT count(*) FROM chunk_vector_buckets WHERE source_id = :source)
                    AS vector_index_rows,
                (SELECT count(*) FROM decisions
                   WHERE source_id = :source AND kind = 'decision') AS decisions,
                (SELECT count(*) FROM decisions WHERE source_id = :source) AS memories,
                (SELECT count(*) FROM evidence WHERE source_id = :source) AS evidence,
                (SELECT count(*) FROM decision_relations
                   WHERE source_decision_id IN
                         (SELECT id FROM decisions WHERE source_id = :source)
                      OR target_decision_id IN
                         (SELECT id FROM decisions WHERE source_id = :source))
                    AS decision_relations,
                (SELECT count(*) FROM study_cards WHERE source_id = :source) AS study_cards,
                (SELECT count(*) FROM study_reviews WHERE card_id IN
                    (SELECT id FROM study_cards WHERE source_id = :source)) AS study_reviews,
                (SELECT count(*) FROM ingestion_jobs WHERE source_id = :source)
                    AS ingestion_jobs_to_detach,
                (SELECT count(*) FROM audit_events
                   WHERE (object_type = 'source' AND object_id = :source)
                      OR (object_type IN ('decision', 'memory') AND object_id IN
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


def delete_source(session: Session, source: Source, *, commit: bool = True) -> None:
    session.execute(
        update(IngestionJob)
        .where(IngestionJob.source_id == source.id)
        .values(source_id=None, source_version_id=None)
    )
    session.execute(
        text(
            """DELETE FROM audit_events
               WHERE object_type IN ('decision', 'memory')
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
    if commit:
        session.commit()
