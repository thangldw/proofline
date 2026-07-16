import hashlib

import proofline.ingestion as ingestion_module
import pytest
from fastapi.testclient import TestClient
from proofline.database import initialize_database, make_engine
from proofline.ingestion import (
    IngestionConflict,
    IngestionExecutionError,
    IngestionRetryConflict,
    retry_ingestion_job,
    run_ingestion_job,
)
from proofline.main import create_app
from proofline.models import (
    Chunk,
    Decision,
    Evidence,
    IngestionJob,
    IngestionJobInput,
    Source,
    SourceVersion,
)
from proofline.schemas import SourceCreate
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker


def assert_failed_ingestion_has_no_partial_domain_state(session, job_id: str) -> None:
    session.expire_all()
    job = session.get(IngestionJob, job_id)
    assert job.state == "failed"
    assert job.stage == "indexing"
    assert job.retryable is True
    assert job.error_code == "ingestion_error"
    assert session.get(IngestionJobInput, job_id) is not None
    for model in (Source, SourceVersion, Chunk, Decision, Evidence):
        assert session.scalar(select(func.count()).select_from(model)) == 0
    assert session.execute(text("SELECT count(*) FROM chunk_search")).scalar_one() == 0


def test_idempotency_key_reuses_success_and_rejects_payload_mismatch(client, session):
    payload = {
        "title": "Idempotent ADR",
        "uri": "file:///idempotent.md",
        "content": "Decision: Preserve one immutable result",
    }
    headers = {"Idempotency-Key": "import-idempotent-adr"}

    first = client.post("/api/v1/sources", json=payload, headers=headers)
    replay = client.post("/api/v1/sources", json=payload, headers=headers)
    mismatch = client.post(
        "/api/v1/sources",
        json={**payload, "content": "Decision: A different payload"},
        headers=headers,
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert replay.headers["x-proofline-job-id"] == first.headers["x-proofline-job-id"]
    assert mismatch.status_code == 409
    assert mismatch.headers["x-proofline-job-id"] == first.headers["x-proofline-job-id"]
    assert session.scalar(select(func.count()).select_from(IngestionJob)) == 1
    assert session.scalar(select(func.count()).select_from(SourceVersion)) == 1
    assert session.scalar(select(func.count()).select_from(IngestionJobInput)) == 0
    public_job = client.get(f"/api/v1/jobs/{first.headers['x-proofline-job-id']}").json()
    assert public_job["request_hash"] is not None
    assert public_job["max_attempts"] == 3
    assert public_job["started_at"] is not None
    assert public_job["finished_at"] is not None
    assert "idempotency_key" not in public_job
    assert "content" not in public_job


def test_crash_rolls_back_domain_then_retry_claim_succeeds(client, session, monkeypatch):
    original_index = ingestion_module._index_version

    def crash_after_index(*args, **kwargs):
        original_index(*args, **kwargs)
        raise RuntimeError("private crash detail and source content")

    monkeypatch.setattr(ingestion_module, "_index_version", crash_after_index)
    failed = client.post(
        "/api/v1/sources",
        json={
            "title": "Crash ADR",
            "uri": "file:///crash.md",
            "content": "Decision: This content must roll back atomically",
        },
    )
    assert failed.status_code == 500
    job_id = failed.headers["x-proofline-job-id"]
    job = session.get(IngestionJob, job_id)
    assert job.state == "failed"
    assert job.stage == "indexing"
    assert job.retryable is True
    assert job.attempts == 1
    assert job.error_detail == "ingestion failed during deterministic processing"
    assert session.scalar(select(func.count()).select_from(Source)) == 0
    assert session.scalar(select(func.count()).select_from(SourceVersion)) == 0
    assert session.scalar(select(func.count()).select_from(Chunk)) == 0
    assert session.scalar(select(func.count()).select_from(Decision)) == 0
    assert session.scalar(select(func.count()).select_from(Evidence)) == 0
    assert session.execute(text("SELECT count(*) FROM chunk_search")).scalar_one() == 0
    assert session.get(IngestionJobInput, job_id) is not None
    public_failed_job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert "content" not in public_failed_job
    assert "title" not in public_failed_job
    assert "uri" not in public_failed_job
    assert "idempotency_key" not in public_failed_job

    monkeypatch.setattr(ingestion_module, "_index_version", original_index)
    retried = client.post(f"/api/v1/jobs/{job_id}/retry")

    assert retried.status_code == 200
    assert retried.json()["state"] == "succeeded"
    assert retried.json()["stage"] == "ready"
    assert retried.json()["attempts"] == 2
    assert "content" not in retried.json()
    assert "idempotency_key" not in retried.json()
    assert session.scalar(select(func.count()).select_from(Source)) == 1
    assert session.scalar(select(func.count()).select_from(SourceVersion)) == 1
    assert session.get(IngestionJobInput, job_id) is None
    assert client.post(f"/api/v1/jobs/{job_id}/retry").status_code == 409


@pytest.mark.parametrize("fault_boundary", ["chunk_parse", "memory_extract"])
def test_ingestion_fault_matrix_rolls_back_before_and_after_chunk_index(
    client, session, monkeypatch, fault_boundary
):
    def fail(*_args, **_kwargs):
        raise RuntimeError("private staged fault content")

    monkeypatch.setattr(
        ingestion_module,
        "chunk_markdown" if fault_boundary == "chunk_parse" else "extract_memories",
        fail,
    )
    response = client.post(
        "/api/v1/sources",
        json={
            "title": f"Fault {fault_boundary}",
            "uri": f"fault:///{fault_boundary}.md",
            "content": "Decision: Roll back every partial provenance record",
        },
    )

    assert response.status_code == 500
    assert_failed_ingestion_has_no_partial_domain_state(
        session, response.headers["x-proofline-job-id"]
    )


def test_ingestion_fault_at_fts_write_rolls_back_chunk_and_source(session, monkeypatch):
    original_execute = session.execute

    def fail_fts(statement, *args, **kwargs):
        if "INSERT INTO chunk_search" in str(statement):
            raise RuntimeError("private FTS write fault")
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(session, "execute", fail_fts)
    with pytest.raises(IngestionExecutionError) as raised:
        run_ingestion_job(
            session,
            SourceCreate(
                title="FTS fault",
                uri="fault:///fts.md",
                content="Decision: FTS and chunks commit together",
            ),
        )

    monkeypatch.setattr(session, "execute", original_execute)
    assert_failed_ingestion_has_no_partial_domain_state(session, raised.value.job_id)


def test_ingestion_fault_at_terminal_commit_rolls_back_all_domain_writes(session, monkeypatch):
    original_commit = session.commit
    commit_count = 0

    def fail_terminal_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 3:
            raise OSError("private terminal commit fault")
        return original_commit()

    monkeypatch.setattr(session, "commit", fail_terminal_commit)
    with pytest.raises(IngestionExecutionError) as raised:
        run_ingestion_job(
            session,
            SourceCreate(
                title="Commit fault",
                uri="fault:///commit.md",
                content="Decision: Commit terminal state with its provenance",
            ),
        )

    monkeypatch.setattr(session, "commit", original_commit)
    assert commit_count == 4
    assert_failed_ingestion_has_no_partial_domain_state(session, raised.value.job_id)


def test_repeated_failure_dead_letters_and_purges_staged_input(client, session, monkeypatch):
    def always_fail(*_args, **_kwargs):
        raise RuntimeError("never expose this private failure")

    monkeypatch.setattr(ingestion_module, "ingest_source", always_fail)
    initial = client.post(
        "/api/v1/sources",
        json={"title": "Dead letter ADR", "content": "Decision: Retry safely"},
    )
    assert initial.status_code == 500
    job_id = initial.headers["x-proofline-job-id"]

    second = client.post(f"/api/v1/jobs/{job_id}/retry")
    third = client.post(f"/api/v1/jobs/{job_id}/retry")

    assert second.status_code == 500
    assert third.status_code == 500
    job = session.get(IngestionJob, job_id)
    session.refresh(job)
    assert job.state == "dead_letter"
    assert job.stage == "indexing"
    assert job.attempts == 3
    assert job.retryable is False
    assert job.finished_at is not None
    assert session.get(IngestionJobInput, job_id) is None
    assert session.scalar(select(func.count()).select_from(Source)) == 0
    assert client.post(f"/api/v1/jobs/{job_id}/retry").status_code == 409


def test_stale_second_retry_claim_cannot_increment_attempts_twice(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'claim.db'}")
    initialize_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    original_ingest = ingestion_module.ingest_source

    def fail_once(*_args, **_kwargs):
        raise RuntimeError("safe retry claim test")

    monkeypatch.setattr(ingestion_module, "ingest_source", fail_once)
    with factory() as session:
        with pytest.raises(IngestionExecutionError) as raised:
            run_ingestion_job(
                session,
                SourceCreate(title="Claim ADR", content="Decision: Claim once"),
            )
        job_id = raised.value.job_id

    monkeypatch.setattr(ingestion_module, "ingest_source", original_ingest)
    with factory() as stale_session:
        stale_job = stale_session.get(IngestionJob, job_id)
        assert stale_job.state == "failed"
        stale_session.commit()

        with factory() as winning_session:
            completed = retry_ingestion_job(winning_session, job_id)
            assert completed.state == "succeeded"
            assert completed.attempts == 2

        # expire_on_commit=False intentionally leaves this session with a stale claim view.
        assert stale_job.state == "failed"
        with pytest.raises(IngestionRetryConflict):
            retry_ingestion_job(stale_session, job_id)
        stale_session.rollback()

    with factory() as session:
        job = session.get(IngestionJob, job_id)
        assert job.attempts == 2
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 1
    engine.dispose()


def test_identity_conflict_is_permanent_safe_and_purges_input(client, session, monkeypatch):
    def conflict(*_args, **_kwargs):
        raise IngestionConflict("private source identity detail")

    monkeypatch.setattr(ingestion_module, "ingest_source", conflict)
    response = client.post(
        "/api/v1/sources",
        json={"title": "Conflict", "content": "private source identity detail"},
    )

    assert response.status_code == 409
    job_id = response.headers["x-proofline-job-id"]
    assert response.json()["detail"] == "source identity conflicts with existing records"
    job = session.get(IngestionJob, job_id)
    assert job.state == "dead_letter"
    assert job.stage == "indexing"
    assert job.retryable is False
    assert job.error_code == "source_identity_conflict"
    assert "private" not in job.error_detail
    assert session.get(IngestionJobInput, job_id) is None


def test_lifespan_recovers_orphan_running_jobs_without_exposing_input(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    initialize_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    content = "Decision: Recover interrupted work"
    with factory() as session:
        retryable = IngestionJob(
            state="running",
            stage="indexing",
            attempts=1,
            max_attempts=3,
            request_hash="a" * 64,
            retryable=False,
        )
        unrecoverable = IngestionJob(
            state="running",
            stage="accepted",
            attempts=1,
            max_attempts=1,
            retryable=False,
        )
        session.add_all([retryable, unrecoverable])
        session.flush()
        session.add(
            IngestionJobInput(
                job_id=retryable.id,
                title="Recoverable",
                kind="markdown",
                uri=None,
                content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )
        retryable_id = retryable.id
        unrecoverable_id = unrecoverable.id
        session.commit()

    with TestClient(create_app(engine)):
        pass

    with factory() as session:
        retryable = session.get(IngestionJob, retryable_id)
        unrecoverable = session.get(IngestionJob, unrecoverable_id)
        assert retryable.state == "failed"
        assert retryable.stage == "indexing"
        assert retryable.retryable is True
        assert retryable.error_code == "ingestion_interrupted"
        assert session.get(IngestionJobInput, retryable_id) is not None
        assert unrecoverable.state == "dead_letter"
        assert unrecoverable.stage == "accepted"
        assert unrecoverable.retryable is False
        assert unrecoverable.error_code == "ingestion_input_missing"
    engine.dispose()
