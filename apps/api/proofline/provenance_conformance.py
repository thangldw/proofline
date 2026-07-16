from __future__ import annotations

import hashlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .database import initialize_database, make_engine
from .evidence_packages import (
    DECISION_PACKAGE_SCHEMA,
    atomic_write_package,
    build_decision_package,
    load_and_verify_package,
)
from .ingestion import ingest_source
from .integrity import verify_live_database
from .models import Decision
from .portability import build_portable_export, canonical_json_bytes
from .portable_import import import_portable_export
from .schemas import SourceCreate

CONFORMANCE_SCHEMA = "proofline-provenance-conformance-v1"
_FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_ORIGINAL_CONTENT = (
    "Decision: retain immutable evidence identities.\n"
    "Reason: derived claims must resolve to exact source spans."
)
_UPDATED_CONTENT = (
    "Decision: retain immutable evidence identities and signed receipts.\n"
    "Reason: verification requirements changed."
)


def _decision_for_current_version(session, source_id: str, source_version_id: str) -> Decision:
    decision = session.scalar(
        select(Decision).where(
            Decision.source_id == source_id,
            Decision.source_version_id == source_version_id,
            Decision.kind == "decision",
        )
    )
    if decision is None:
        raise RuntimeError("conformance_decision_missing")
    return decision


def run_provenance_conformance() -> dict[str, Any]:
    """Exercise production provenance paths and return a content-free receipt."""

    checks: dict[str, bool] = {}
    counts: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="proofline-provenance-") as directory:
        root = Path(directory)
        source_engine = make_engine(f"sqlite:///{root / 'source.db'}")
        target_engine = make_engine(f"sqlite:///{root / 'target.db'}")
        initialize_database(source_engine)
        initialize_database(target_engine)
        source_factory = sessionmaker(bind=source_engine, expire_on_commit=False)
        target_factory = sessionmaker(bind=target_engine, expire_on_commit=False)
        try:
            with source_factory() as session:
                source, created = ingest_source(
                    session,
                    SourceCreate(
                        title="Provenance conformance fixture",
                        uri="file:///proofline-conformance.md",
                        content=_ORIGINAL_CONTENT,
                    ),
                )
                if not created or source.current_version_id is None:
                    raise RuntimeError("conformance_source_creation_failed")
                decision = _decision_for_current_version(
                    session, source.id, source.current_version_id
                )
                artifact_id = decision.id
                original_version_id = decision.source_version_id
                first = build_decision_package(session, artifact_id, created_at=_FIXED_TIME)
                second = build_decision_package(session, artifact_id, created_at=_FIXED_TIME)
                original_root = first["manifest"]["root_hash"]
                checks["deterministic_package_root"] = (
                    first == second and original_root == second["manifest"]["root_hash"]
                )

                citations = first["payload"]["citations"]
                chunks = {item["node_hash"] for item in first["payload"]["chunks"]}
                checks["exact_citation_chunk_chain"] = bool(citations) and all(
                    citation["chunk_node_hashes"]
                    and set(citation["chunk_node_hashes"]).issubset(chunks)
                    for citation in citations
                )

                first_archive = root / "first.zip"
                second_archive = root / "second.zip"
                atomic_write_package(first_archive, first)
                atomic_write_package(second_archive, second)
                _loaded, archive_report = load_and_verify_package(first_archive)
                checks["deterministic_archive"] = (
                    first_archive.read_bytes() == second_archive.read_bytes()
                )
                checks["verified_archive_round_trip"] = (
                    archive_report["valid"] is True and archive_report["root_hash"] == original_root
                )

                updated, updated_created = ingest_source(
                    session,
                    SourceCreate(
                        title="Provenance conformance fixture revised",
                        uri="file:///proofline-conformance.md",
                        content=_UPDATED_CONTENT,
                    ),
                )
                if updated_created or updated.current_version_id == original_version_id:
                    raise RuntimeError("conformance_source_update_failed")
                rebuilt = build_decision_package(session, artifact_id, created_at=_FIXED_TIME)
                checks["source_update_preserves_old_artifact"] = (
                    rebuilt["manifest"]["root_hash"] == original_root
                )
                portable = build_portable_export(session, created_at=_FIXED_TIME)

            with target_factory() as target, target.begin():
                import_report = import_portable_export(target, portable)
            with target_factory() as target:
                imported = build_decision_package(target, artifact_id, created_at=_FIXED_TIME)
                checks["portable_round_trip_preserves_root"] = (
                    imported["manifest"]["root_hash"] == original_root
                )

            source_integrity = verify_live_database(source_engine)
            target_integrity = verify_live_database(target_engine)
            checks["source_database_integrity"] = source_integrity["valid"] is True
            checks["imported_database_integrity"] = target_integrity["valid"] is True
            counts = {
                "source_versions": source_integrity["source_versions"],
                "decisions": source_integrity["memories"],
                "evidence": source_integrity["evidence"],
                "portable_records": sum(import_report["counts"].values()),
            }
        finally:
            source_engine.dispose()
            target_engine.dispose()

    if not all(checks.values()):
        raise RuntimeError("provenance_conformance_failed")
    contract = {
        "schema": CONFORMANCE_SCHEMA,
        "package_schema": DECISION_PACKAGE_SCHEMA,
        "checks": checks,
        "counts": counts,
        "qualification": (
            "credential-free deterministic SQLite conformance only; does not establish "
            "authenticity, signature trust, external-model behavior, or production scale"
        ),
    }
    return {
        **contract,
        "receipt_sha256": hashlib.sha256(canonical_json_bytes(contract)).hexdigest(),
    }
