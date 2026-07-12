from proofline.database import initialize_database, make_engine
from proofline.migrations import MIGRATIONS, _initial_schema
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
    assert versions == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert {
        "sources",
        "source_versions",
        "chunks",
        "decisions",
        "evidence",
        "ingestion_jobs",
        "audit_events",
        "model_runs",
        "chunk_embeddings",
        "ingestion_job_inputs",
    } <= tables
    engine.dispose()


def test_v7_ingestion_jobs_migrate_without_becoming_retryable(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'v7.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        for version, description, migration in MIGRATIONS[:7]:
            migration(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, description) "
                    "VALUES (:version, :description)"
                ),
                {"version": version, "description": description},
            )
        connection.execute(
            text(
                """INSERT INTO ingestion_jobs
                   (id, source_id, source_version_id, kind, state, stage, attempts,
                    error_code, error_detail, retryable, created_at, updated_at)
                   VALUES ('legacy-job', NULL, NULL, 'source_ingestion', 'failed', 'failed', 1,
                           'ingestion_error', 'safe legacy failure', 1, :created, :updated)"""
            ),
            {
                "created": "2026-07-12T00:00:00+00:00",
                "updated": "2026-07-12T00:01:00+00:00",
            },
        )

    initialize_database(engine)

    with engine.connect() as connection:
        job = (
            connection.execute(text("SELECT * FROM ingestion_jobs WHERE id = 'legacy-job'"))
            .mappings()
            .one()
        )
        versions = (
            connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
            .scalars()
            .all()
        )
        staged_count = connection.execute(
            text("SELECT count(*) FROM ingestion_job_inputs")
        ).scalar_one()
    assert versions == list(range(1, 10))
    assert job["request_hash"] is None
    assert job["idempotency_key"] is None
    assert job["max_attempts"] == 1
    assert job["retryable"] == 0
    assert job["started_at"] == job["created_at"]
    assert job["finished_at"] == job["updated_at"]
    assert staged_count == 0
    engine.dispose()


def test_v8_decisions_are_backfilled_as_decision_kind(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'v8-memory.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        for version, description, migration in MIGRATIONS[:8]:
            migration(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, description) "
                    "VALUES (:version, :description)"
                ),
                {"version": version, "description": description},
            )
        connection.execute(
            text(
                """INSERT INTO sources
                   (id, title, kind, uri, content, content_hash, status, created_at, indexed_at,
                    current_version_id)
                   VALUES ('source-v8', 'Legacy ADR', 'markdown', 'file:///legacy.md',
                           'Decision: Keep compatibility', :identity, 'indexed', :now, :now,
                           'version-v8')"""
            ),
            {"identity": "a" * 64, "now": "2026-07-12T00:00:00+00:00"},
        )
        connection.execute(
            text(
                """INSERT INTO source_versions
                   (id, source_id, content_hash, content, version_number, content_length,
                    status, parser_version, created_at)
                   VALUES ('version-v8', 'source-v8', :content_hash,
                           'Decision: Keep compatibility', 1, 28, 'indexed',
                           'deterministic-v1', :now)"""
            ),
            {"content_hash": "b" * 64, "now": "2026-07-12T00:00:00+00:00"},
        )
        connection.execute(
            text(
                """INSERT INTO decisions
                   (id, source_id, source_version_id, title, statement, status, confidence,
                    extraction_method, created_at, updated_at)
                   VALUES ('decision-v8', 'source-v8', 'version-v8', 'Keep compatibility',
                           'Keep compatibility', 'active', 1.0, 'deterministic', :now, :now)"""
            ),
            {"now": "2026-07-12T00:00:00+00:00"},
        )

    initialize_database(engine)

    with engine.connect() as connection:
        memory = (
            connection.execute(text("SELECT id, kind FROM decisions WHERE id = 'decision-v8'"))
            .mappings()
            .one()
        )
        indexes = {row[1] for row in connection.exec_driver_sql("PRAGMA index_list(decisions)")}
    assert dict(memory) == {"id": "decision-v8", "kind": "decision"}
    assert "ix_decisions_kind" in indexes
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
        decision = (
            connection.execute(text("SELECT id, kind FROM decisions WHERE id = 'decision-1'"))
            .mappings()
            .one()
        )
        foreign_key_errors = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    assert source["id"] == "source-1"
    assert source["current_version_id"] == version["id"]
    assert version["version_number"] == 1
    assert evidence["source_version_id"] == version["id"]
    assert dict(decision) == {"id": "decision-1", "kind": "decision"}
    assert len(evidence["quote_hash"]) == 64
    assert foreign_key_errors == []
    engine.dispose()
