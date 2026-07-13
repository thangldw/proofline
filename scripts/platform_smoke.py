#!/usr/bin/env python3
"""Credential-free installed-package smoke test for declared development platforms."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="proofline-platform-smoke-") as directory:
        root = Path(directory)
        os.environ["PROOFLINE_DATABASE_URL"] = f"sqlite:///{root / 'proofline.db'}"
        os.environ["PROOFLINE_AI_PROVIDER"] = "disabled"
        os.environ["PROOFLINE_EMBEDDING_PROVIDER"] = "disabled"
        os.environ["PROOFLINE_ALLOW_REMOTE_AI"] = "false"

        from proofline.backup import (
            create_sqlite_backup,
            restore_sqlite_backup,
            verify_sqlite_backup,
        )
        from proofline.database import SessionLocal, engine, initialize_database, make_engine
        from proofline.ingestion import ingest_source
        from proofline.portability import (
            atomic_write_export,
            build_portable_export,
            load_and_verify_export,
        )
        from proofline.portable_import import import_portable_export, load_verified_import
        from proofline.retrieval import lexical_search
        from proofline.schemas import SourceCreate
        from sqlalchemy.orm import sessionmaker

        initialize_database()
        first_content = (
            "# Platform smoke 🧠\n\n"
            "Decision: Use SQLite for portable local state.\n"
            "Reason: deterministic setup needs no external service."
        )
        second_content = (
            "# Platform smoke 🧠\n\n"
            "Decision: Keep SQLite for portable local state.\n"
            "Reason: exact evidence remains inspectable across versions."
        )
        with SessionLocal() as session:
            source, created = ingest_source(
                session,
                SourceCreate(
                    title="Platform smoke",
                    uri="smoke://platform/decision",
                    content=first_content,
                ),
            )
            assert created
            source, created = ingest_source(
                session,
                SourceCreate(
                    title="Platform smoke revised",
                    uri="smoke://platform/decision",
                    content=second_content,
                ),
            )
            assert not created
            assert len(source.versions) == 2
            hits = lexical_search(session, "inspectable versions", limit=5)
            assert hits and hits[0].source_id == source.id
            assert second_content[hits[0].start_offset : hits[0].end_offset] == hits[0].content
            memory = next(
                item
                for item in source.decisions
                if item.source_version_id == source.current_version_id
            )
            evidence = memory.evidence[0]
            assert second_content[evidence.start_offset : evidence.end_offset] == evidence.quote

        export_path = root / "portable.json"
        with SessionLocal() as session, session.begin():
            document = build_portable_export(session)
        atomic_write_export(export_path, document)
        export_counts = load_and_verify_export(export_path)

        restored_engine = make_engine(f"sqlite:///{root / 'restored.db'}")
        initialize_database(restored_engine)
        restored_sessions = sessionmaker(bind=restored_engine, expire_on_commit=False)
        with restored_sessions() as restored, restored.begin():
            import_report = import_portable_export(restored, load_verified_import(export_path))
        with restored_sessions() as restored:
            restored_hits = lexical_search(restored, "inspectable versions", limit=5)
            assert restored_hits and restored_hits[0].source_id == source.id
        restored_engine.dispose()

        backup_path = root / "proofline-backup.db"
        backup_report = create_sqlite_backup(engine, backup_path)
        assert verify_sqlite_backup(backup_path) == backup_report
        live_path = root / "proofline.db"
        rollback_path = root / "proofline-before-restore.db"
        restored_path = root / "restored-from-backup.db"
        shutil.copy2(live_path, restored_path)
        drill_engine = make_engine(f"sqlite:///{restored_path}")
        drill_sessions = sessionmaker(bind=drill_engine, expire_on_commit=False)
        with drill_sessions() as drill:
            extra_source, extra_created = ingest_source(
                drill,
                SourceCreate(
                    title="Restore drill marker",
                    uri="smoke://platform/restore-drill",
                    content="Decision: Preserve rollbackmarkerx during a restore drill.",
                ),
            )
            assert extra_created
            extra_source_id = extra_source.id
        drill_engine.dispose()
        restore_report = restore_sqlite_backup(
            backup_path,
            restored_path,
            rollback_output=rollback_path,
        )
        assert restore_report["rollback_created"] is True
        assert verify_sqlite_backup(restored_path) == backup_report
        restored_engine = make_engine(f"sqlite:///{restored_path}")
        restored_sessions = sessionmaker(bind=restored_engine, expire_on_commit=False)
        with restored_sessions() as restored:
            assert not lexical_search(restored, "rollbackmarkerx", limit=5)
        restored_engine.dispose()
        rollback_drill_path = root / "proofline-before-rollback.db"
        rollback_report = restore_sqlite_backup(
            rollback_path,
            restored_path,
            rollback_output=rollback_drill_path,
        )
        assert rollback_report["rollback_created"] is True
        assert verify_sqlite_backup(restored_path) == backup_report
        rolled_back_engine = make_engine(f"sqlite:///{restored_path}")
        rolled_back_sessions = sessionmaker(bind=rolled_back_engine, expire_on_commit=False)
        with rolled_back_sessions() as rolled_back:
            rolled_back_hits = lexical_search(rolled_back, "rollbackmarkerx", limit=5)
            assert rolled_back_hits and rolled_back_hits[0].source_id == extra_source_id
        rolled_back_engine.dispose()

        print(
            json.dumps(
                {
                    "status": "ok",
                    "sources": export_counts["sources"],
                    "source_versions": export_counts["source_versions"],
                    "import_payload_sha256": import_report["payload_sha256"],
                    "migration_version": backup_report["migration_version"],
                    "backup_restore": True,
                    "rollback_restore": True,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
