import proofline.embeddings as embeddings_module
from proofline.embeddings import hybrid_search, index_current_embeddings
from proofline.ingestion import delete_source, ingest_source
from proofline.model_gateway import FakeEmbeddingProvider
from proofline.models import Chunk, ChunkEmbedding
from proofline.schemas import SearchHit, SourceCreate
from sqlalchemy import func, select


def test_incremental_embedding_index_and_semantic_retrieval(session):
    storage, _ = ingest_source(
        session,
        SourceCreate(
            title="Storage ADR",
            uri="file:///storage.md",
            content="Decision: Use SQLite for local metadata.",
        ),
    )
    messaging, _ = ingest_source(
        session,
        SourceCreate(
            title="Messaging ADR",
            uri="file:///messaging.md",
            content="Decision: Use NATS for control-plane events.",
        ),
    )
    chunks = list(session.scalars(select(Chunk).order_by(Chunk.source_id)).all())
    vectors = {
        chunk.content: [1.0, 0.0] if chunk.source_id == storage.id else [0.0, 1.0]
        for chunk in chunks
    }
    vectors["single-node persistence choice"] = [1.0, 0.0]
    vectors["SQLite local metadata"] = [1.0, 0.0]
    provider = FakeEmbeddingProvider(vectors)

    first = index_current_embeddings(session, provider, batch_size=1)
    second = index_current_embeddings(session, provider, batch_size=1)
    semantic_only = hybrid_search(session, "single-node persistence choice", provider, 5)
    overlap = hybrid_search(session, "SQLite local metadata", provider, 5)

    assert first.indexed == 2
    assert len(first.model_run_ids) == 2
    assert second.indexed == 0
    assert second.skipped == 2
    assert semantic_only[0].source_id == storage.id
    assert semantic_only[0].retrieval_channels == ["semantic"]
    assert overlap[0].source_id == storage.id
    assert overlap[0].retrieval_channels == ["lexical", "semantic"]

    delete_source(session, messaging)
    assert (
        session.scalar(
            select(func.count())
            .select_from(ChunkEmbedding)
            .where(ChunkEmbedding.source_id == messaging.id)
        )
        == 0
    )


def test_old_version_embeddings_are_excluded_from_semantic_search(session):
    source, _ = ingest_source(
        session,
        SourceCreate(
            title="Queue ADR",
            uri="file:///queue.md",
            content="Decision: Use Kafka for very high throughput.",
        ),
    )
    old_chunk = session.scalar(select(Chunk).where(Chunk.source_id == source.id))
    provider = FakeEmbeddingProvider(
        {
            old_chunk.content: [1.0, 0.0],
            "legacy streaming platform": [1.0, 0.0],
        }
    )
    index_current_embeddings(session, provider)
    ingest_source(
        session,
        SourceCreate(
            title="Queue ADR updated",
            uri="file:///queue.md",
            content="Decision: Use NATS for modest control traffic.",
        ),
    )

    hits = hybrid_search(session, "legacy streaming platform", provider, 5)

    assert all(hit.chunk_id != old_chunk.id for hit in hits)


def search_hit(chunk_id: str, source_id: str, rank: float = -1.0) -> SearchHit:
    content = f"exact content for {chunk_id}"
    return SearchHit(
        chunk_id=chunk_id,
        source_id=source_id,
        source_version_id=f"version-{source_id}",
        source_title=f"Source {source_id}",
        content=content,
        start_offset=10,
        end_offset=10 + len(content),
        start_line=2,
        end_line=2,
        rank=rank,
    )


def test_lexical_diversity_cap_backfills_in_original_rank_order(monkeypatch, session):
    ranked = [
        search_hit("a-1", "a"),
        search_hit("a-2", "a"),
        search_hit("a-3", "a"),
        search_hit("b-1", "b"),
        search_hit("c-1", "c"),
    ]
    monkeypatch.setattr(embeddings_module, "lexical_search", lambda *_args: ranked)

    hits = hybrid_search(session, "queue", None, limit=4, max_per_source=1)

    assert [hit.chunk_id for hit in hits] == ["a-1", "b-1", "c-1", "a-2"]
    assert [(hit.start_offset, hit.end_offset, hit.content) for hit in hits] == [
        (item.start_offset, item.end_offset, item.content)
        for item in [ranked[0], ranked[3], ranked[4], ranked[1]]
    ]
    assert [hit.lexical_rank for hit in hits] == [1, 4, 5, 2]


def test_diversity_cap_does_not_drop_single_source_results(monkeypatch, session):
    ranked = [search_hit(f"a-{index}", "a") for index in range(1, 6)]
    monkeypatch.setattr(embeddings_module, "lexical_search", lambda *_args: ranked)

    first = hybrid_search(session, "queue", None, limit=4, max_per_source=1)
    second = hybrid_search(session, "queue", None, limit=4, max_per_source=1)

    assert [hit.chunk_id for hit in first] == ["a-1", "a-2", "a-3", "a-4"]
    assert [hit.chunk_id for hit in second] == [hit.chunk_id for hit in first]


def test_hybrid_diversity_preserves_deterministic_rrf_metadata(monkeypatch, session):
    lexical = [
        search_hit("a-1", "a"),
        search_hit("a-2", "a"),
        search_hit("a-3", "a"),
        search_hit("b-1", "b"),
    ]
    semantic = [
        search_hit("a-1", "a").model_copy(
            update={"semantic_score": 0.99, "retrieval_channels": ["semantic"]}
        ),
        search_hit("a-2", "a").model_copy(
            update={"semantic_score": 0.98, "retrieval_channels": ["semantic"]}
        ),
        search_hit("c-1", "c").model_copy(
            update={"semantic_score": 0.97, "retrieval_channels": ["semantic"]}
        ),
    ]
    monkeypatch.setattr(embeddings_module, "lexical_search", lambda *_args: lexical)
    monkeypatch.setattr(embeddings_module, "semantic_search", lambda *_args: semantic)

    first = hybrid_search(session, "queue", object(), limit=4, max_per_source=1)
    second = hybrid_search(session, "queue", object(), limit=4, max_per_source=1)

    assert [hit.chunk_id for hit in first] == ["a-1", "c-1", "b-1", "a-2"]
    assert [hit.chunk_id for hit in second] == [hit.chunk_id for hit in first]
    assert first[0].retrieval_channels == ["lexical", "semantic"]
    assert first[0].lexical_rank == 1
    assert first[0].semantic_rank == 1
    assert first[0].semantic_score == 0.99
    assert first[0].fused_score == (1 / 61) + (1 / 61)
