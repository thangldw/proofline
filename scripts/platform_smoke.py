#!/usr/bin/env python3
"""Credential-free installed-package smoke test for declared development platforms."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="proofline-platform-smoke-") as directory:
        root = Path(directory)
        os.environ["PROOFLINE_DATABASE_URL"] = f"sqlite:///{root / 'proofline.db'}"
        os.environ["PROOFLINE_AI_PROVIDER"] = "disabled"
        os.environ["PROOFLINE_EMBEDDING_PROVIDER"] = "disabled"
        os.environ["PROOFLINE_ALLOW_REMOTE_AI"] = "false"

        from proofline.backup import create_sqlite_backup, verify_sqlite_backup
        from proofline.database import SessionLocal, engine, initialize_database
        from proofline.ingestion import ingest_source
        from proofline.portability import (
            atomic_write_export,
            build_portable_export,
            load_and_verify_export,
        )
        from proofline.retrieval import lexical_search
        from proofline.schemas import SourceCreate

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

        backup_path = root / "proofline-backup.db"
        backup_report = create_sqlite_backup(engine, backup_path)
        assert verify_sqlite_backup(backup_path) == backup_report

        print(
            json.dumps(
                {
                    "status": "ok",
                    "sources": export_counts["sources"],
                    "source_versions": export_counts["source_versions"],
                    "migration_version": backup_report["migration_version"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
