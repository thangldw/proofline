from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .model_gateway import EmbeddingProvider, EmbeddingRequest, run_embedding
from .models import Chunk, ChunkEmbedding, Source
from .retrieval import lexical_search
from .schemas import SearchHit


@dataclass(frozen=True, slots=True)
class EmbeddingIndexReport:
    indexed: int
    skipped: int
    model_run_ids: list[str]


def chunk_fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def index_current_embeddings(
    session: Session,
    provider: EmbeddingProvider,
    batch_size: int = 64,
) -> EmbeddingIndexReport:
    chunks = list(
        session.scalars(
            select(Chunk)
            .join(Source)
            .where(Chunk.source_version_id == Source.current_version_id)
            .order_by(Chunk.source_id, Chunk.ordinal)
        ).all()
    )
    existing = {
        item.chunk_id: item
        for item in session.scalars(
            select(ChunkEmbedding).where(
                ChunkEmbedding.provider_id == provider.id,
                ChunkEmbedding.model_id == provider.model,
            )
        ).all()
    }
    pending: list[tuple[Chunk, str]] = []
    skipped = 0
    for chunk in chunks:
        fingerprint = chunk_fingerprint(chunk.content)
        stored = existing.get(chunk.id)
        if stored and stored.content_hash == fingerprint:
            skipped += 1
        else:
            pending.append((chunk, fingerprint))

    run_ids: list[str] = []
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        request = EmbeddingRequest(
            texts=[chunk.content for chunk, _fingerprint in batch],
            input_hashes=[fingerprint for _chunk, fingerprint in batch],
            template_version="chunk-embedding-v1",
        )
        result, run = run_embedding(session, provider, request)
        run_ids.append(run.id)
        for (chunk, fingerprint), vector in zip(batch, result.vectors, strict=True):
            session.execute(
                delete(ChunkEmbedding).where(
                    ChunkEmbedding.chunk_id == chunk.id,
                    ChunkEmbedding.provider_id == provider.id,
                    ChunkEmbedding.model_id == provider.model,
                )
            )
            session.add(
                ChunkEmbedding(
                    chunk_id=chunk.id,
                    source_id=chunk.source_id,
                    source_version_id=chunk.source_version_id,
                    provider_id=provider.id,
                    model_id=provider.model,
                    dimensions=len(vector),
                    vector_json=vector,
                    content_hash=fingerprint,
                )
            )
        session.commit()
    return EmbeddingIndexReport(len(pending), skipped, run_ids)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return -1.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def semantic_search(
    session: Session,
    query: str,
    provider: EmbeddingProvider,
    limit: int = 10,
) -> list[SearchHit]:
    rows = session.execute(
        select(ChunkEmbedding, Chunk, Source.title)
        .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
        .join(Source, Source.id == Chunk.source_id)
        .where(
            ChunkEmbedding.provider_id == provider.id,
            ChunkEmbedding.model_id == provider.model,
            Chunk.source_version_id == Source.current_version_id,
        )
    ).all()
    if not rows:
        return []
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
    result, _run = run_embedding(
        session,
        provider,
        EmbeddingRequest(
            texts=[query], input_hashes=[query_hash], template_version="query-embedding-v1"
        ),
    )
    query_vector = result.vectors[0]
    scored = sorted(
        (
            (cosine_similarity(query_vector, embedding.vector_json), chunk, title)
            for embedding, chunk, title in rows
        ),
        key=lambda item: (-item[0], item[1].id),
    )[:limit]
    return [
        SearchHit(
            chunk_id=chunk.id,
            source_id=chunk.source_id,
            source_version_id=chunk.source_version_id,
            source_title=title,
            content=chunk.content,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            rank=-score,
            retrieval_channels=["semantic"],
            semantic_rank=index,
            semantic_score=score,
        )
        for index, (score, chunk, title) in enumerate(scored, start=1)
    ]


def hybrid_search(
    session: Session,
    query: str,
    provider: EmbeddingProvider | None,
    limit: int = 10,
    rrf_constant: int = 60,
    max_per_source: int = 2,
) -> list[SearchHit]:
    lexical = lexical_search(session, query, max(limit * 3, limit))
    lexical = [
        hit.model_copy(update={"lexical_rank": index, "retrieval_channels": ["lexical"]})
        for index, hit in enumerate(lexical, start=1)
    ]
    semantic = semantic_search(session, query, provider, max(limit * 3, limit)) if provider else []
    hits_by_id = {hit.chunk_id: hit for hit in [*lexical, *semantic]}
    scores: dict[str, float] = {}
    lexical_ranks = {hit.chunk_id: index for index, hit in enumerate(lexical, start=1)}
    semantic_ranks = {hit.chunk_id: index for index, hit in enumerate(semantic, start=1)}
    for chunk_id, rank in lexical_ranks.items():
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (rrf_constant + rank)
    for chunk_id, rank in semantic_ranks.items():
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (rrf_constant + rank)
    ranked_ids = sorted(
        scores,
        key=lambda chunk_id: (
            -scores[chunk_id],
            lexical_ranks.get(chunk_id, math.inf),
            semantic_ranks.get(chunk_id, math.inf),
            chunk_id,
        ),
    )
    selected_ids: list[str] = []
    deferred_ids: list[str] = []
    source_counts: dict[str, int] = {}
    for chunk_id in ranked_ids:
        source_id = hits_by_id[chunk_id].source_id
        if source_counts.get(source_id, 0) < max_per_source:
            selected_ids.append(chunk_id)
            source_counts[source_id] = source_counts.get(source_id, 0) + 1
        else:
            deferred_ids.append(chunk_id)
        if len(selected_ids) == limit:
            break
    if len(selected_ids) < limit:
        selected_ids.extend(deferred_ids[: limit - len(selected_ids)])
    return [
        hits_by_id[chunk_id].model_copy(
            update={
                "rank": -scores[chunk_id],
                "fused_score": scores[chunk_id],
                "lexical_rank": lexical_ranks.get(chunk_id),
                "semantic_rank": semantic_ranks.get(chunk_id),
                "semantic_score": next(
                    (hit.semantic_score for hit in semantic if hit.chunk_id == chunk_id),
                    None,
                ),
                "retrieval_channels": [
                    channel
                    for channel, ranks in (
                        ("lexical", lexical_ranks),
                        ("semantic", semantic_ranks),
                    )
                    if chunk_id in ranks
                ],
            }
        )
        for chunk_id in selected_ids
    ]
