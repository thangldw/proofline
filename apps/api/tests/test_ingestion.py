from proofline.ingestion import chunk_markdown, extract_decisions, ingest_source
from proofline.models import Chunk, Decision, Evidence, Source
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
