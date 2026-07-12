import copy
import json
from datetime import UTC, datetime

import proofline.cli as cli_module
import proofline.portable_import as import_module
import pytest
from proofline.cli import main
from proofline.database import initialize_database, make_engine
from proofline.ingestion import (
    IngestionRetryConflict,
    delete_source,
    ingest_source,
    retry_ingestion_job,
)
from proofline.models import (
    AuditEvent,
    Chunk,
    ChunkEmbedding,
    Decision,
    Evidence,
    ImportReceipt,
    IngestionJob,
    ModelRun,
    Source,
    SourceVersion,
)
from proofline.portability import (
    PortabilityError,
    atomic_write_export,
    build_portable_export,
    payload_sha256,
)
from proofline.portable_import import import_portable_export, load_verified_import
from proofline.retrieval import lexical_search
from proofline.schemas import SourceCreate
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker


def _rich_document(session):
    source, _ = ingest_source(
        session,
        SourceCreate(
            title="Queue ADR",
            uri="file:///queue.md",
            content="Decision: Use Kafka for throughput\nReason: expected high traffic.",
        ),
    )
    old_version_id = source.current_version_id
    source, _ = ingest_source(
        session,
        SourceCreate(
            title="Queue ADR revised",
            uri="file:///queue.md",
            content="Decision: Use NATS for simplicity\nReason: measured traffic is modest.",
        ),
    )
    memory = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    run = ModelRun(
        provider_id="test-provider",
        model_id="test-model",
        operation="generate",
        template_version="memory-v1",
        input_hashes=[source.content_hash],
        attempt_number=1,
        status="succeeded",
        validation_status="valid",
        created_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    memory.model_run_id = run.id
    memory.extraction_method = "model"
    memory.status = "accepted"
    session.add(
        AuditEvent(
            actor="local_user",
            action="memory.accepted",
            object_type="memory",
            object_id=memory.id,
            before_json={"status": "active"},
            after_json={"status": "accepted"},
        )
    )
    session.add(
        IngestionJob(
            source_id=source.id,
            source_version_id=source.current_version_id,
            kind="source_ingestion",
            state="failed",
            stage="parse",
            attempts=1,
            max_attempts=3,
            error_code="ingestion_error",
            retryable=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    )
    session.commit()
    return build_portable_export(session), source.id, old_version_id, memory.id


def _target_factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'import-target.db'}")
    initialize_database(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_import_round_trip_preserves_provenance_and_rebuilds_only_indexes(session, tmp_path):
    document, source_id, old_version_id, memory_id = _rich_document(session)
    engine, factory = _target_factory(tmp_path)

    with factory() as target, target.begin():
        report = import_portable_export(target, document)

    assert report["payload_sha256"] == document["manifest"]["payload_sha256"]
    assert report["embeddings_rebuilt"] is False
    with factory() as target:
        rebuilt = build_portable_export(target)
        assert rebuilt["payload"] == document["payload"]
        assert target.get(Source, source_id).current_version_id != old_version_id
        assert target.get(SourceVersion, old_version_id) is not None
        assert target.get(Decision, memory_id) is not None
        evidence = target.scalar(select(Evidence).where(Evidence.decision_id == memory_id))
        version = target.get(SourceVersion, evidence.source_version_id)
        assert version.content[evidence.start_offset : evidence.end_offset] == evidence.quote
        assert lexical_search(target, "simplicity")[0].source_id == source_id
        assert target.scalar(select(func.count()).select_from(Chunk)) > 0
        assert target.scalar(select(func.count()).select_from(ChunkEmbedding)) == 0
        receipt = target.scalar(select(ImportReceipt))
        assert receipt.payload_sha256 == document["manifest"]["payload_sha256"]

        imported_job = target.scalar(select(IngestionJob))
        with pytest.raises(IngestionRetryConflict, match="staged ingestion input is unavailable"):
            retry_ingestion_job(target, imported_job.id)
        target.expire_all()
        degraded = target.get(IngestionJob, imported_job.id)
        assert degraded.state == "dead_letter"
        assert degraded.error_code == "ingestion_input_missing"
        assert degraded.retryable is False

        delete_source(target, target.get(Source, source_id))
        assert target.scalar(select(func.count()).select_from(SourceVersion)) == 0
        assert target.scalar(select(func.count()).select_from(Evidence)) == 0
        assert target.scalar(select(func.count()).select_from(Chunk)) == 0
    engine.dispose()


def test_import_rejects_nonempty_target_without_mutation(session, tmp_path):
    document, *_ = _rich_document(session)
    engine, factory = _target_factory(tmp_path)
    with factory() as target:
        existing, _ = ingest_source(
            target, SourceCreate(title="Existing", content="Decision: Keep existing data")
        )
        existing_id = existing.id

    with pytest.raises(PortabilityError, match="target_not_empty"):
        with factory() as target, target.begin():
            import_portable_export(target, document)

    with factory() as target:
        assert target.scalar(select(func.count()).select_from(Source)) == 1
        assert target.get(Source, existing_id) is not None
        assert target.scalar(select(func.count()).select_from(ImportReceipt)) == 0
    engine.dispose()


def test_import_rolls_back_and_hides_internal_failure(session, tmp_path, monkeypatch):
    document, *_ = _rich_document(session)
    engine, factory = _target_factory(tmp_path)

    def fail_without_leaking(*_args, **_kwargs):
        raise RuntimeError("PRIVATE-IMPORT-CONTENT")

    monkeypatch.setattr(import_module, "index_source_version_chunks", fail_without_leaking)
    with pytest.raises(PortabilityError, match="^import_failed$") as raised:
        with factory() as target, target.begin():
            import_portable_export(target, document)
    assert "PRIVATE" not in str(raised.value)

    with factory() as target:
        for model in (Source, SourceVersion, Decision, Evidence, ImportReceipt):
            assert target.scalar(select(func.count()).select_from(model)) == 0
    engine.dispose()


def test_import_owns_savepoint_when_caller_catches_then_commits(session, tmp_path, monkeypatch):
    document, *_ = _rich_document(session)
    engine, factory = _target_factory(tmp_path)
    original_builder = import_module.build_portable_export

    def fail_final_equivalence(target):
        rebuilt = original_builder(target)
        rebuilt["payload"]["sources"][0]["title"] = "changed after import"
        return rebuilt

    monkeypatch.setattr(import_module, "build_portable_export", fail_final_equivalence)
    with factory() as target:
        with pytest.raises(PortabilityError, match="import_verification_failed"):
            import_portable_export(target, document)
        target.commit()

    with factory() as target:
        for model in (Source, SourceVersion, Decision, Evidence, Chunk, ImportReceipt):
            assert target.scalar(select(func.count()).select_from(model)) == 0
        assert target.scalar(text("SELECT count(*) FROM chunk_search")) == 0
    engine.dispose()


def test_empty_import_is_receipted_and_tampering_never_writes(session, tmp_path):
    document = build_portable_export(session)
    path = tmp_path / "portable.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(PortabilityError, match="invalid_structure"):
        load_verified_import(path)

    changed = copy.deepcopy(document)
    changed["payload"]["sources"] = [{"content": "PRIVATE"}]
    changed["manifest"]["payload_sha256"] = payload_sha256(changed["payload"])
    invalid_engine, invalid_factory = _target_factory(tmp_path)
    with invalid_factory() as target, pytest.raises(PortabilityError):
        import_portable_export(target, changed)
    invalid_engine.dispose()

    engine = make_engine(f"sqlite:///{tmp_path / 'empty-target.db'}")
    initialize_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as target, target.begin():
        report = import_portable_export(target, document)
    assert report["counts"] == document["manifest"]["counts"]
    with factory() as target:
        assert target.scalar(select(func.count()).select_from(Source)) == 0
        assert target.scalar(select(func.count()).select_from(ImportReceipt)) == 1
    engine.dispose()


def test_import_cli_reports_safe_receipt_and_rejects_second_import(
    session, tmp_path, monkeypatch, capsys
):
    document, *_ = _rich_document(session)
    export_path = tmp_path / "portable.json"
    atomic_write_export(export_path, document)
    engine, factory = _target_factory(tmp_path)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    monkeypatch.setattr(cli_module, "initialize_database", lambda: None)

    main(["import", str(export_path)])
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert report["payload_sha256"] == document["manifest"]["payload_sha256"]
    assert "content" not in report

    with pytest.raises(SystemExit, match="import failed: target_not_empty"):
        main(["import", str(export_path)])
    engine.dispose()


def test_supported_ingestion_state_always_exports_verifies_and_imports(session, tmp_path):
    source, _ = ingest_source(
        session,
        SourceCreate(
            title="Boundary contract",
            content="Decision: Review the queue choice\nStatus: pending",
            uri="x" * 4_096,
        ),
    )
    assert source.decisions[0].status == "candidate"
    document = build_portable_export(session)
    engine, factory = _target_factory(tmp_path)

    with factory() as target, target.begin():
        import_portable_export(target, document)
    with factory() as target:
        imported = target.get(Source, source.id)
        assert imported.uri == source.uri
        assert imported.decisions[0].status == "candidate"
    engine.dispose()
