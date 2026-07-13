from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import DateTime, bindparam, text
from sqlalchemy.orm import Session

from .models import DEFAULT_WORKSPACE_ID
from .schemas import SearchHit

ENGLISH_QUERY_STOPWORDS = {
    "a",
    "and",
    "be",
    "for",
    "how",
    "is",
    "should",
    "the",
    "to",
    "use",
    "was",
    "what",
    "when",
    "which",
    "why",
}


def lexical_search(
    session: Session,
    query: str,
    limit: int = 10,
    source_ids: list[str] | None = None,
    ingested_from: datetime | None = None,
    ingested_before: datetime | None = None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> list[SearchHit]:
    """Search current source versions while treating user input as terms, not FTS syntax."""
    raw_terms = re.findall(r"[\w\-]+", query, flags=re.UNICODE)
    terms = [term for term in raw_terms if term.casefold() not in ENGLISH_QUERY_STOPWORDS]
    if not terms:
        terms = raw_terms
    if not terms:
        return []
    if source_ids == []:
        return []
    fts_query = " OR ".join(f'"{term}"' for term in terms)
    filters = [
        "chunk_search MATCH :query",
        "c.source_version_id = s.current_version_id",
        "s.workspace_id = :workspace_id",
    ]
    parameters: dict = {"query": fts_query, "limit": limit, "workspace_id": workspace_id}
    if source_ids is not None:
        filters.append("c.source_id IN :source_ids")
        parameters["source_ids"] = source_ids
    if ingested_from is not None:
        filters.append("sv.created_at >= :ingested_from")
        parameters["ingested_from"] = ingested_from
    if ingested_before is not None:
        filters.append("sv.created_at < :ingested_before")
        parameters["ingested_before"] = ingested_before
    statement = text(
        f"""
            SELECT c.id, c.source_id, c.source_version_id, s.title, c.content,
                   c.start_offset, c.end_offset, c.start_line, c.end_line,
                   bm25(chunk_search) AS rank, s.kind, s.git_commit_sha, s.git_path,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM decisions d
                       WHERE d.source_id = s.id
                         AND d.source_version_id = s.current_version_id
                         AND d.kind = 'decision'
                         AND (d.status = 'obsolete' OR d.valid_to IS NOT NULL)
                   ) THEN 1 ELSE 0 END AS temporal_rank,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM decisions d
                       WHERE d.source_id = s.id
                         AND d.source_version_id = s.current_version_id
                         AND d.kind = 'decision'
                         AND d.status IN ('active', 'accepted')
                         AND d.valid_to IS NULL
                   ) THEN 1 ELSE 0 END AS is_current_decision
            FROM chunk_search
            JOIN chunks c ON c.id = chunk_search.chunk_id
            JOIN sources s ON s.id = c.source_id
            JOIN source_versions sv ON sv.id = c.source_version_id
            WHERE {" AND ".join(filters)}
            ORDER BY temporal_rank, rank, c.id
            LIMIT :limit
            """
    )
    if source_ids is not None:
        statement = statement.bindparams(bindparam("source_ids", expanding=True))
    if ingested_from is not None:
        statement = statement.bindparams(bindparam("ingested_from", type_=DateTime()))
    if ingested_before is not None:
        statement = statement.bindparams(bindparam("ingested_before", type_=DateTime()))
    rows = session.execute(statement, parameters).all()
    return [
        SearchHit(
            chunk_id=row[0],
            source_id=row[1],
            source_version_id=row[2],
            source_title=row[3],
            content=row[4],
            start_offset=row[5],
            end_offset=row[6],
            start_line=row[7],
            end_line=row[8],
            rank=row[9],
            source_kind=row[10],
            git_commit_sha=row[11],
            git_path=row[12],
            temporal_priority="current_decision" if row[14] == 1 else "neutral",
        )
        for row in rows
    ]
