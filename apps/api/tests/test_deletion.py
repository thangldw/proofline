import hashlib

from proofline.models import (
    AuditEvent,
    Chunk,
    ChunkEmbedding,
    Decision,
    Evidence,
    IngestionJob,
    Source,
    SourceVersion,
)
from sqlalchemy import func, select, text


def count_for_source(session, model, source_id):
    return session.scalar(
        select(func.count()).select_from(model).where(model.source_id == source_id)
    )


def test_deletion_impact_matches_complete_cascade_and_detaches_jobs(client, session):
    uri = "file:///architecture/queue.md"
    first = client.post(
        "/api/v1/sources",
        json={
            "title": "Queue ADR v1",
            "uri": uri,
            "content": "Decision: Use Kafka\nReason: high throughput",
        },
    )
    assert first.status_code == 201
    source_id = first.json()["id"]
    job_ids = [first.headers["x-proofline-job-id"]]
    old_decision = client.get("/api/v1/decisions").json()[0]
    assert (
        client.patch(
            f"/api/v1/decisions/{old_decision['id']}", json={"status": "accepted"}
        ).status_code
        == 200
    )

    second = client.post(
        "/api/v1/sources",
        json={
            "title": "Queue ADR v2",
            "uri": uri,
            "content": "Decision: Use NATS\nReason: operational simplicity",
        },
    )
    assert second.status_code == 200
    job_ids.append(second.headers["x-proofline-job-id"])
    current_decision = client.get("/api/v1/decisions").json()[0]
    assert (
        client.patch(
            f"/api/v1/decisions/{current_decision['id']}", json={"status": "accepted"}
        ).status_code
        == 200
    )

    unrelated = client.post(
        "/api/v1/sources",
        json={
            "title": "Unrelated ADR",
            "uri": "file:///architecture/storage.md",
            "content": "Decision: Keep unrelated storage evidence",
        },
    )
    assert unrelated.status_code == 201
    unrelated_source_id = unrelated.json()["id"]

    chunks = list(session.scalars(select(Chunk).where(Chunk.source_id == source_id)).all())
    assert len(chunks) == 2
    for chunk in chunks:
        session.add(
            ChunkEmbedding(
                chunk_id=chunk.id,
                source_id=source_id,
                source_version_id=chunk.source_version_id,
                provider_id="test-embedding-provider",
                model_id="test-embedding-model",
                dimensions=2,
                vector_json=[0.25, 0.75],
                content_hash=hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
            )
        )
    session.add(
        AuditEvent(
            action="source.metadata_reviewed",
            object_type="source",
            object_id=source_id,
            before_json={},
            after_json={},
        )
    )
    session.commit()

    preview_response = client.get(f"/api/v1/sources/{source_id}/deletion-impact")
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview == {
        "source_id": source_id,
        "title": "Queue ADR v2",
        "current_version_id": second.json()["current_version_id"],
        "versions": 2,
        "chunks": 2,
        "embeddings": 2,
        "vector_index_rows": 0,
        "decisions": 2,
        "memories": 2,
        "evidence": 2,
        "decision_relations": 0,
        "study_cards": 0,
        "study_reviews": 0,
        "action_proposals": 0,
        "proposal_citations": 0,
        "studio_artifacts": 0,
        "studio_citations": 0,
        "ingestion_jobs_to_detach": 2,
        "audit_events_to_delete": 3,
        "fts_rows": 2,
    }
    assert "content" not in preview

    decision_ids = list(
        session.scalars(select(Decision.id).where(Decision.source_id == source_id)).all()
    )
    deleted = client.delete(f"/api/v1/sources/{source_id}")
    assert deleted.status_code == 204
    session.expire_all()

    assert session.get(Source, source_id) is None
    assert count_for_source(session, SourceVersion, source_id) == 0
    assert count_for_source(session, Chunk, source_id) == 0
    assert count_for_source(session, ChunkEmbedding, source_id) == 0
    assert count_for_source(session, Decision, source_id) == 0
    assert count_for_source(session, Evidence, source_id) == 0
    assert (
        session.execute(
            text("SELECT count(*) FROM chunk_search WHERE source_id = :source"),
            {"source": source_id},
        ).scalar_one()
        == 0
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.object_id.in_([source_id, *decision_ids]))
        )
        == 0
    )

    jobs = list(
        session.scalars(
            select(IngestionJob).where(IngestionJob.id.in_(job_ids)).order_by(IngestionJob.id)
        ).all()
    )
    assert len(jobs) == 2
    assert all(job.source_id is None for job in jobs)
    assert all(job.source_version_id is None for job in jobs)

    assert client.get(f"/api/v1/sources/{source_id}/deletion-impact").status_code == 404
    assert client.get(f"/api/v1/sources/{unrelated_source_id}").status_code == 200
    assert client.get("/api/v1/search", params={"q": "unrelated storage"}).json()["hits"]
    assert session.execute(text("SELECT count(*) FROM chunk_search")).scalar_one() == 1
