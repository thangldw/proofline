import hashlib

import proofline.ingestion as ingestion_module
import pytest
from proofline.ingestion import (
    IngestionExecutionError,
    chunk_markdown,
    extract_decisions,
    extract_memories,
    ingest_source,
    run_ingestion_job,
)
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
from sqlalchemy import func, select


def test_chunks_preserve_exact_unicode_spans():
    content = "# Kiến trúc 🧠\n\nĐây là quyết định tiếng Việt.\n\n中文の段落です。"
    spans = chunk_markdown(content)
    assert spans
    assert all(content[span.start_offset : span.end_offset] == span.text for span in spans)
    assert "中文の段落です。" in spans[-1].text
    assert spans[-1].end_line == 5


def test_single_large_paragraph_is_split_without_content_loss():
    content = "x" * (5 * 1024 * 1024)

    spans = chunk_markdown(content)

    assert len(spans) > 3_000
    assert all(0 < len(span.text) <= 1_600 for span in spans)
    assert "".join(span.text for span in spans) == content
    assert spans[0].start_offset == 0
    assert spans[-1].end_offset == len(content)


def test_new_source_versions_record_bounded_parser_version(session):
    source, _ = ingest_source(
        session,
        SourceCreate(title="Parser version", content="Decision: Bound every chunk"),
    )

    assert source.versions[0].parser_version == "deterministic-v2"


def test_overlong_unicode_paragraph_preserves_codepoint_spans_and_lines():
    unit = "中文🧠e\u0301"
    content = unit * 700

    spans = chunk_markdown(content)

    assert len(spans) > 1
    assert all(len(span.text) <= 1_600 for span in spans)
    assert "".join(span.text for span in spans) == content
    assert all(content[span.start_offset : span.end_offset] == span.text for span in spans)
    assert all(span.start_line == span.end_line == 1 for span in spans)


def test_crlf_and_combining_characters_keep_exact_offsets_and_lines():
    content = (
        "# Cafe\u0301 architecture\r\n\r\n"
        "Decision: Preserve code-point offsets 🧠\r\n"
        "Reason: citations must survive CRLF.\r\n"
    )

    spans = chunk_markdown(content)
    decisions = extract_decisions(content)

    assert spans
    assert all(content[item.start_offset : item.end_offset] == item.text for item in spans)
    assert len(decisions) == 1
    decision = decisions[0]
    assert content[decision["start_offset"] : decision["end_offset"]] == decision["quote"]
    assert decision["start_line"] == 3
    assert decision["end_line"] == 4


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


def test_extracts_generalized_memory_kinds_with_exact_evidence(session):
    content = (
        "Decision: Use SQLite for local state\nReason: no external service.\n\n"
        "Assumption: A single writer owns the database.\n\n"
        "## Ràng buộc: Dữ liệu không được rời máy\n\n"
        "Phương án: Use Postgres for a future team deployment."
    )

    extracted = extract_memories(content)

    assert [item["kind"] for item in extracted] == [
        "decision",
        "assumption",
        "constraint",
        "alternative",
    ]
    assert [item["kind"] for item in extract_decisions(content)] == ["decision"]
    assert all(
        content[item["start_offset"] : item["end_offset"]] == item["quote"] for item in extracted
    )
    source, _created = ingest_source(
        session,
        SourceCreate(title="Generalized ADR", content=content),
    )
    memories = list(
        session.scalars(
            select(Decision)
            .where(Decision.source_version_id == source.current_version_id)
            .order_by(Decision.created_at)
        ).all()
    )
    assert {memory.kind for memory in memories} == {
        "decision",
        "assumption",
        "constraint",
        "alternative",
    }
    for memory in memories:
        assert memory.status == "active"
        assert len(memory.evidence) == 1
        evidence = memory.evidence[0]
        assert content[evidence.start_offset : evidence.end_offset] == evidence.quote


def test_memory_heading_accepts_markdown_spacing_before_metadata(session):
    content = (
        "## Alternative: Run Kafka\n\n"
        "Rationale: It remains viable for hosted scale.\n"
        "Status: rejected\n\n"
        "Unrelated paragraph."
    )
    source, _ = ingest_source(
        session,
        SourceCreate(title="Spaced ADR", content=content),
    )

    memory = source.decisions[0]
    evidence = memory.evidence[0]
    assert memory.kind == "alternative"
    assert memory.rationale == "It remains viable for hosted scale."
    assert memory.status == "rejected"
    assert evidence.quote.endswith("Status: rejected")
    assert "Unrelated paragraph" not in evidence.quote
    assert content[evidence.start_offset : evidence.end_offset] == evidence.quote


def test_superseded_source_status_normalizes_to_reviewable_obsolete():
    for source_status in ("superseded", "replaced", "obsolete"):
        [memory] = extract_memories(f"Decision: Retire the old queue\nStatus: {source_status}")
        assert memory["status"] == "obsolete"


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
    assert evidence.quote_hash == hashlib.sha256(evidence.quote.encode("utf-8")).hexdigest()


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
    assert job.stage == "indexing"
    assert job.error_code == "ingestion_error"
    assert job.retryable is True
    assert job.attempts == 1
    assert job.max_attempts == 3
    assert job.started_at is not None
    assert job.finished_at is not None
    assert "private source text" not in job.error_detail
    assert session.get(IngestionJobInput, job.id).content == "private source text"
    assert session.scalar(select(func.count()).select_from(Source)) == 0
