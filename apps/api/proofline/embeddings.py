from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from .model_gateway import EmbeddingProvider, EmbeddingRequest, run_embedding
from .models import (
    DEFAULT_WORKSPACE_ID,
    Chunk,
    ChunkEmbedding,
    ChunkVectorBucket,
    Source,
    SourceVersion,
)
from .reranking import Reranker, apply_reranking
from .retrieval import lexical_search
from .schemas import SearchHit


@dataclass(frozen=True, slots=True)
class EmbeddingIndexReport:
    indexed: int
    skipped: int
    model_run_ids: list[str]


def chunk_fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def vector_bands(vector: list[float], band_width: int = 16) -> list[tuple[int, str]]:
    bits = "".join("1" if value >= 0 else "0" for value in vector[:64])
    return [
        (index // band_width, bits[index : index + band_width])
        for index in range(0, len(bits), band_width)
        if bits[index : index + band_width]
    ]


def index_current_embeddings(
    session: Session,
    provider: EmbeddingProvider,
    batch_size: int = 64,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> EmbeddingIndexReport:
    chunks = list(
        session.scalars(
            select(Chunk)
            .join(Source)
            .where(
                Chunk.source_version_id == Source.current_version_id,
                Source.workspace_id == workspace_id,
            )
            .order_by(Chunk.source_id, Chunk.ordinal)
        ).all()
    )
    existing = {
        item.chunk_id: item
        for item in session.scalars(
            select(ChunkEmbedding).where(
                ChunkEmbedding.provider_id == provider.id,
                ChunkEmbedding.model_id == provider.model,
                ChunkEmbedding.source_id.in_(
                    select(Source.id).where(Source.workspace_id == workspace_id)
                ),
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
            workspace_id=workspace_id,
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
            embedding = ChunkEmbedding(
                chunk_id=chunk.id,
                source_id=chunk.source_id,
                source_version_id=chunk.source_version_id,
                provider_id=provider.id,
                model_id=provider.model,
                dimensions=len(vector),
                vector_json=vector,
                content_hash=fingerprint,
            )
            session.add(embedding)
            session.flush()
            session.add_all(
                ChunkVectorBucket(
                    embedding_id=embedding.id,
                    chunk_id=chunk.id,
                    source_id=chunk.source_id,
                    source_version_id=chunk.source_version_id,
                    provider_id=provider.id,
                    model_id=provider.model,
                    band_index=band_index,
                    band_value=band_value,
                )
                for band_index, band_value in vector_bands(vector)
            )
        session.commit()
    return EmbeddingIndexReport(len(pending), skipped, run_ids)


def cosine_similarity(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or not left:
        return None
    if not all(math.isfinite(value) for value in [*left, *right]):
        return None
    left_norm = math.hypot(*left)
    right_norm = math.hypot(*right)
    if (
        left_norm == 0
        or right_norm == 0
        or not math.isfinite(left_norm)
        or not math.isfinite(right_norm)
    ):
        return None
    score = sum((a / left_norm) * (b / right_norm) for a, b in zip(left, right, strict=True))
    if not math.isfinite(score):
        return None
    return max(-1.0, min(1.0, score))


def semantic_search(
    session: Session,
    query: str,
    provider: EmbeddingProvider,
    limit: int = 10,
    min_semantic_score: float = 0.0,
    source_ids: list[str] | None = None,
    ingested_from: datetime | None = None,
    ingested_before: datetime | None = None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> list[SearchHit]:
    if not math.isfinite(min_semantic_score) or not 0 <= min_semantic_score <= 1:
        raise ValueError("min_semantic_score must be finite and between 0 and 1")
    if source_ids == []:
        return []
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
    result, _run = run_embedding(
        session,
        provider,
        EmbeddingRequest(
            texts=[query],
            input_hashes=[query_hash],
            template_version="query-embedding-v1",
            workspace_id=workspace_id,
        ),
    )
    query_vector = result.vectors[0]
    bands = vector_bands(query_vector)
    if not bands:
        return []
    statement = (
        select(ChunkEmbedding, Chunk, Source)
        .join(ChunkVectorBucket, ChunkVectorBucket.embedding_id == ChunkEmbedding.id)
        .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
        .join(Source, Source.id == Chunk.source_id)
        .join(SourceVersion, SourceVersion.id == Chunk.source_version_id)
        .where(
            ChunkEmbedding.provider_id == provider.id,
            ChunkEmbedding.model_id == provider.model,
            Chunk.source_version_id == Source.current_version_id,
            Source.workspace_id == workspace_id,
            or_(
                *[
                    and_(
                        ChunkVectorBucket.band_index == band_index,
                        ChunkVectorBucket.band_value == band_value,
                    )
                    for band_index, band_value in bands
                ]
            ),
        )
        .distinct()
        .limit(max(limit * 20, 100))
    )
    if source_ids is not None:
        statement = statement.where(Chunk.source_id.in_(source_ids))
    if ingested_from is not None:
        statement = statement.where(SourceVersion.created_at >= ingested_from)
    if ingested_before is not None:
        statement = statement.where(SourceVersion.created_at < ingested_before)
    rows = session.execute(statement).all()
    if not rows:
        return []
    candidates = []
    for embedding, chunk, source in rows:
        score = cosine_similarity(query_vector, embedding.vector_json)
        if score is not None and score >= min_semantic_score:
            current = any(
                decision.kind == "decision"
                and decision.source_version_id == source.current_version_id
                and decision.status in {"active", "accepted"}
                and decision.valid_to is None
                for decision in source.decisions
            )
            obsolete = any(
                decision.kind == "decision"
                and decision.source_version_id == source.current_version_id
                and (decision.status == "obsolete" or decision.valid_to is not None)
                for decision in source.decisions
            )
            candidates.append((score, current, obsolete, chunk, source))
    scored = sorted(
        candidates,
        key=lambda item: (int(item[2]), -item[0], item[3].id),
    )[:limit]
    return [
        SearchHit(
            chunk_id=chunk.id,
            source_id=chunk.source_id,
            source_version_id=chunk.source_version_id,
            source_title=source.title,
            content=chunk.content,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            rank=-score,
            retrieval_channels=["semantic"],
            semantic_rank=index,
            semantic_score=score,
            source_kind=source.kind,
            git_commit_sha=source.git_commit_sha,
            git_path=source.git_path,
            temporal_priority="current_decision" if current else "neutral",
        )
        for index, (score, current, _obsolete, chunk, source) in enumerate(scored, start=1)
    ]


def hybrid_search(
    session: Session,
    query: str,
    provider: EmbeddingProvider | None,
    limit: int = 10,
    rrf_constant: int = 60,
    max_per_source: int = 2,
    min_semantic_score: float = 0.0,
    source_ids: list[str] | None = None,
    ingested_from: datetime | None = None,
    ingested_before: datetime | None = None,
    reranker: Reranker | None = None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> list[SearchHit]:
    lexical = lexical_search(
        session,
        query,
        max(limit * 3, limit),
        source_ids,
        ingested_from,
        ingested_before,
        workspace_id,
    )
    lexical = [
        hit.model_copy(update={"lexical_rank": index, "retrieval_channels": ["lexical"]})
        for index, hit in enumerate(lexical, start=1)
    ]
    semantic = (
        semantic_search(
            session,
            query,
            provider,
            max(limit * 3, limit),
            min_semantic_score,
            source_ids,
            ingested_from,
            ingested_before,
            workspace_id,
        )
        if provider
        else []
    )
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
    result = [
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
    return apply_reranking(query, result, reranker) if reranker and result else result
