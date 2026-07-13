import json

import pytest
from proofline import cli
from proofline.embeddings import index_current_embeddings
from proofline.ingestion import ingest_source
from proofline.integrity import IntegrityVerificationError, verify_live_database
from proofline.model_gateway import FakeEmbeddingProvider
from proofline.schemas import SourceCreate
from sqlalchemy import text


def seeded(session):
    source, _created = ingest_source(
        session,
        SourceCreate(
            title="Integrity ADR",
            uri="file:///integrity.md",
            content="# Queue\n\nDecision: Use NATS.\nReason: It is operationally small.",
        ),
    )
    return source


def second_source(session):
    source, _created = ingest_source(
        session,
        SourceCreate(
            title="Second ADR",
            uri="file:///second.md",
            content="Decision: Keep the second source separate.",
        ),
    )
    return source


def test_live_integrity_verifier_accepts_clean_provenance(session):
    seeded(session)

    report = verify_live_database(session.get_bind())

    assert report == {
        "valid": True,
        "sources": 1,
        "source_versions": 1,
        "chunks": 1,
        "memories": 1,
        "evidence": 1,
        "embeddings": 0,
        "vector_index_rows": 0,
    }


def test_live_integrity_verifier_accepts_owned_embedding(session):
    source = seeded(session)
    provider = FakeEmbeddingProvider({source.chunks[0].content: [0.25, 0.75]})
    index_current_embeddings(session, provider)

    report = verify_live_database(session.get_bind())

    assert report["valid"] is True
    assert report["embeddings"] == 1
    assert report["vector_index_rows"] == 1


@pytest.mark.parametrize(
    ("corruption", "expected_code"),
    [
        ("source_identity", "source_identity_hash_mismatch"),
        ("version_hash", "source_version_hash_mismatch"),
        ("chunk_content", "chunk_content_mismatch"),
        ("evidence_hash", "evidence_quote_hash_mismatch"),
        ("fts_content", "fts_content_mismatch"),
    ],
)
def test_live_integrity_verifier_fails_closed_with_safe_codes(session, corruption, expected_code):
    seeded(session)
    statements = {
        "source_identity": "UPDATE sources SET content_hash = 'invalid'",
        "version_hash": "UPDATE source_versions SET content_hash = 'invalid'",
        "chunk_content": "UPDATE chunks SET content = 'PRIVATE CORRUPTED CONTENT'",
        "evidence_hash": "UPDATE evidence SET quote_hash = 'invalid'",
        "fts_content": "UPDATE chunk_search SET content = 'PRIVATE CORRUPTED CONTENT'",
    }
    session.execute(text(statements[corruption]))
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == expected_code
    assert "PRIVATE" not in str(raised.value)


@pytest.mark.parametrize(
    ("statement", "expected_code"),
    [
        (
            "UPDATE source_versions SET content_length = content_length + 1",
            "source_version_length_mismatch",
        ),
        ("UPDATE source_versions SET version_number = 2", "source_version_sequence_invalid"),
        ("UPDATE sources SET content = content || ' drift'", "source_current_content_mismatch"),
        (
            "UPDATE sources SET current_version_id = '00000000-0000-0000-0000-000000000000'",
            "source_current_version_invalid",
        ),
        ("UPDATE chunks SET end_offset = 999999", "chunk_span_invalid"),
        ("UPDATE chunks SET start_line = start_line + 1", "chunk_span_invalid"),
        ("UPDATE chunks SET ordinal = 2", "chunk_ordinal_sequence_invalid"),
        (
            "UPDATE decisions SET extraction_method = 'model', model_run_id = NULL",
            "memory_model_run_missing",
        ),
        ("UPDATE evidence SET quote = 'PRIVATE CORRUPTED QUOTE'", "evidence_quote_mismatch"),
        ("UPDATE evidence SET end_offset = 999999", "evidence_span_invalid"),
        ("DELETE FROM chunk_search", "fts_row_set_mismatch"),
    ],
)
def test_live_integrity_verifier_detects_semantic_corruption(session, statement, expected_code):
    seeded(session)
    session.execute(text(statement))
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == expected_code
    assert "PRIVATE" not in str(raised.value)


@pytest.mark.parametrize(
    ("table", "expected_code"),
    [
        ("chunks", "chunk_ownership_invalid"),
        ("decisions", "memory_ownership_invalid"),
        ("evidence", "evidence_memory_ownership_invalid"),
    ],
)
def test_live_integrity_verifier_detects_cross_source_ownership(session, table, expected_code):
    seeded(session)
    other = second_source(session)
    session.execute(text(f"UPDATE {table} SET source_id = :source_id"), {"source_id": other.id})
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("statement", "expected_code"),
    [
        ("UPDATE chunk_embeddings SET content_hash = 'invalid'", "embedding_content_hash_mismatch"),
        ("UPDATE chunk_embeddings SET vector_json = '[]'", "embedding_vector_invalid"),
        ("UPDATE chunk_embeddings SET dimensions = dimensions + 1", "embedding_vector_invalid"),
    ],
)
def test_live_integrity_verifier_detects_embedding_corruption(session, statement, expected_code):
    source = seeded(session)
    provider = FakeEmbeddingProvider({source.chunks[0].content: [0.25, 0.75]})
    index_current_embeddings(session, provider)
    session.execute(text(statement))
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == expected_code


def test_live_integrity_verifier_detects_foreign_key_corruption(session):
    seeded(session)
    session.commit()
    raw = session.get_bind().raw_connection()
    try:
        raw.execute("PRAGMA foreign_keys = OFF")
        raw.execute("UPDATE evidence SET decision_id = '00000000-0000-0000-0000-000000000000'")
        raw.commit()
    finally:
        raw.close()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == "foreign_key_check_failed"


def test_live_integrity_verifier_requires_evidence_for_every_memory(session):
    seeded(session)
    session.execute(text("DELETE FROM evidence"))
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == "memory_evidence_missing"


def test_live_integrity_verifier_rejects_coordinated_cross_source_evidence(session):
    first = seeded(session)
    other = second_source(session)
    evidence = first.decisions[0].evidence[0]
    other_evidence = other.decisions[0].evidence[0]
    evidence.source_id = other_evidence.source_id
    evidence.source_version_id = other_evidence.source_version_id
    evidence.quote = other_evidence.quote
    evidence.quote_hash = other_evidence.quote_hash
    evidence.start_offset = other_evidence.start_offset
    evidence.end_offset = other_evidence.end_offset
    evidence.start_line = other_evidence.start_line
    evidence.end_line = other_evidence.end_line
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == "evidence_memory_ownership_invalid"


def test_live_integrity_verifier_normalizes_malformed_sqlite_types(session):
    seeded(session)
    session.execute(text("UPDATE source_versions SET content = X'FF'"))
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == "database_validation_failed"
    assert "PRIVATE" not in str(raised.value)


def test_live_integrity_verifier_rejects_model_run_cycles(session):
    source = seeded(session)
    provider = FakeEmbeddingProvider({source.chunks[0].content: [0.25, 0.75]})
    index_current_embeddings(session, provider)
    session.execute(text("UPDATE model_runs SET parent_run_id = id"))
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == "model_run_lineage_invalid"


def test_live_integrity_verifier_requires_complete_migration_history(session):
    seeded(session)
    session.execute(
        text(
            "DELETE FROM schema_migrations "
            "WHERE version = (SELECT max(version) FROM schema_migrations)"
        )
    )
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == "migration_version_mismatch"


def test_live_integrity_verifier_requires_latest_version_to_be_current(session):
    source = seeded(session)
    old_version_id = source.current_version_id
    ingest_source(
        session,
        SourceCreate(
            title=source.title,
            uri=source.uri,
            content="# Queue\n\nDecision: Use JetStream.\nReason: Requirements changed.",
        ),
    )
    session.execute(
        text(
            "UPDATE sources SET current_version_id = :version_id, "
            "content = (SELECT content FROM source_versions WHERE id = :version_id) "
            "WHERE id = :source_id"
        ),
        {"version_id": old_version_id, "source_id": source.id},
    )
    session.commit()

    with pytest.raises(IntegrityVerificationError) as raised:
        verify_live_database(session.get_bind())

    assert raised.value.code == "source_current_version_not_latest"


def test_verify_integrity_cli_emits_metadata_only_report(session, monkeypatch, capsys):
    seeded(session)
    monkeypatch.setattr(cli, "engine", session.get_bind())

    cli.main(["verify-integrity"])

    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert report["sources"] == 1
    assert "Integrity ADR" not in json.dumps(report)
