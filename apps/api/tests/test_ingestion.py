import proofline.ingestion as ingestion_module
import pytest
from proofline.ingestion import (
    IngestionExecutionError,
    chunk_markdown,
    extract_decisions,
    ingest_source,
    run_ingestion_job,
)
from proofline.models import Chunk, Decision, Evidence, IngestionJob, Source, SourceVersion
from proofline.schemas import SourceCreate
from sqlalchemy import func, select


def test_chunks_preserve_exact_unicode_spans():
    content = "# Kiến trúc 🧠\n\nĐây là quyết định tiếng Việt.\n\n中文の段落です。"
    spans = chunk_markdown(content)
    assert spans
    assert all(content[span.start_offset : span.end_offset] == span.text for span in spans)
    assert "中文の段落です。" in spans[-1].text
    assert spans[-1].end_line == 5


def test_extracts_decision_and_exact_evidence():
    content = (
        "# ADR\n\n## Quyết định: Dùng SQLite cho MVP\n"
        "Lý do: triển khai local đơn giản.\nTrạng thái: active\n"
    )
    results = extract_decisions(content)
    assert len(results) == 1
    result = results[0]
    assert result["statement"] == "Dùng SQLite cho MVP"
    assert result["rationale"] == "triển khai local đơn giản."
    assert content[result["start_offset"] : result["end_offset"]] == result["quote"]
    assert result["end_line"] == 5


def test_ingestion_is_idempotent(session):
    payload = SourceCreate(title="ADR", content="Decision: Use SQLite\nReason: simple local setup")
    first, first_created = ingest_source(session, payload)
    second, second_created = ingest_source(session, payload)
    assert first_created is True
    assert second_created is False
    assert first.id == second.id
    assert session.scalar(select(func.count()).select_from(Source)) == 1
    assert session.scalar(select(func.count()).select_from(Decision)) == 1
    assert session.scalar(select(func.count()).select_from(Evidence)) == 1
    assert session.scalar(select(func.count()).select_from(Chunk)) == 1
    assert session.scalar(select(func.count()).select_from(SourceVersion)) == 1


def test_same_uri_creates_immutable_version_and_keeps_historical_evidence(session):
    first_content = "Decision: Use SQLite\nReason: simple local setup"
    second_content = "Decision: Use Postgres\nReason: shared hosted workload"
    first, first_created = ingest_source(
        session,
        SourceCreate(title="ADR", uri="file:///adr.md", content=first_content),
    )
    first_version = first.current_version_id
    first_decision = session.scalar(
        select(Decision).where(Decision.source_version_id == first_version)
    )

    second, second_created = ingest_source(
        session,
        SourceCreate(title="ADR updated", uri="file:///adr.md", content=second_content),
    )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.current_version_id != first_version
    assert session.scalar(select(func.count()).select_from(SourceVersion)) == 2
    assert session.get(Decision, first_decision.id).statement == "Use SQLite"
    evidence = session.scalar(select(Evidence).where(Evidence.decision_id == first_decision.id))
    assert first_content[evidence.start_offset : evidence.end_offset] == evidence.quote


def test_ingestion_failure_is_persisted_without_source_content(session, monkeypatch):
    def fail_ingestion(*_args, **_kwargs):
        raise RuntimeError("private source text must not be persisted in the job")

    monkeypatch.setattr(ingestion_module, "ingest_source", fail_ingestion)
    with pytest.raises(IngestionExecutionError) as raised:
        run_ingestion_job(
            session,
            SourceCreate(title="Sensitive", content="private source text"),
        )

    job = session.get(IngestionJob, raised.value.job_id)
    assert job.state == "failed"
    assert job.error_code == "ingestion_error"
    assert job.retryable is False
    assert "private source text" not in job.error_detail
    assert session.scalar(select(func.count()).select_from(Source)) == 0
