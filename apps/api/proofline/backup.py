from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import Engine

from .migrations import MIGRATIONS

REQUIRED_CORE_TABLES = {
    "schema_migrations",
    "sources",
    "source_versions",
    "chunks",
    "chunk_search",
    "decisions",
    "evidence",
    "audit_events",
    "model_runs",
    "chunk_embeddings",
    "ingestion_jobs",
    "ingestion_job_inputs",
    "import_receipts",
}


class BackupError(RuntimeError):
    """A backup failure identified only by a safe non-content-bearing code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _readonly_connection(path: Path) -> sqlite3.Connection:
    absolute = Path(os.path.abspath(path.expanduser()))
    uri = f"file:{quote(str(absolute), safe='/')}?mode=ro&immutable=1"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise BackupError("backup_unreadable") from exc


def verify_sqlite_backup(path: Path) -> dict[str, int]:
    connection = _readonly_connection(path)
    try:
        try:
            quick = [row[0] for row in connection.execute("PRAGMA quick_check").fetchall()]
            if quick != ["ok"]:
                raise BackupError("quick_check_failed")
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()]
            if integrity != ["ok"]:
                raise BackupError("integrity_check_failed")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise BackupError("foreign_key_check_failed")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                ).fetchall()
            }
            if not REQUIRED_CORE_TABLES.issubset(tables):
                raise BackupError("required_schema_missing")
            versions = {
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
            }
        except BackupError:
            raise
        except sqlite3.Error as exc:
            raise BackupError("backup_validation_failed") from exc
        expected_versions = {version for version, _description, _migration in MIGRATIONS}
        if versions != expected_versions or max(versions, default=0) != max(expected_versions):
            raise BackupError("migration_version_mismatch")
        return {
            "migration_version": max(versions),
            "table_count": len(tables),
        }
    finally:
        connection.close()


def _publish_backup(temporary: Path, output: Path, *, force: bool) -> None:
    try:
        if force:
            os.replace(temporary, output)
        else:
            os.link(temporary, output)
            temporary.unlink()
        os.chmod(output, 0o600)
    except FileExistsError as exc:
        raise BackupError("output_exists") from exc
    except OSError as exc:
        raise BackupError("backup_publish_failed") from exc


def create_sqlite_backup(engine: Engine, output: Path, *, force: bool = False) -> dict[str, int]:
    if engine.dialect.name != "sqlite":
        raise BackupError("sqlite_required")
    output = Path(os.path.abspath(output.expanduser()))
    source_database = engine.url.database
    if source_database and source_database != ":memory:":
        source_path = Path(os.path.abspath(Path(source_database).expanduser()))
        if output == source_path:
            raise BackupError("output_is_live_database")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(temporary_name)
    os.close(descriptor)
    os.chmod(temporary, 0o600)
    try:
        try:
            with engine.connect() as sqlalchemy_connection:
                source = sqlalchemy_connection.connection.driver_connection
                destination = sqlite3.connect(temporary)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
        except (sqlite3.Error, OSError, AttributeError) as exc:
            raise BackupError("backup_creation_failed") from exc
        report = verify_sqlite_backup(temporary)
        _publish_backup(temporary, output, force=force)
        return report
    finally:
        if temporary.exists():
            temporary.unlink()
