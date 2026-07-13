import hashlib
from datetime import UTC, datetime

import pytest
from proofline.backup import create_sqlite_backup, verify_sqlite_backup
from proofline.database import initialize_database, make_engine
from proofline.ingestion import delete_source, source_deletion_impact
from proofline.migrations import MIGRATIONS, _initial_schema
from proofline.models import ImportReceipt, Source
from proofline.portability import build_portable_export, verify_portable_export
from proofline.retrieval import lexical_search
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


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
    assert versions == list(range(1, 21))
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
        "import_receipts",
        "git_repositories",
        "decision_relations",
        "chunk_vector_buckets",
        "workspaces",
        "workspace_leases",
        "study_cards",
        "study_reviews",
        "action_proposals",
        "proposal_citations",
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
        assert versions == list(range(1, 21))
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


def test_v9_model_runs_gain_repair_lineage_without_losing_metadata(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'v9-model-runs.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        for version, description, migration in MIGRATIONS[:9]:
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
                """INSERT INTO model_runs
                   (id, provider_id, model_id, operation, template_version, input_hashes,
                    status, validation_status, created_at)
                   VALUES ('legacy-run', 'fake', 'legacy-model', 'generate', 'legacy-v1',
                           '["hash"]', 'succeeded', 'valid', :now)"""
            ),
            {"now": "2026-07-12T00:00:00+00:00"},
        )

    initialize_database(engine)
    initialize_database(engine)

    with engine.connect() as connection:
        run = (
            connection.execute(
                text(
                    "SELECT id, parent_run_id, attempt_number, repair_reason "
                    "FROM model_runs WHERE id = 'legacy-run'"
                )
            )
            .mappings()
            .one()
        )
        indexes = {row[1] for row in connection.exec_driver_sql("PRAGMA index_list(model_runs)")}
        versions = (
            connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
            .scalars()
            .all()
        )
    assert dict(run) == {
        "id": "legacy-run",
        "parent_run_id": None,
        "attempt_number": 1,
        "repair_reason": None,
    }
    assert "ix_model_runs_parent_run_id" in indexes
    assert versions == list(range(1, 21))
    engine.dispose()


def test_v10_superseded_memories_normalize_to_obsolete(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'v10-memory-status.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        for version, description, migration in MIGRATIONS[:10]:
            migration(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, description) "
                    "VALUES (:version, :description)"
                ),
                {"version": version, "description": description},
            )
        now = "2026-07-12T00:00:00+00:00"
        connection.execute(
            text(
                """INSERT INTO sources
                   (id, title, kind, content, content_hash, status, created_at, indexed_at,
                    current_version_id)
                   VALUES ('source-v10', 'Legacy status ADR', 'markdown',
                           'Decision: Retire queue', :identity, 'indexed', :now, :now,
                           'version-v10')"""
            ),
            {"identity": "c" * 64, "now": now},
        )
        connection.execute(
            text(
                """INSERT INTO source_versions
                   (id, source_id, content_hash, content, version_number, content_length,
                    status, parser_version, created_at)
                   VALUES ('version-v10', 'source-v10', :content_hash,
                           'Decision: Retire queue', 1, 22, 'indexed',
                           'deterministic-v1', :now)"""
            ),
            {"content_hash": "d" * 64, "now": now},
        )
        connection.execute(
            text(
                """INSERT INTO decisions
                   (id, source_id, source_version_id, kind, title, statement, status, confidence,
                    extraction_method, created_at, updated_at)
                   VALUES ('memory-v10', 'source-v10', 'version-v10', 'decision', 'Retire queue',
                           'Retire queue', 'superseded', 1.0, 'deterministic', :now, :now)"""
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """INSERT INTO decisions
                   (id, source_id, source_version_id, kind, title, statement, status, confidence,
                    extraction_method, created_at, updated_at)
                   VALUES ('memory-v10-custom', 'source-v10', 'version-v10', 'decision',
                           'Review queue', 'Review queue', 'PENDING', 1.0,
                           'deterministic', :now, :now)"""
            ),
            {"now": now},
        )

    initialize_database(engine)
    initialize_database(engine)

    with engine.connect() as connection:
        statuses = dict(
            connection.execute(text("SELECT id, status FROM decisions ORDER BY id")).all()
        )
        versions = (
            connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
            .scalars()
            .all()
        )
    assert statuses == {"memory-v10": "obsolete", "memory-v10-custom": "candidate"}
    assert versions == list(range(1, 21))
    engine.dispose()


def test_v11_database_gains_persistent_unique_import_receipts(tmp_path):
    database_path = tmp_path / "v11-import-receipts.db"
    engine = make_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        for version, description, migration in MIGRATIONS[:11]:
            migration(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, description) "
                    "VALUES (:version, :description)"
                ),
                {"version": version, "description": description},
            )

    initialize_database(engine)
    export_created_at = datetime(2026, 7, 13, 1, 2, 3, tzinfo=UTC)
    with Session(engine) as session:
        receipt = ImportReceipt(
            schema="proofline-portable-export-v1",
            payload_sha256="a" * 64,
            export_app_version="0.1.0a2",
            export_created_at=export_created_at,
            counts_json={"sources": 2, "source_versions": 3},
        )
        session.add(receipt)
        session.commit()
        receipt_id = receipt.id
        assert receipt.imported_at is not None

    engine.dispose()
    reopened = make_engine(f"sqlite:///{database_path}")
    initialize_database(reopened)
    with Session(reopened) as session:
        receipt = session.scalar(select(ImportReceipt).where(ImportReceipt.id == receipt_id))
        assert receipt is not None
        assert receipt.schema == "proofline-portable-export-v1"
        assert receipt.payload_sha256 == "a" * 64
        assert receipt.export_app_version == "0.1.0a2"
        assert receipt.export_created_at == export_created_at.replace(tzinfo=None)
        assert receipt.counts_json == {"sources": 2, "source_versions": 3}

        session.add(
            ImportReceipt(
                schema="proofline-portable-export-v1",
                payload_sha256="a" * 64,
                export_app_version="0.1.0a2",
                export_created_at=export_created_at,
                counts_json={},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with reopened.connect() as connection:
        columns = {
            column["name"]: column for column in inspect(connection).get_columns("import_receipts")
        }
        versions = (
            connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
            .scalars()
            .all()
        )
        indexes = {
            row[1]: row[2]
            for row in connection.exec_driver_sql("PRAGMA index_list(import_receipts)")
        }
    assert set(columns) == {
        "id",
        "schema",
        "payload_sha256",
        "export_app_version",
        "export_created_at",
        "imported_at",
        "counts_json",
    }
    assert columns["imported_at"]["default"] == "CURRENT_TIMESTAMP"
    assert indexes["ix_import_receipts_payload_sha256"] == 1
    assert versions == list(range(1, 21))
    reopened.dispose()


def test_v16_backfills_vector_candidate_bands_for_existing_embeddings(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'vector-backfill.db'}")
    initialize_database(engine)
    now = "2026-07-14T00:00:00+00:00"
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM schema_migrations WHERE version = 16"))
        connection.exec_driver_sql("DROP TABLE chunk_vector_buckets")
        connection.execute(
            text(
                """INSERT INTO sources
               (id,title,kind,content,content_hash,status,created_at,indexed_at,current_version_id)
               VALUES ('s','S','text','x',:identity,'indexed',:now,:now,'v')"""
            ),
            {"identity": hashlib.sha256(b"source:s").hexdigest(), "now": now},
        )
        connection.execute(
            text(
                """INSERT INTO source_versions
               (id,source_id,content_hash,content,version_number,content_length,status,parser_version,created_at)
               VALUES ('v','s',:hash,'x',1,1,'indexed','test',:now)"""
            ),
            {"hash": hashlib.sha256(b"x").hexdigest(), "now": now},
        )
        connection.execute(
            text(
                """INSERT INTO chunks
               (id,source_id,source_version_id,ordinal,content,start_offset,end_offset,start_line,end_line)
               VALUES ('c','s','v',0,'x',0,1,1,1)"""
            )
        )
        connection.execute(
            text(
                """INSERT INTO chunk_embeddings
               (id,chunk_id,source_id,source_version_id,provider_id,model_id,dimensions,vector_json,content_hash,created_at)
               VALUES ('e','c','s','v','p','m',4,'[1,-1,1,-1]',:hash,:now)"""
            ),
            {"hash": hashlib.sha256(b"x").hexdigest(), "now": now},
        )
    initialize_database(engine)
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT embedding_id,band_index,band_value FROM chunk_vector_buckets")
        ).all()
    assert rows == [("e", 0, "1010")]
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


def test_large_foundation_fixture_migrates_with_exact_provenance_and_recovery(tmp_path):
    """Exercise every v1 provenance relationship at a non-trivial local fixture size."""
    source_count = 250
    database_path = tmp_path / "large-legacy.db"
    engine = make_engine(f"sqlite:///{database_path}")
    now = "2026-07-12T00:00:00+00:00"
    sources = []
    chunks = []
    decisions = []
    evidence = []
    fts_rows = []
    contents: dict[str, str] = {}
    for index in range(source_count):
        source_id = f"legacy-source-{index:04d}"
        content = (
            f"Decision: Keep component {index:04d} local.\n"
            f"Reason: migration sentinel legacytoken{index:04d}."
        )
        quote = f"Decision: Keep component {index:04d} local."
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        contents[source_id] = content
        sources.append(
            {
                "id": source_id,
                "title": f"Legacy ADR {index:04d}",
                "uri": f"file:///legacy/{index:04d}.md",
                "content": content,
                "content_hash": content_hash,
                "now": now,
            }
        )
        chunks.append(
            {
                "id": f"legacy-chunk-{index:04d}",
                "source_id": source_id,
                "content": content,
                "end_offset": len(content),
            }
        )
        decisions.append(
            {
                "id": f"legacy-decision-{index:04d}",
                "source_id": source_id,
                "title": f"Keep component {index:04d} local",
                "statement": f"Keep component {index:04d} local.",
                "now": now,
            }
        )
        evidence.append(
            {
                "id": f"legacy-evidence-{index:04d}",
                "decision_id": f"legacy-decision-{index:04d}",
                "source_id": source_id,
                "quote": quote,
                "end_offset": len(quote),
            }
        )
        fts_rows.append(
            {
                "chunk_id": f"legacy-chunk-{index:04d}",
                "source_id": source_id,
                "content": content,
            }
        )

    with engine.begin() as connection:
        _initial_schema(connection)
        connection.execute(
            text(
                """INSERT INTO sources
                   (id, title, kind, uri, content, content_hash, status, created_at, indexed_at)
                   VALUES (:id, :title, 'markdown', :uri, :content, :content_hash,
                           'indexed', :now, :now)"""
            ),
            sources,
        )
        connection.execute(
            text(
                """INSERT INTO chunks
                   (id, source_id, ordinal, content, start_offset, end_offset,
                    start_line, end_line)
                   VALUES (:id, :source_id, 0, :content, 0, :end_offset, 1, 2)"""
            ),
            chunks,
        )
        connection.execute(
            text(
                """INSERT INTO decisions
                   (id, source_id, title, statement, rationale, status, confidence,
                    extraction_method, valid_from, valid_to, created_at)
                   VALUES (:id, :source_id, :title, :statement, NULL, 'active', 1.0,
                           'deterministic', NULL, NULL, :now)"""
            ),
            decisions,
        )
        connection.execute(
            text(
                """INSERT INTO evidence
                   (id, decision_id, source_id, quote, start_offset, end_offset,
                    start_line, end_line)
                   VALUES (:id, :decision_id, :source_id, :quote, 0, :end_offset, 1, 1)"""
            ),
            evidence,
        )
        connection.execute(
            text(
                """INSERT INTO chunk_search(chunk_id, source_id, content)
                   VALUES (:chunk_id, :source_id, :content)"""
            ),
            fts_rows,
        )

    initialize_database(engine)
    initialize_database(engine)

    with Session(engine) as session:
        counts = {
            table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in ("sources", "source_versions", "chunks", "decisions", "evidence")
        }
        assert counts == {table: source_count for table in counts}
        for index in (0, source_count // 2, source_count - 1):
            source_id = f"legacy-source-{index:04d}"
            row = (
                session.execute(
                    text(
                        """SELECT s.id, s.content_hash AS identity_hash, s.current_version_id,
                                  v.content_hash, v.content, c.source_version_id AS chunk_version,
                                  d.source_version_id AS memory_version, d.kind,
                                  e.source_version_id AS evidence_version, e.quote, e.quote_hash,
                                  e.start_offset, e.end_offset
                           FROM sources s
                           JOIN source_versions v ON v.id = s.current_version_id
                           JOIN chunks c ON c.source_id = s.id
                           JOIN decisions d ON d.source_id = s.id
                           JOIN evidence e ON e.decision_id = d.id
                           WHERE s.id = :source_id"""
                    ),
                    {"source_id": source_id},
                )
                .mappings()
                .one()
            )
            content = contents[source_id]
            assert (
                row["identity_hash"] == hashlib.sha256(f"source:{source_id}".encode()).hexdigest()
            )
            assert row["content_hash"] == hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert row["content"] == content
            assert row["chunk_version"] == row["current_version_id"]
            assert row["memory_version"] == row["current_version_id"]
            assert row["evidence_version"] == row["current_version_id"]
            assert row["kind"] == "decision"
            assert content[row["start_offset"] : row["end_offset"]] == row["quote"]
            assert row["quote_hash"] == hashlib.sha256(row["quote"].encode("utf-8")).hexdigest()

        hits = lexical_search(session, "legacytoken0249", limit=5)
        assert [hit.source_id for hit in hits] == ["legacy-source-0249"]
        export = build_portable_export(session)
        assert verify_portable_export(export)["sources"] == source_count

        deleted = session.get(Source, "legacy-source-0000")
        assert deleted is not None
        impact = source_deletion_impact(session, deleted)
        impact_counts = (
            impact.versions,
            impact.chunks,
            impact.memories,
            impact.evidence,
            impact.fts_rows,
        )
        assert impact_counts == (
            1,
            1,
            1,
            1,
            1,
        )
        delete_source(session, deleted)

    backup_path = tmp_path / "large-legacy-backup.db"
    backup_report = create_sqlite_backup(engine, backup_path)
    assert verify_sqlite_backup(backup_path) == backup_report
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(text("SELECT count(*) FROM sources")).scalar_one() == 249
        assert (
            connection.execute(
                text("SELECT count(*) FROM chunk_search WHERE source_id = 'legacy-source-0000'")
            ).scalar_one()
            == 0
        )
    engine.dispose()
