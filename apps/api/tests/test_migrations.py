from proofline.database import initialize_database, make_engine
from proofline.migrations import _initial_schema
from sqlalchemy import inspect, text


def test_migrations_are_idempotent_and_recorded(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'migrations.db'}")

    initialize_database(engine)
    initialize_database(engine)

    with engine.connect() as connection:
        versions = (
            connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
            .scalars()
            .all()
        )
        tables = set(inspect(connection).get_table_names())
    assert versions == [1, 2, 3, 4, 5]
    assert {
        "sources",
        "source_versions",
        "chunks",
        "decisions",
        "evidence",
        "ingestion_jobs",
        "audit_events",
        "model_runs",
    } <= tables
    engine.dispose()


def test_populated_foundation_database_is_backfilled_without_changing_ids(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        _initial_schema(connection)
        connection.execute(
            text(
                """INSERT INTO sources
                   (id, title, kind, uri, content, content_hash, status, created_at, indexed_at)
                   VALUES ('source-1', 'ADR', 'markdown', 'file:///adr.md',
                           'Decision: Use SQLite', :digest, 'indexed', :now, :now)"""
            ),
            {
                "digest": "5f7614bc2ea64fba28f97f208a3c99a554946e722037c65cbddac74cd759f4f3",
                "now": "2026-07-12T00:00:00+00:00",
            },
        )
        connection.execute(
            text(
                """INSERT INTO chunks
                   (id, source_id, ordinal, content, start_offset, end_offset,
                    start_line, end_line)
                   VALUES ('chunk-1', 'source-1', 0, 'Decision: Use SQLite', 0, 20, 1, 1)"""
            )
        )
        connection.execute(
            text(
                """INSERT INTO decisions
                   (id, source_id, title, statement, rationale, status, confidence,
                    extraction_method, valid_from, valid_to, created_at)
                   VALUES ('decision-1', 'source-1', 'Use SQLite', 'Use SQLite', NULL,
                           'active', 1.0, 'deterministic', NULL, NULL, :now)"""
            ),
            {"now": "2026-07-12T00:00:00+00:00"},
        )
        connection.execute(
            text(
                """INSERT INTO evidence
                   (id, decision_id, source_id, quote, start_offset, end_offset,
                    start_line, end_line)
                   VALUES ('evidence-1', 'decision-1', 'source-1',
                           'Decision: Use SQLite', 0, 20, 1, 1)"""
            )
        )
        connection.execute(
            text(
                """INSERT INTO chunk_search(chunk_id, source_id, content)
                   VALUES ('chunk-1', 'source-1', 'Decision: Use SQLite')"""
            )
        )

    initialize_database(engine)

    with engine.connect() as connection:
        source = (
            connection.execute(
                text("SELECT id, current_version_id FROM sources WHERE id = 'source-1'")
            )
            .mappings()
            .one()
        )
        version = (
            connection.execute(text("SELECT * FROM source_versions WHERE source_id = 'source-1'"))
            .mappings()
            .one()
        )
        evidence = (
            connection.execute(text("SELECT * FROM evidence WHERE id = 'evidence-1'"))
            .mappings()
            .one()
        )
        foreign_key_errors = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    assert source["id"] == "source-1"
    assert source["current_version_id"] == version["id"]
    assert version["version_number"] == 1
    assert evidence["source_version_id"] == version["id"]
    assert len(evidence["quote_hash"]) == 64
    assert foreign_key_errors == []
    engine.dispose()
