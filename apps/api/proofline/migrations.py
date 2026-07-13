from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable

from sqlalchemy import Connection, Engine, inspect, text

Migration = tuple[int, str, Callable[[Connection], None]]


def _initial_schema(connection: Connection) -> None:
    """Create the foundation schema without changing existing pre-alpha tables."""
    statements = (
        """CREATE TABLE IF NOT EXISTS sources (
            id VARCHAR(36) PRIMARY KEY,
            title VARCHAR(300) NOT NULL,
            kind VARCHAR(30) NOT NULL,
            uri TEXT,
            content TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(30) NOT NULL,
            created_at DATETIME NOT NULL,
            indexed_at DATETIME NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS ix_sources_content_hash ON sources (content_hash)",
        """CREATE TABLE IF NOT EXISTS chunks (
            id VARCHAR(36) PRIMARY KEY,
            source_id VARCHAR(36) NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            content TEXT NOT NULL,
            start_offset INTEGER NOT NULL,
            end_offset INTEGER NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS ix_chunks_source_id ON chunks (source_id)",
        """CREATE TABLE IF NOT EXISTS decisions (
            id VARCHAR(36) PRIMARY KEY,
            source_id VARCHAR(36) NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            title VARCHAR(300) NOT NULL,
            statement TEXT NOT NULL,
            rationale TEXT,
            status VARCHAR(30) NOT NULL,
            confidence FLOAT NOT NULL,
            extraction_method VARCHAR(40) NOT NULL,
            valid_from DATETIME,
            valid_to DATETIME,
            created_at DATETIME NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS ix_decisions_source_id ON decisions (source_id)",
        """CREATE TABLE IF NOT EXISTS evidence (
            id VARCHAR(36) PRIMARY KEY,
            decision_id VARCHAR(36) NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
            source_id VARCHAR(36) NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            quote TEXT NOT NULL,
            start_offset INTEGER NOT NULL,
            end_offset INTEGER NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS ix_evidence_decision_id ON evidence (decision_id)",
        "CREATE INDEX IF NOT EXISTS ix_evidence_source_id ON evidence (source_id)",
        """CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search USING fts5(
            chunk_id UNINDEXED,
            source_id UNINDEXED,
            content,
            tokenize = 'unicode61'
        )""",
    )
    for statement in statements:
        connection.exec_driver_sql(statement)


def _add_source_versions(connection: Connection) -> None:
    connection.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS source_versions (
            id VARCHAR(36) PRIMARY KEY,
            source_id VARCHAR(36) NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            content_hash VARCHAR(64) NOT NULL,
            content TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            content_length INTEGER NOT NULL,
            status VARCHAR(30) NOT NULL,
            parser_version VARCHAR(30) NOT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE(source_id, content_hash),
            UNIQUE(source_id, version_number)
        )"""
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_source_versions_source_id ON source_versions (source_id)"
    )

    columns = {
        table: {column["name"] for column in inspect(connection).get_columns(table)}
        for table in ("sources", "chunks", "decisions", "evidence")
    }
    if "current_version_id" not in columns["sources"]:
        connection.exec_driver_sql("ALTER TABLE sources ADD COLUMN current_version_id VARCHAR(36)")
    for table in ("chunks", "decisions", "evidence"):
        if "source_version_id" not in columns[table]:
            connection.exec_driver_sql(
                f"ALTER TABLE {table} ADD COLUMN source_version_id VARCHAR(36)"
            )
    if "quote_hash" not in columns["evidence"]:
        connection.exec_driver_sql("ALTER TABLE evidence ADD COLUMN quote_hash VARCHAR(64)")

    sources = connection.execute(
        text(
            "SELECT id, content_hash, content, status, indexed_at, current_version_id FROM sources"
        )
    ).mappings()
    for source in sources:
        version_id = source["current_version_id"]
        if not version_id:
            version_id = str(uuid.uuid4())
            connection.execute(
                text(
                    """INSERT INTO source_versions
                       (id, source_id, content_hash, content, version_number,
                        content_length, status, parser_version, created_at)
                       VALUES (:id, :source_id, :content_hash, :content, :version_number,
                               :content_length, :status, 'foundation-v1', :created_at)"""
                ),
                {
                    "id": version_id,
                    "source_id": source["id"],
                    "content_hash": source["content_hash"],
                    "content": source["content"],
                    "version_number": 1,
                    "content_length": len(source["content"]),
                    "status": source["status"],
                    "created_at": source["indexed_at"],
                },
            )
            connection.execute(
                text(
                    """UPDATE sources
                       SET current_version_id = :version, content_hash = :identity_hash
                       WHERE id = :source"""
                ),
                {
                    "version": version_id,
                    "identity_hash": hashlib.sha256(f"source:{source['id']}".encode()).hexdigest(),
                    "source": source["id"],
                },
            )
        for table in ("chunks", "decisions", "evidence"):
            connection.execute(
                text(
                    f"""UPDATE {table} SET source_version_id = :version
                        WHERE source_id = :source AND source_version_id IS NULL"""
                ),
                {"version": version_id, "source": source["id"]},
            )
        evidence_rows = list(
            connection.execute(
                text("SELECT id, quote FROM evidence WHERE source_id = :source"),
                {"source": source["id"]},
            ).mappings()
        )
        if evidence_rows:
            connection.execute(
                text(
                    """UPDATE evidence SET quote_hash = :quote_hash
                       WHERE source_id = :source AND source_version_id = :version
                         AND id = :evidence"""
                ),
                [
                    {
                        "quote_hash": hashlib.sha256(row["quote"].encode("utf-8")).hexdigest(),
                        "source": source["id"],
                        "version": version_id,
                        "evidence": row["id"],
                    }
                    for row in evidence_rows
                ],
            )

    for table in ("chunks", "decisions", "evidence"):
        connection.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_source_version_id "
            f"ON {table} (source_version_id)"
        )


def _add_ingestion_jobs(connection: Connection) -> None:
    connection.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS ingestion_jobs (
            id VARCHAR(36) PRIMARY KEY,
            source_id VARCHAR(36) REFERENCES sources(id) ON DELETE SET NULL,
            source_version_id VARCHAR(36),
            kind VARCHAR(30) NOT NULL,
            state VARCHAR(30) NOT NULL,
            stage VARCHAR(30) NOT NULL,
            attempts INTEGER NOT NULL,
            error_code VARCHAR(80),
            error_detail VARCHAR(500),
            retryable BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )"""
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_source_id ON ingestion_jobs (source_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_state ON ingestion_jobs (state, updated_at)"
    )


def _add_memory_audit(connection: Connection) -> None:
    decision_columns = {column["name"] for column in inspect(connection).get_columns("decisions")}
    if "updated_at" not in decision_columns:
        connection.exec_driver_sql("ALTER TABLE decisions ADD COLUMN updated_at DATETIME")
        connection.exec_driver_sql("UPDATE decisions SET updated_at = created_at")
    connection.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS audit_events (
            id VARCHAR(36) PRIMARY KEY,
            actor VARCHAR(100) NOT NULL,
            action VARCHAR(80) NOT NULL,
            object_type VARCHAR(50) NOT NULL,
            object_id VARCHAR(36) NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            created_at DATETIME NOT NULL
        )"""
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_audit_events_object "
        "ON audit_events (object_type, object_id, created_at)"
    )


def _add_model_runs(connection: Connection) -> None:
    connection.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS model_runs (
            id VARCHAR(36) PRIMARY KEY,
            provider_id VARCHAR(100) NOT NULL,
            model_id VARCHAR(200) NOT NULL,
            operation VARCHAR(50) NOT NULL,
            template_version VARCHAR(80) NOT NULL,
            input_hashes TEXT NOT NULL,
            status VARCHAR(30) NOT NULL,
            validation_status VARCHAR(30),
            latency_ms INTEGER,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            error_code VARCHAR(80),
            created_at DATETIME NOT NULL,
            finished_at DATETIME
        )"""
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_model_runs_status ON model_runs (status, created_at)"
    )


def _add_chunk_embeddings(connection: Connection) -> None:
    connection.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS chunk_embeddings (
            id VARCHAR(36) PRIMARY KEY,
            chunk_id VARCHAR(36) NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            source_id VARCHAR(36) NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            source_version_id VARCHAR(36) NOT NULL REFERENCES source_versions(id) ON DELETE CASCADE,
            provider_id VARCHAR(100) NOT NULL,
            model_id VARCHAR(200) NOT NULL,
            dimensions INTEGER NOT NULL,
            vector_json TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE(chunk_id, provider_id, model_id)
        )"""
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_version "
        "ON chunk_embeddings (source_version_id, provider_id, model_id)"
    )


def _link_decisions_to_model_runs(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("decisions")}
    if "model_run_id" not in columns:
        connection.exec_driver_sql("ALTER TABLE decisions ADD COLUMN model_run_id VARCHAR(36)")
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_decisions_model_run_id ON decisions (model_run_id)"
    )


def _add_resumable_ingestion_jobs(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("ingestion_jobs")}
    additions = {
        "request_hash": "VARCHAR(64)",
        "idempotency_key": "VARCHAR(200)",
        "max_attempts": "INTEGER NOT NULL DEFAULT 3",
        "started_at": "DATETIME",
        "finished_at": "DATETIME",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.exec_driver_sql(f"ALTER TABLE ingestion_jobs ADD COLUMN {name} {definition}")
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_request_hash ON ingestion_jobs (request_hash)"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_jobs_idempotency_key "
        "ON ingestion_jobs (idempotency_key)"
    )
    # Every row present before v8 lacks staged input and therefore cannot be retried safely.
    # The column default remains three for newly inserted v8 jobs.
    connection.exec_driver_sql("UPDATE ingestion_jobs SET max_attempts = 1, retryable = 0")
    connection.exec_driver_sql(
        "UPDATE ingestion_jobs SET started_at = created_at WHERE started_at IS NULL"
    )
    connection.exec_driver_sql(
        """UPDATE ingestion_jobs SET finished_at = updated_at
           WHERE finished_at IS NULL AND state != 'running'"""
    )
    connection.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS ingestion_job_inputs (
            job_id VARCHAR(36) PRIMARY KEY
                REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
            title VARCHAR(300) NOT NULL,
            kind VARCHAR(30) NOT NULL,
            uri TEXT,
            content TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL
        )"""
    )


def _generalize_governed_memory(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("decisions")}
    if "kind" not in columns:
        connection.exec_driver_sql(
            "ALTER TABLE decisions ADD COLUMN kind VARCHAR(30) NOT NULL DEFAULT 'decision'"
        )
    connection.exec_driver_sql("UPDATE decisions SET kind = 'decision' WHERE kind IS NULL")
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_decisions_kind ON decisions (kind)")


def _add_model_run_repair_lineage(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("model_runs")}
    additions = {
        "parent_run_id": "VARCHAR(36) REFERENCES model_runs(id) ON DELETE SET NULL",
        "attempt_number": "INTEGER NOT NULL DEFAULT 1",
        "repair_reason": "VARCHAR(80)",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.exec_driver_sql(f"ALTER TABLE model_runs ADD COLUMN {name} {definition}")
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_model_runs_parent_run_id ON model_runs (parent_run_id)"
    )
    connection.exec_driver_sql(
        "UPDATE model_runs SET attempt_number = 1 WHERE attempt_number IS NULL"
    )


def _normalize_governed_memory_statuses(connection: Connection) -> None:
    connection.exec_driver_sql(
        "UPDATE decisions SET status = 'obsolete' WHERE status = 'superseded'"
    )


def _add_import_receipts(connection: Connection) -> None:
    connection.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS import_receipts (
            id VARCHAR(36) PRIMARY KEY,
            schema VARCHAR(100) NOT NULL,
            payload_sha256 VARCHAR(64) NOT NULL UNIQUE,
            export_app_version VARCHAR(50) NOT NULL,
            export_created_at DATETIME NOT NULL,
            imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            counts_json JSON NOT NULL
        )"""
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_import_receipts_payload_sha256 "
        "ON import_receipts (payload_sha256)"
    )


def _enforce_memory_status_contract(connection: Connection) -> None:
    connection.exec_driver_sql(
        """UPDATE decisions
           SET status = CASE
               WHEN lower(trim(status)) IN
                    ('candidate', 'active', 'accepted', 'rejected', 'obsolete')
                   THEN lower(trim(status))
               WHEN lower(trim(status)) IN ('superseded', 'replaced') THEN 'obsolete'
               ELSE 'candidate'
           END"""
    )


def _add_git_repositories(connection: Connection) -> None:
    connection.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS git_repositories (
            id VARCHAR(36) PRIMARY KEY,
            title VARCHAR(300) NOT NULL,
            path TEXT NOT NULL UNIQUE,
            current_commit_sha VARCHAR(40),
            status VARCHAR(30) NOT NULL,
            created_at DATETIME NOT NULL,
            indexed_at DATETIME NOT NULL
        )"""
    )
    columns = {column["name"] for column in inspect(connection).get_columns("sources")}
    additions = {
        "git_repository_id": "VARCHAR(36) REFERENCES git_repositories(id) ON DELETE CASCADE",
        "git_commit_sha": "VARCHAR(40)",
        "git_path": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.exec_driver_sql(f"ALTER TABLE sources ADD COLUMN {name} {definition}")
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sources_git_repository_id ON sources (git_repository_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sources_git_commit_sha ON sources (git_commit_sha)"
    )


MIGRATIONS: tuple[Migration, ...] = (
    (1, "initial foundation schema", _initial_schema),
    (2, "immutable source versions", _add_source_versions),
    (3, "observable ingestion jobs", _add_ingestion_jobs),
    (4, "governed memory audit trail", _add_memory_audit),
    (5, "provider-neutral model runs", _add_model_runs),
    (6, "versioned chunk embeddings", _add_chunk_embeddings),
    (7, "model-derived decision candidates", _link_decisions_to_model_runs),
    (8, "resumable atomic ingestion jobs", _add_resumable_ingestion_jobs),
    (9, "generalized governed memory kinds", _generalize_governed_memory),
    (10, "bounded model output repair lineage", _add_model_run_repair_lineage),
    (11, "normalize governed memory statuses", _normalize_governed_memory_statuses),
    (12, "portable import receipts", _add_import_receipts),
    (13, "enforce governed memory status contract", _enforce_memory_status_contract),
    (14, "read-only git repository sources", _add_git_repositories),
)


def run_migrations(engine: Engine) -> None:
    """Apply pending SQLite schema migrations transactionally and in order."""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        applied = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }
        for version, description, migration in MIGRATIONS:
            if version in applied:
                continue
            migration(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, description) "
                    "VALUES (:version, :description)"
                ),
                {"version": version, "description": description},
            )
