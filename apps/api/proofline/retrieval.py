from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from .schemas import SearchHit


def lexical_search(session: Session, query: str, limit: int = 10) -> list[SearchHit]:
    """Search current source versions while treating user input as terms, not FTS syntax."""
    terms = re.findall(r"[\w\-]+", query, flags=re.UNICODE)
    if not terms:
        return []
    fts_query = " OR ".join(f'"{term}"' for term in terms)
    rows = session.execute(
        text(
            """
            SELECT c.id, c.source_id, c.source_version_id, s.title, c.content,
                   c.start_offset, c.end_offset, c.start_line, c.end_line,
                   bm25(chunk_search) AS rank
            FROM chunk_search
            JOIN chunks c ON c.id = chunk_search.chunk_id
            JOIN sources s ON s.id = c.source_id
            WHERE chunk_search MATCH :query
              AND c.source_version_id = s.current_version_id
            ORDER BY rank
            LIMIT :limit
            """
        ),
        {"query": fts_query, "limit": limit},
    ).all()
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
        )
        for row in rows
    ]
