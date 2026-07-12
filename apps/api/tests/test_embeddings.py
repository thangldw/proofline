from proofline.embeddings import hybrid_search, index_current_embeddings
from proofline.ingestion import delete_source, ingest_source
from proofline.model_gateway import FakeEmbeddingProvider
from proofline.models import Chunk, ChunkEmbedding
from proofline.schemas import SourceCreate
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
