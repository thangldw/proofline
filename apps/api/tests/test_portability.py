import copy
import hashlib
import json
import stat
from datetime import UTC, datetime, timedelta

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.ingestion import ingest_source
from proofline.models import AuditEvent, Decision, IngestionJob, IngestionJobInput, ModelRun
from proofline.portability import (
    PORTABLE_EXPORT_SCHEMA,
    PortabilityError,
    atomic_write_export,
    build_portable_export,
    canonical_json_bytes,
    load_and_verify_export,
    payload_sha256,
    verify_portable_export,
)
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def rich_export_fixture(session):
    first_content = "Decision: Use Kafka for throughput\nReason: expected high traffic."
    source, _ = ingest_source(
        session,
        SourceCreate(title="Queue ADR", uri="file:///queue.md", content=first_content),
    )
    old_version_id = source.current_version_id
    second_content = "Decision: Use NATS for simplicity\nReason: measured traffic is modest."
    source, _ = ingest_source(
        session,
        SourceCreate(title="Queue ADR revised", uri="file:///queue.md", content=second_content),
    )
    memory = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    parent = ModelRun(
        provider_id="test-provider",
        model_id="test-model",
        operation="generate",
        template_version="memory-v1",
        input_hashes=[source.content_hash],
        attempt_number=1,
        status="failed",
        validation_status="invalid",
        error_code="structured_output_invalid",
    )
    session.add(parent)
    session.flush()
    child = ModelRun(
        provider_id="test-provider",
        model_id="test-model",
        operation="generate",
        template_version="memory-v1-repair-v1",
        input_hashes=[source.content_hash],
        parent_run_id=parent.id,
        attempt_number=2,
        repair_reason="structured_output_invalid",
        status="succeeded",
        validation_status="valid",
    )
    session.add(child)
    session.flush()
    before = {
        "kind": memory.kind,
        "statement": memory.statement,
        "rationale": memory.rationale,
        "status": memory.status,
    }
    memory.statement = "Use NATS after measured traffic remained modest"
    memory.rationale = "Corrected by human review."
    memory.status = "accepted"
    memory.model_run_id = child.id
    session.add(
        AuditEvent(
            actor="local_user",
            action="memory.updated",
            object_type="memory",
            object_id=memory.id,
            before_json=before,
            after_json={
                **before,
                "statement": memory.statement,
                "rationale": memory.rationale,
                "status": memory.status,
            },
        )
    )
    private_sentinel = "PRIVATE-STAGED-INGESTION-SENTINEL"
    job = IngestionJob(
        source_id=source.id,
        source_version_id=source.current_version_id,
        state="failed",
        stage="parse",
        attempts=1,
        request_hash="REQUEST-HASH-MUST-NOT-EXPORT",
        idempotency_key="IDEMPOTENCY-KEY-MUST-NOT-EXPORT",
        error_code="ingestion_error",
        error_detail="safe stored detail",
        retryable=True,
    )
    session.add(job)
    session.flush()
    session.add(
        IngestionJobInput(
            job_id=job.id,
            title="private input",
            kind="markdown",
            uri="file:///private.md",
            content=private_sentinel,
            content_hash=hashlib.sha256(private_sentinel.encode()).hexdigest(),
        )
    )
    session.commit()
    return {
        "source_id": source.id,
        "current_version_id": source.current_version_id,
        "old_version_id": old_version_id,
        "memory_id": memory.id,
        "parent_run_id": parent.id,
        "child_run_id": child.id,
        "sentinel": private_sentinel,
    }


def test_payload_hash_is_stable_and_export_is_complete_and_private(session):
    expected = rich_export_fixture(session)

    first = build_portable_export(session, created_at=datetime(2026, 1, 1, tzinfo=UTC))
    second = build_portable_export(session, created_at=datetime(2026, 1, 2, tzinfo=UTC))

    assert first["manifest"]["schema"] == PORTABLE_EXPORT_SCHEMA
    assert first["manifest"]["created_at"] != second["manifest"]["created_at"]
    assert first["manifest"]["payload_sha256"] == second["manifest"]["payload_sha256"]
    assert first["payload"] == second["payload"]
    versions = first["payload"]["source_versions"]
    assert {item["id"] for item in versions} >= {
        expected["old_version_id"],
        expected["current_version_id"],
    }
    memory = next(
        item for item in first["payload"]["memories"] if item["id"] == expected["memory_id"]
    )
    assert memory["status"] == "accepted"
    assert memory["model_run_id"] == expected["child_run_id"]
    child = next(
        item for item in first["payload"]["model_runs"] if item["id"] == expected["child_run_id"]
    )
    assert child["parent_run_id"] == expected["parent_run_id"]
    assert any(
        item["object_id"] == expected["memory_id"] for item in first["payload"]["audit_events"]
    )
    assert verify_portable_export(first) == first["manifest"]["counts"]

    encoded = canonical_json_bytes(first).decode("utf-8")
    for forbidden in [
        expected["sentinel"],
        "REQUEST-HASH-MUST-NOT-EXPORT",
        "IDEMPOTENCY-KEY-MUST-NOT-EXPORT",
        "safe stored detail",
        "ingestion_job_inputs",
        "idempotency_key",
        "request_hash",
        "chunks",
        "embeddings",
        "chunk_search",
    ]:
        assert forbidden not in encoded
    assert '"prompt":' not in encoded


def test_empty_database_export_is_valid_and_deterministic(session):
    document = build_portable_export(session)

    assert document["manifest"]["counts"] == {key: 0 for key in sorted(document["payload"])}
    assert verify_portable_export(document) == document["manifest"]["counts"]


def test_verifier_detects_hash_and_rehashed_provenance_tampering(session):
    rich_export_fixture(session)
    original = build_portable_export(session)
    changed = copy.deepcopy(original)
    changed["payload"]["source_versions"][0]["content"] += " tampered"

    with pytest.raises(PortabilityError, match="payload_hash_mismatch"):
        verify_portable_export(changed)

    changed["manifest"]["payload_sha256"] = payload_sha256(changed["payload"])
    with pytest.raises(PortabilityError, match="source_content_hash_mismatch"):
        verify_portable_export(changed)

    hidden = copy.deepcopy(original)
    hidden["payload"]["model_runs"][0]["prompt"] = "hidden content"
    hidden["manifest"]["payload_sha256"] = payload_sha256(hidden["payload"])
    with pytest.raises(PortabilityError, match="unexpected_fields"):
        verify_portable_export(hidden)


def test_verifier_detects_rehashed_line_and_orphan_memory_tampering(session):
    rich_export_fixture(session)
    original = build_portable_export(session)
    changed_line = copy.deepcopy(original)
    changed_line["payload"]["evidence"][0]["start_line"] += 1
    changed_line["manifest"]["payload_sha256"] = payload_sha256(changed_line["payload"])

    with pytest.raises(PortabilityError, match="evidence_line_mismatch"):
        verify_portable_export(changed_line)

    orphan = copy.deepcopy(original)
    memory_id = orphan["payload"]["memories"][0]["id"]
    orphan["payload"]["evidence"] = [
        item for item in orphan["payload"]["evidence"] if item["memory_id"] != memory_id
    ]
    orphan["manifest"]["counts"]["evidence"] = len(orphan["payload"]["evidence"])
    orphan["manifest"]["payload_sha256"] = payload_sha256(orphan["payload"])

    with pytest.raises(PortabilityError, match="memory_without_evidence"):
        verify_portable_export(orphan)

    invalid_identity = copy.deepcopy(original)
    invalid_identity["payload"]["sources"][0]["identity_hash"] = "not-a-sha256"
    invalid_identity["manifest"]["payload_sha256"] = payload_sha256(invalid_identity["payload"])

    with pytest.raises(PortabilityError, match="invalid_source_identity"):
        verify_portable_export(invalid_identity)


def test_atomic_writer_refuses_overwrite_and_enforces_private_permissions(session, tmp_path):
    document = build_portable_export(session)
    output = tmp_path / "portable.json"

    atomic_write_export(output, document)

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert load_and_verify_export(output) == document["manifest"]["counts"]
    original = output.read_bytes()
    with pytest.raises(PortabilityError, match="output_exists"):
        atomic_write_export(output, {"not": "written"})
    assert output.read_bytes() == original
    assert not list(tmp_path.glob(".portable.json.*"))

    replacement = build_portable_export(
        session, created_at=datetime.now(UTC) + timedelta(seconds=1)
    )
    atomic_write_export(output, replacement, force=True)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.read_bytes() != original


def test_export_and_verifier_cli_pass_and_fail_safely(session, tmp_path, monkeypatch, capsys):
    rich_export_fixture(session)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    monkeypatch.setattr(cli_module, "initialize_database", lambda: None)
    output = tmp_path / "cli-export.json"

    main(["export", "--output", str(output)])
    exported = json.loads(capsys.readouterr().out)
    assert exported["schema"] == PORTABLE_EXPORT_SCHEMA
    main(["verify-export", str(output)])
    assert json.loads(capsys.readouterr().out)["valid"] is True

    document = json.loads(output.read_text(encoding="utf-8"))
    document["payload"]["sources"][0]["title"] = "tampered"
    output.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SystemExit, match="export verification failed: payload_hash_mismatch"):
        main(["verify-export", str(output)])
    assert "tampered" not in capsys.readouterr().err

    with pytest.raises(SystemExit, match="export failed: output_exists"):
        main(["export", "--output", str(output)])
