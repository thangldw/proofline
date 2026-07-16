import copy
import json
import stat
import struct
import zipfile
from datetime import UTC, datetime

import proofline.cli as cli_module
import proofline.evidence_packages as evidence_package_module
import proofline.portability as portability_module
import pytest
from proofline.cli import main
from proofline.database import initialize_database, make_engine
from proofline.evidence_packages import (
    DECISION_PACKAGE_SCHEMA,
    EvidencePackageError,
    atomic_write_package,
    build_decision_package,
    diff_decision_packages,
    explain_decision_package,
    load_and_verify_package,
    verify_decision_package,
)
from proofline.ingestion import ingest_source
from proofline.models import Decision, ModelRun, SourceVersion, Workspace
from proofline.portability import build_portable_export
from proofline.portable_import import import_portable_export
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _seed_decision(session):
    source, _created = ingest_source(
        session,
        SourceCreate(
            title="Queue ADR",
            uri="file:///queue.md",
            content="Decision: Use SQLite for the local queue.\nReason: no service dependency.",
        ),
    )
    decision = session.scalar(
        select(Decision).where(
            Decision.source_version_id == source.current_version_id,
            Decision.kind == "decision",
        )
    )
    assert decision is not None
    return source, decision


def test_decision_package_is_deterministic_verifiable_and_explainable(session):
    source, decision = _seed_decision(session)

    first = build_decision_package(
        session, decision.id, created_at=datetime(2026, 7, 16, tzinfo=UTC)
    )
    second = build_decision_package(
        session, decision.id, created_at=datetime(2026, 7, 17, tzinfo=UTC)
    )

    assert first["manifest"]["schema"] == DECISION_PACKAGE_SCHEMA
    assert first["manifest"]["created_at"] != second["manifest"]["created_at"]
    assert first["manifest"]["root_hash"] == second["manifest"]["root_hash"]
    assert first["payload"] == second["payload"]
    report = verify_decision_package(first)
    assert report == {
        "valid": True,
        "schema": DECISION_PACKAGE_SCHEMA,
        "root_hash": first["manifest"]["root_hash"],
        "artifact_id": decision.id,
        "citation_count": 1,
    }
    explanation = explain_decision_package(first)
    assert explanation["source"]["source_id"] == source.id
    assert explanation["citations"][0]["quote"] == decision.evidence[0].quote
    assert "content" not in explanation["source"]
    assert explanation["chunks"]
    assert "content" not in explanation["chunks"][0]


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda package: package["payload"]["source_version"].__setitem__(
                "content", package["payload"]["source_version"]["content"] + " drift"
            ),
            "source_content_invalid",
        ),
        (
            lambda package: package["payload"]["citations"][0].__setitem__("start_offset", 1),
            "citation_span_invalid",
        ),
        (
            lambda package: package["payload"]["chunks"][0].__setitem__(
                "content", "tampered chunk"
            ),
            "chunk_span_invalid",
        ),
        (
            lambda package: package["payload"]["artifact"].__setitem__(
                "statement", "tampered statement"
            ),
            "artifact_node_hash_mismatch",
        ),
        (
            lambda package: package["payload"]["review"].__setitem__("status", "accepted"),
            "review_node_hash_mismatch",
        ),
    ],
)
def test_decision_package_rejects_tampering_without_exposing_content(
    session, mutate, expected_code
):
    _source, decision = _seed_decision(session)
    package = copy.deepcopy(build_decision_package(session, decision.id))
    mutate(package)

    with pytest.raises(EvidencePackageError) as raised:
        verify_decision_package(package)

    assert raised.value.code == expected_code
    assert "SQLite" not in str(raised.value)


def test_old_package_and_artifact_stay_bound_to_old_source_version_after_reingestion(session):
    source, decision = _seed_decision(session)
    old_version_id = decision.source_version_id
    original = build_decision_package(session, decision.id)

    updated, created = ingest_source(
        session,
        SourceCreate(
            title="Queue ADR revised",
            uri=source.uri,
            content="Decision: Use NATS for the local queue.\nReason: requirements changed.",
        ),
    )

    assert created is False
    assert updated.current_version_id != old_version_id
    assert session.get(SourceVersion, old_version_id) is not None
    rebuilt_old = build_decision_package(session, decision.id)
    assert rebuilt_old["manifest"]["root_hash"] == original["manifest"]["root_hash"]
    assert verify_decision_package(original)["valid"] is True


def test_portable_export_import_preserves_decision_package_root(session, tmp_path):
    _source, decision = _seed_decision(session)
    expected_root = build_decision_package(session, decision.id)["manifest"]["root_hash"]
    portable = build_portable_export(session)
    engine = make_engine(f"sqlite:///{tmp_path / 'package-round-trip.db'}")
    initialize_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as target, target.begin():
        import_portable_export(target, portable)
    with factory() as target:
        actual_root = build_decision_package(target, decision.id)["manifest"]["root_hash"]

    assert actual_root == expected_root
    engine.dispose()


def test_review_state_changes_package_root_but_not_artifact_identity(session):
    _source, decision = _seed_decision(session)
    before = build_decision_package(session, decision.id)
    artifact_hash = before["payload"]["artifact"]["node_hash"]

    decision.status = "accepted"
    session.commit()
    after = build_decision_package(session, decision.id)

    assert after["payload"]["artifact"]["node_hash"] == artifact_hash
    assert after["payload"]["review"]["node_hash"] != before["payload"]["review"]["node_hash"]
    assert after["manifest"]["root_hash"] != before["manifest"]["root_hash"]


def test_package_builder_rejects_cross_workspace_model_lineage(session):
    _source, decision = _seed_decision(session)
    other = Workspace(slug="other", title="Other workspace")
    session.add(other)
    session.flush()
    run = ModelRun(
        workspace_id=other.id,
        provider_id="test-provider",
        model_id="test-model",
        operation="generate",
        template_version="memory-v1",
        input_hashes=["a" * 64],
        status="succeeded",
        validation_status="valid",
    )
    session.add(run)
    session.flush()
    decision.extraction_method = "model"
    decision.model_run_id = run.id
    session.commit()

    with pytest.raises(EvidencePackageError, match="model_run_lineage_invalid"):
        build_decision_package(session, decision.id)


def test_package_verifier_normalizes_malformed_nonfinite_values(session):
    _source, decision = _seed_decision(session)
    package = build_decision_package(session, decision.id)
    package["payload"]["artifact"]["confidence"] = float("nan")

    with pytest.raises(EvidencePackageError) as raised:
        verify_decision_package(package)

    assert raised.value.code == "artifact_content_invalid"


def test_package_diff_is_verified_semantic_and_content_free(session):
    _source, decision = _seed_decision(session)
    before = build_decision_package(session, decision.id)
    unchanged = diff_decision_packages(before, copy.deepcopy(before))
    assert unchanged["same_root"] is True
    assert unchanged["artifact_changed_fields"] == []
    assert unchanged["review_changed_fields"] == []

    decision.statement = "Use SQLite with a bounded local queue"
    decision.status = "accepted"
    session.commit()
    after = build_decision_package(session, decision.id)
    changed = diff_decision_packages(before, after)

    assert changed["same_root"] is False
    assert changed["same_artifact_id"] is True
    assert changed["artifact_changed_fields"] == ["statement"]
    assert changed["review_changed_fields"] == ["status"]
    assert changed["source_changed_fields"] == []
    assert changed["chunks_added"] == []
    assert changed["chunks_removed"] == []
    assert changed["citations_added"] == []
    assert changed["citations_removed"] == []
    assert "SQLite" not in json.dumps(changed)


def test_package_diff_cli_verifies_both_inputs(session, tmp_path, monkeypatch, capsys):
    _source, decision = _seed_decision(session)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    monkeypatch.setattr(cli_module, "initialize_database", lambda: None)
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    atomic_write_package(before_path, build_decision_package(session, decision.id))
    decision.status = "accepted"
    session.commit()
    atomic_write_package(after_path, build_decision_package(session, decision.id))

    main(["diff", str(before_path), str(after_path)])
    report = json.loads(capsys.readouterr().out)
    assert report["same_root"] is False
    assert report["review_changed_fields"] == ["status"]

    tampered = json.loads(after_path.read_text(encoding="utf-8"))
    tampered["payload"]["review"]["status"] = "rejected"
    after_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(SystemExit, match="package diff failed: review_node_hash_mismatch"):
        main(["diff", str(before_path), str(after_path)])


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_package_publish_failure_cleans_temporary_state(session, tmp_path, monkeypatch, operation):
    _source, decision = _seed_decision(session)
    package = build_decision_package(session, decision.id)
    output = tmp_path / "evidence.json"

    def fail(*_args, **_kwargs):
        raise OSError("private publish failure")

    monkeypatch.setattr(portability_module.os, operation, fail)
    with pytest.raises(EvidencePackageError, match="package_publish_failed") as raised:
        atomic_write_package(output, package)

    assert "private" not in str(raised.value)
    assert not output.exists()
    assert not list(tmp_path.glob(".evidence.json.*"))


def test_forced_package_replace_failure_preserves_existing_output(session, tmp_path, monkeypatch):
    _source, decision = _seed_decision(session)
    package = build_decision_package(session, decision.id)
    output = tmp_path / "evidence.json"
    output.write_bytes(b"existing-valid-sentinel")

    def fail(*_args, **_kwargs):
        raise OSError("private replace failure")

    monkeypatch.setattr(portability_module.os, "replace", fail)
    with pytest.raises(EvidencePackageError, match="package_publish_failed"):
        atomic_write_package(output, package, force=True)

    assert output.read_bytes() == b"existing-valid-sentinel"
    assert not list(tmp_path.glob(".evidence.json.*"))


def test_package_cli_exports_verifies_explains_and_fails_closed(
    session, tmp_path, monkeypatch, capsys
):
    _source, decision = _seed_decision(session)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    monkeypatch.setattr(cli_module, "initialize_database", lambda: None)
    output = tmp_path / "decision-evidence.json"

    main(["export-package", decision.id, "--output", str(output)])
    exported = json.loads(capsys.readouterr().out)
    assert exported["schema"] == DECISION_PACKAGE_SCHEMA
    main(["verify-package", str(output)])
    assert json.loads(capsys.readouterr().out)["valid"] is True
    main(["explain", decision.id])
    explained = json.loads(capsys.readouterr().out)
    assert explained["artifact_id"] == decision.id
    assert explained["source"]["source_version_id"] == decision.source_version_id

    tampered = json.loads(output.read_text(encoding="utf-8"))
    tampered["payload"]["citations"][0]["quote"] = "PRIVATE TAMPERED CONTENT"
    output.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(SystemExit, match="package verification failed: citation_span_invalid"):
        main(["verify-package", str(output)])
    assert "PRIVATE" not in capsys.readouterr().err

    with pytest.raises(SystemExit, match="artifact explanation failed: artifact_not_found"):
        main(["explain", "00000000-0000-0000-0000-000000000000"])


def test_package_loader_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"manifest":{},"manifest":{},"payload":{}}', encoding="utf-8")

    with pytest.raises(EvidencePackageError, match="duplicate_json_key"):
        load_and_verify_package(path)


def _write_test_archive(
    path, entries: list[tuple[str, bytes]], *, compression: int = zipfile.ZIP_STORED
):
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, content in entries:
            archive.writestr(name, content)


def test_zip_package_is_deterministic_private_and_verifiable(session, tmp_path):
    _source, decision = _seed_decision(session)
    package = build_decision_package(
        session, decision.id, created_at=datetime(2026, 7, 16, tzinfo=UTC)
    )
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    atomic_write_package(first, package)
    atomic_write_package(second, package)

    assert first.read_bytes() == second.read_bytes()
    assert stat.S_IMODE(first.stat().st_mode) == 0o600
    document, report = load_and_verify_package(first)
    assert document == package
    assert report["root_hash"] == package["manifest"]["root_hash"]


@pytest.mark.parametrize(
    ("entries", "compression", "expected_code"),
    [
        (
            [("../evidence.json", b"{}")],
            zipfile.ZIP_STORED,
            "archive_entry_invalid",
        ),
        (
            [("evidence.json", b"{}"), ("extra.json", b"{}")],
            zipfile.ZIP_STORED,
            "archive_entry_count_invalid",
        ),
        (
            [("evidence.json", b"{}")],
            zipfile.ZIP_DEFLATED,
            "archive_compression_unsupported",
        ),
    ],
)
def test_zip_package_rejects_unsafe_archive_shapes(tmp_path, entries, compression, expected_code):
    path = tmp_path / "unsafe.zip"
    _write_test_archive(path, entries, compression=compression)

    with pytest.raises(EvidencePackageError, match=expected_code):
        load_and_verify_package(path)


def test_zip_package_rejects_symlink_encryption_and_oversized_metadata(tmp_path):
    symlink_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("evidence.json")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink_path, "w") as archive:
        archive.writestr(info, b"target")
    with pytest.raises(EvidencePackageError, match="archive_entry_invalid"):
        load_and_verify_package(symlink_path)

    encrypted_path = tmp_path / "encrypted.zip"
    _write_test_archive(encrypted_path, [("evidence.json", b"{}")])
    encrypted = bytearray(encrypted_path.read_bytes())
    struct.pack_into("<H", encrypted, 6, struct.unpack_from("<H", encrypted, 6)[0] | 0x1)
    central = encrypted.index(b"PK\x01\x02")
    struct.pack_into(
        "<H", encrypted, central + 8, struct.unpack_from("<H", encrypted, central + 8)[0] | 0x1
    )
    encrypted_path.write_bytes(encrypted)
    with pytest.raises(EvidencePackageError, match="archive_encrypted"):
        load_and_verify_package(encrypted_path)

    oversized_path = tmp_path / "oversized.zip"
    _write_test_archive(oversized_path, [("evidence.json", b"{}")])
    oversized = bytearray(oversized_path.read_bytes())
    central = oversized.index(b"PK\x01\x02")
    struct.pack_into("<I", oversized, central + 24, evidence_package_module.MAX_PACKAGE_BYTES + 1)
    oversized_path.write_bytes(oversized)
    with pytest.raises(EvidencePackageError, match="archive_entry_too_large"):
        load_and_verify_package(oversized_path)


def test_zip_package_publish_failure_cleans_temporary_state(session, tmp_path, monkeypatch):
    _source, decision = _seed_decision(session)
    output = tmp_path / "evidence.zip"

    def fail(*_args, **_kwargs):
        raise OSError("private zip publish failure")

    monkeypatch.setattr(evidence_package_module.os, "link", fail)
    with pytest.raises(EvidencePackageError, match="package_publish_failed"):
        atomic_write_package(output, build_decision_package(session, decision.id))

    assert not output.exists()
    assert not list(tmp_path.glob(".evidence.zip.*"))


@pytest.mark.parametrize(
    ("suffix", "writer_module"),
    [(".json", portability_module), (".zip", evidence_package_module)],
)
def test_package_permission_fault_closes_descriptor_and_cleans_temporary_state(
    session, tmp_path, monkeypatch, suffix, writer_module
):
    _source, decision = _seed_decision(session)
    output = tmp_path / f"evidence{suffix}"
    closed_descriptors = []
    original_close = writer_module.os.close

    def fail_permission(*_args, **_kwargs):
        raise OSError("private permission fault")

    def record_close(descriptor):
        closed_descriptors.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(writer_module.os, "fchmod", fail_permission)
    monkeypatch.setattr(writer_module.os, "close", record_close)

    with pytest.raises(EvidencePackageError, match="package_publish_failed"):
        atomic_write_package(output, build_decision_package(session, decision.id))

    assert len(closed_descriptors) == 1
    assert not output.exists()
    assert not list(tmp_path.glob(f".{output.name}.*"))


def test_package_cli_round_trips_zip_and_diffs_mixed_containers(
    session, tmp_path, monkeypatch, capsys
):
    _source, decision = _seed_decision(session)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    monkeypatch.setattr(cli_module, "initialize_database", lambda: None)
    before = tmp_path / "before.zip"
    after = tmp_path / "after.json"

    main(["export-package", decision.id, "--output", str(before)])
    capsys.readouterr()
    main(["verify-package", str(before)])
    assert json.loads(capsys.readouterr().out)["valid"] is True
    decision.status = "accepted"
    session.commit()
    atomic_write_package(after, build_decision_package(session, decision.id))
    main(["diff", str(before), str(after)])
    assert json.loads(capsys.readouterr().out)["review_changed_fields"] == ["status"]
