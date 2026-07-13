import hashlib
import json
import shutil
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path

import proofline.backup as backup_module
import proofline.cli as cli_module
import pytest
from proofline.backup import (
    BackupError,
    create_sqlite_backup,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from proofline.cli import main
from proofline.ingestion import ingest_source
from proofline.models import (
    AuditEvent,
    Decision,
    ImportReceipt,
    IngestionJob,
    IngestionJobInput,
    ModelRun,
)
from proofline.schemas import SourceCreate
from sqlalchemy import func, select


def raw_backup_fixture(session):
    original = "Decision: Use Kafka for high throughput\nReason: projected traffic was high."
    source, _ = ingest_source(
        session,
        SourceCreate(title="Messaging ADR", uri="file:///messaging.md", content=original),
    )
    historical_version_id = source.current_version_id
    revised = "Decision: Use NATS for modest traffic\nReason: operations stay simple."
    source, _ = ingest_source(
        session,
        SourceCreate(title="Messaging ADR revised", uri="file:///messaging.md", content=revised),
    )
    memory = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    run = ModelRun(
        provider_id="backup-test",
        model_id="safe-model-id",
        operation="generate",
        template_version="backup-test-v1",
        input_hashes=[source.versions[-1].content_hash],
        attempt_number=1,
        status="succeeded",
        validation_status="valid",
    )
    session.add(run)
    session.flush()
    memory.model_run_id = run.id
    session.add(
        AuditEvent(
            actor="local_user",
            action="memory.updated",
            object_type="memory",
            object_id=memory.id,
            before_json={"status": memory.status},
            after_json={"status": "accepted"},
        )
    )
    memory.status = "accepted"
    private_content = "RAW-BACKUP-PRIVATE-STAGED-CONTENT"
    job = IngestionJob(
        source_id=source.id,
        source_version_id=source.current_version_id,
        state="failed",
        stage="parse",
        attempts=1,
        request_hash="raw-private-request-hash",
        idempotency_key="raw-private-idempotency-key",
        error_code="ingestion_error",
        error_detail="raw private diagnostic",
        retryable=True,
    )
    session.add(job)
    session.flush()
    session.add(
        IngestionJobInput(
            job_id=job.id,
            title="private staged title",
            kind="markdown",
            uri="file:///private-staged.md",
            content=private_content,
            content_hash=hashlib.sha256(private_content.encode()).hexdigest(),
        )
    )
    session.add(
        ImportReceipt(
            schema="proofline-portable-export-v1",
            payload_sha256="b" * 64,
            export_app_version="0.1.0a2",
            export_created_at=datetime(2026, 7, 13, tzinfo=UTC),
            counts_json={"sources": 2, "source_versions": 2},
        )
    )
    session.commit()
    return {
        "source_id": source.id,
        "historical_version_id": historical_version_id,
        "current_version_id": source.current_version_id,
        "memory_id": memory.id,
        "run_id": run.id,
        "private_content": private_content,
    }


def read_only(path):
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def test_online_backup_is_complete_sensitive_and_live_database_remains_usable(session, tmp_path):
    expected = raw_backup_fixture(session)
    output = tmp_path / "proofline-backup.db"

    report = create_sqlite_backup(session.get_bind(), output)

    assert report["migration_version"] >= 1
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    before_verification = hashlib.sha256(output.read_bytes()).hexdigest()
    assert verify_sqlite_backup(output) == report
    assert hashlib.sha256(output.read_bytes()).hexdigest() == before_verification
    with read_only(output) as recovered:
        assert recovered.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0] == 2
        assert (
            recovered.execute(
                "SELECT content FROM ingestion_job_inputs WHERE content = ?",
                (expected["private_content"],),
            ).fetchone()[0]
            == expected["private_content"]
        )
        assert recovered.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 1
        assert recovered.execute("SELECT id FROM model_runs").fetchone()[0] == expected["run_id"]
        assert (
            recovered.execute("SELECT payload_sha256 FROM import_receipts").fetchone()[0]
            == "b" * 64
        )

    ingest_source(
        session,
        SourceCreate(title="After backup", uri="file:///after.md", content="Decision: continue."),
    )
    assert session.scalar(select(func.count()).select_from(Decision)) == 3


def test_backup_recovery_exercise_preserves_exact_evidence_and_hashes(session, tmp_path):
    expected = raw_backup_fixture(session)
    backup = tmp_path / "backup.db"
    recovered_copy = tmp_path / "recovered.db"
    create_sqlite_backup(session.get_bind(), backup)
    shutil.copy2(backup, recovered_copy)

    assert verify_sqlite_backup(recovered_copy)["migration_version"] >= 1
    with read_only(recovered_copy) as recovered:
        row = recovered.execute(
            """SELECT sv.content, sv.content_hash, e.quote, e.quote_hash,
                      e.start_offset, e.end_offset
               FROM evidence e
               JOIN source_versions sv ON sv.id = e.source_version_id
               WHERE e.decision_id = ?""",
            (expected["memory_id"],),
        ).fetchone()
        content, content_hash, quote, quote_hash, start, end = row
        assert content[start:end] == quote
        assert hashlib.sha256(content.encode()).hexdigest() == content_hash
        assert hashlib.sha256(quote.encode()).hexdigest() == quote_hash
        assert (
            recovered.execute(
                "SELECT COUNT(*) FROM source_versions WHERE source_id = ?",
                (expected["source_id"],),
            ).fetchone()[0]
            == 2
        )


def test_restore_backup_preserves_rollback_and_can_reverse_the_restore(session, tmp_path):
    raw_backup_fixture(session)
    engine = session.get_bind()
    target = Path(engine.url.database)
    backup = tmp_path / "before-change.db"
    rollback = tmp_path / "before-restore.db"
    reverse_rollback = tmp_path / "before-rollback.db"
    create_sqlite_backup(engine, backup)

    ingest_source(
        session,
        SourceCreate(
            title="Post-backup state",
            uri="file:///post-backup.md",
            content="Decision: this state must survive in the rollback copy.",
        ),
    )
    assert session.scalar(select(func.count()).select_from(Decision)) == 3
    session.close()
    engine.dispose()

    restored = restore_sqlite_backup(backup, target, rollback_output=rollback)
    assert restored["target_existed"] is True
    assert restored["rollback_created"] is True
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with read_only(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2
    with read_only(rollback) as connection:
        assert connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 3

    reversed_report = restore_sqlite_backup(
        rollback,
        target,
        rollback_output=reverse_rollback,
    )
    assert reversed_report["rollback_created"] is True
    with read_only(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 3
    with read_only(reverse_rollback) as connection:
        assert connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2


def test_restore_backup_requires_safe_distinct_paths_and_no_sqlite_sidecars(session, tmp_path):
    raw_backup_fixture(session)
    engine = session.get_bind()
    target = Path(engine.url.database)
    backup = tmp_path / "backup.db"
    rollback = tmp_path / "rollback.db"
    create_sqlite_backup(engine, backup)
    session.close()
    engine.dispose()

    new_target = tmp_path / "new-target.db"
    created = restore_sqlite_backup(backup, new_target)
    assert created["target_existed"] is False
    assert created["rollback_created"] is False
    assert verify_sqlite_backup(new_target)["migration_version"] >= 1

    with pytest.raises(BackupError, match="rollback_output_required"):
        restore_sqlite_backup(backup, target)
    with pytest.raises(BackupError, match="restore_paths_must_be_distinct"):
        restore_sqlite_backup(backup, target, rollback_output=backup)
    rollback.write_bytes(b"do not overwrite")
    with pytest.raises(BackupError, match="rollback_output_exists"):
        restore_sqlite_backup(backup, target, rollback_output=rollback)
    rollback.unlink()
    sidecar = Path(f"{target}-wal")
    sidecar.touch()
    with pytest.raises(BackupError, match="restore_target_has_sidecars"):
        restore_sqlite_backup(backup, target, rollback_output=rollback)
    sidecar.unlink()


def test_backup_verifier_rejects_corruption_truncation_and_old_schema(tmp_path):
    corrupted = tmp_path / "corrupted.db"
    corrupted.write_bytes(b"not a sqlite database")
    with pytest.raises(BackupError):
        verify_sqlite_backup(corrupted)

    truncated = tmp_path / "truncated.db"
    with sqlite3.connect(truncated) as connection:
        connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY)")
        connection.commit()
    truncated.write_bytes(truncated.read_bytes()[:64])
    with pytest.raises(BackupError):
        verify_sqlite_backup(truncated)

    old = tmp_path / "old.db"
    with sqlite3.connect(old) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, description TEXT)"
        )
        connection.execute("INSERT INTO schema_migrations VALUES (1, 'old')")
        connection.commit()
    with pytest.raises(BackupError, match="required_schema_missing"):
        verify_sqlite_backup(old)


def test_backup_publish_no_overwrite_force_permissions_and_temp_cleanup(session, tmp_path):
    raw_backup_fixture(session)
    output = tmp_path / "backup.db"
    create_sqlite_backup(session.get_bind(), output)
    original = output.read_bytes()

    with pytest.raises(BackupError, match="output_exists"):
        create_sqlite_backup(session.get_bind(), output)
    assert output.read_bytes() == original
    assert not list(tmp_path.glob(".backup.db.*"))

    ingest_source(
        session,
        SourceCreate(title="New", uri="file:///new.md", content="Decision: new state."),
    )
    create_sqlite_backup(session.get_bind(), output, force=True)
    assert output.read_bytes() != original
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".backup.db.*"))


def test_backup_publish_failure_is_safe_and_preserves_existing_output(
    session, tmp_path, monkeypatch
):
    raw_backup_fixture(session)
    output = tmp_path / "backup.db"
    create_sqlite_backup(session.get_bind(), output)
    original = output.read_bytes()
    monkeypatch.setattr(
        backup_module.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(PermissionError("test-only failure")),
    )

    with pytest.raises(BackupError, match="backup_publish_failed"):
        create_sqlite_backup(session.get_bind(), output, force=True)

    assert output.read_bytes() == original
    assert not list(tmp_path.glob(".backup.db.*"))


def test_backup_refuses_non_sqlite_engine(tmp_path):
    class NonSqliteEngine:
        class Dialect:
            name = "postgresql"

        dialect = Dialect()

    with pytest.raises(BackupError, match="sqlite_required"):
        create_sqlite_backup(NonSqliteEngine(), tmp_path / "backup.db")


def test_backup_cli_refuses_non_sqlite_before_initialization(tmp_path, monkeypatch):
    class NonSqliteEngine:
        class Dialect:
            name = "postgresql"

        dialect = Dialect()

    monkeypatch.setattr(cli_module, "engine", NonSqliteEngine())
    monkeypatch.setattr(
        cli_module,
        "initialize_database",
        lambda: pytest.fail("non-SQLite backup must not initialize or migrate the database"),
    )

    with pytest.raises(SystemExit, match="backup failed: sqlite_required"):
        main(["backup", "--output", str(tmp_path / "backup.db")])


def test_backup_cli_passes_and_fails_with_safe_codes(session, tmp_path, monkeypatch, capsys):
    expected = raw_backup_fixture(session)
    monkeypatch.setattr(cli_module, "engine", session.get_bind())
    monkeypatch.setattr(cli_module, "initialize_database", lambda: None)
    output = tmp_path / "cli-backup.db"

    main(["backup", "--output", str(output)])
    assert json.loads(capsys.readouterr().out)["valid"] is True
    main(["verify-backup", str(output)])
    assert json.loads(capsys.readouterr().out)["valid"] is True

    output.write_bytes(b"CORRUPTED-" + expected["private_content"].encode())
    with pytest.raises(SystemExit, match="backup verification failed:"):
        main(["verify-backup", str(output)])
    assert expected["private_content"] not in capsys.readouterr().err

    with pytest.raises(SystemExit, match="backup failed: output_exists"):
        main(["backup", "--output", str(output)])


def test_restore_backup_cli_targets_configured_sqlite_and_reports_rollback(
    session, tmp_path, monkeypatch, capsys
):
    raw_backup_fixture(session)
    engine = session.get_bind()
    target = Path(engine.url.database)
    backup = tmp_path / "cli-restore-source.db"
    rollback = tmp_path / "cli-rollback.db"
    create_sqlite_backup(engine, backup)
    ingest_source(
        session,
        SourceCreate(
            title="After CLI backup",
            uri="file:///after-cli-backup.md",
            content="Decision: preserve this only in the CLI rollback copy.",
        ),
    )
    session.close()
    monkeypatch.setattr(cli_module, "engine", engine)

    main(["restore-backup", str(backup), "--rollback-output", str(rollback)])

    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert report["rollback_created"] is True
    with read_only(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2
    with read_only(rollback) as connection:
        assert connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 3
