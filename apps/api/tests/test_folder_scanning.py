import os

import proofline.folder_scanning as folder_scanning
import pytest
from proofline.config import get_settings
from proofline.ingestion import IngestionConflict
from proofline.models import Chunk, Evidence, IngestionJob, Source, SourceVersion
from sqlalchemy import func, select


def register_roots(monkeypatch, *roots):
    monkeypatch.setenv("PROOFLINE_IMPORT_ROOTS", os.pathsep.join(str(root) for root in roots))


def test_import_roots_are_path_separated_resolved_and_deduplicated(monkeypatch, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(tmp_path)
    register_roots(monkeypatch, "first", second, first)

    assert get_settings().import_roots == (first.resolve(), second.resolve())


def test_folder_scan_requires_a_registered_root(client, monkeypatch):
    monkeypatch.delenv("PROOFLINE_IMPORT_ROOTS", raising=False)

    response = client.post("/api/v1/folder-scans", json={})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "import_roots_disabled"


def test_folder_scan_rejects_traversal_and_symlink_escape(client, monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("Decision: Never import this", encoding="utf-8")
    register_roots(monkeypatch, root)

    traversal = client.post("/api/v1/folder-scans", json={"path": "../outside"})
    assert traversal.status_code == 422
    assert traversal.json()["detail"]["code"] == "scan_path_escape"

    linked_directory = root / "linked"
    linked_file = root / "escape.md"
    try:
        linked_directory.symlink_to(outside, target_is_directory=True)
        linked_file.symlink_to(outside / "secret.md")
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    escaped_path = client.post("/api/v1/folder-scans", json={"path": "linked"})
    assert escaped_path.status_code == 422
    assert escaped_path.json()["detail"]["code"] == "scan_path_escape"

    report = client.post("/api/v1/folder-scans", json={}).json()
    assert report["created_count"] == 0
    assert report["failed_count"] == 1
    assert report["files"][0]["relative_path"] == "escape.md"
    assert report["files"][0]["error_code"] == "file_symlink_escape"
    assert client.get("/api/v1/sources").json() == []


def test_folder_scan_creates_skips_and_versions_unicode_source(client, monkeypatch, tmp_path):
    root = tmp_path / "vault"
    nested = root / "kiến-trúc"
    nested.mkdir(parents=True)
    source_path = nested / "quyết-định-🧠.md"
    first_content = "# ADR\n\nQuyết định: Dùng SQLite\nLý do: 本地运行 đơn giản."
    source_path.write_text(first_content, encoding="utf-8")
    register_roots(monkeypatch, root)

    first = client.post("/api/v1/folder-scans", json={}).json()
    assert first["created_count"] == 1
    assert first["failed_count"] == 0
    assert first["files"][0]["relative_path"] == "kiến-trúc/quyết-định-🧠.md"
    assert first["files"][0]["uri"] == source_path.resolve().as_uri()
    source_id = first["files"][0]["source_id"]
    first_version_id = first["files"][0]["source_version_id"]
    first_job_id = first["files"][0]["job_id"]
    assert client.get(f"/api/v1/sources/{source_id}").json()["content"] == first_content

    unchanged = client.post("/api/v1/folder-scans", json={}).json()
    assert unchanged["unchanged_count"] == 1
    assert unchanged["files"][0]["source_version_id"] == first_version_id
    assert unchanged["files"][0]["job_id"] is None
    assert [job["id"] for job in client.get("/api/v1/jobs").json()] == [first_job_id]
    assert len(client.get(f"/api/v1/sources/{source_id}/versions").json()) == 1

    second_content = "# ADR\n\nQuyết định: Dùng DuckDB\nLý do: hỗ trợ phân tích local."
    source_path.write_text(second_content, encoding="utf-8")
    updated = client.post("/api/v1/folder-scans", json={}).json()
    assert updated["updated_count"] == 1
    assert updated["files"][0]["source_id"] == source_id
    assert updated["files"][0]["source_version_id"] != first_version_id
    assert len(client.get(f"/api/v1/sources/{source_id}/versions").json()) == 2
    assert client.get("/api/v1/search", params={"q": "SQLite"}).json()["hits"] == []
    assert client.get("/api/v1/search", params={"q": "DuckDB"}).json()["hits"]


def test_folder_scan_rejects_file_changed_during_read_then_retries_cleanly(
    client, session, monkeypatch, tmp_path
):
    root = tmp_path / "vault"
    root.mkdir()
    source_path = root / "partial.md"
    original = "Decision: Keep immutable evidence\nReason: stable input"
    replacement = "Decision: Retry stable evidence\nReason: complete write"
    source_path.write_text(original, encoding="utf-8")
    register_roots(monkeypatch, root)
    created = client.post("/api/v1/folder-scans", json={}).json()
    source_id = created["files"][0]["source_id"]
    version_id = created["files"][0]["source_version_id"]
    job_count = session.scalar(select(func.count()).select_from(IngestionJob))
    version_count = session.scalar(select(func.count()).select_from(SourceVersion))
    evidence_before = list(
        session.scalars(select(Evidence).where(Evidence.source_id == source_id)).all()
    )

    real_read_bytes = folder_scanning.Path.read_bytes
    mutated = False

    def mutate_after_read(path):
        nonlocal mutated
        content = real_read_bytes(path)
        if path == source_path.resolve() and not mutated:
            mutated = True
            source_path.write_text(replacement, encoding="utf-8")
        return content

    monkeypatch.setattr(folder_scanning.Path, "read_bytes", mutate_after_read)
    failed = client.post("/api/v1/folder-scans", json={}).json()

    assert failed["failed_count"] == 1
    assert failed["files"][0]["error_code"] == "file_changed_during_read"
    assert failed["files"][0]["job_id"] is None
    assert session.scalar(select(func.count()).select_from(IngestionJob)) == job_count
    assert session.scalar(select(func.count()).select_from(SourceVersion)) == version_count
    session.expire_all()
    source = session.get(Source, source_id)
    assert source.current_version_id == version_id
    assert source.content == original
    evidence_after_failure = list(
        session.scalars(select(Evidence).where(Evidence.source_id == source_id)).all()
    )
    assert [item.id for item in evidence_after_failure] == [item.id for item in evidence_before]
    assert all(item.source_version_id == version_id for item in evidence_after_failure)

    monkeypatch.setattr(folder_scanning.Path, "read_bytes", real_read_bytes)
    retried = client.post("/api/v1/folder-scans", json={}).json()

    assert retried["updated_count"] == 1
    assert retried["failed_count"] == 0
    assert retried["files"][0]["source_id"] == source_id
    assert retried["files"][0]["source_version_id"] != version_id
    assert retried["files"][0]["job_id"] is not None
    assert client.get(f"/api/v1/sources/{source_id}").json()["content"] == replacement


def test_folder_scan_rename_preserves_source_identity_history_and_evidence(
    client, session, monkeypatch, tmp_path
):
    root = tmp_path / "vault"
    root.mkdir()
    old_path = root / "old-name.md"
    old_path.write_text("Decision: Use Kafka\nReason: initial throughput", encoding="utf-8")
    register_roots(monkeypatch, root)
    first = client.post("/api/v1/folder-scans", json={}).json()
    source_id = first["files"][0]["source_id"]

    old_path.write_text(
        "Decision: Use NATS\nReason: operational simplicity",
        encoding="utf-8",
    )
    updated = client.post("/api/v1/folder-scans", json={}).json()
    current_version_id = updated["files"][0]["source_version_id"]
    previous_uri = old_path.resolve().as_uri()
    before = session.get(Source, source_id)
    indexed_at_before_rename = before.indexed_at
    chunks_before = session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.source_id == source_id)
    )
    evidence_before = session.scalar(
        select(func.count()).select_from(Evidence).where(Evidence.source_id == source_id)
    )
    jobs_before = session.scalar(select(func.count()).select_from(IngestionJob))

    new_path = root / "renamed-architecture.txt"
    old_path.rename(new_path)
    report = client.post("/api/v1/folder-scans", json={}).json()

    assert report["created_count"] == 0
    assert report["updated_count"] == 0
    assert report["renamed_count"] == 1
    assert report["missing_count"] == 0
    result = report["files"][0]
    assert result["status"] == "renamed"
    assert result["source_id"] == source_id
    assert result["source_version_id"] == current_version_id
    assert result["uri"] == new_path.resolve().as_uri()
    assert result["previous_uri"] == previous_uri
    assert result["job_id"] is None

    source = client.get(f"/api/v1/sources/{source_id}").json()
    assert source["title"] == "renamed-architecture.txt"
    assert source["kind"] == "text"
    assert source["uri"] == new_path.resolve().as_uri()
    assert source["current_version_id"] == current_version_id
    assert len(client.get(f"/api/v1/sources/{source_id}/versions").json()) == 2
    session.expire_all()
    persisted = session.get(Source, source_id)
    assert persisted.indexed_at > indexed_at_before_rename
    assert (
        session.scalar(select(func.count()).select_from(Chunk).where(Chunk.source_id == source_id))
        == chunks_before
    )
    assert (
        session.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.source_id == source_id)
        )
        == evidence_before
    )
    assert session.scalar(select(func.count()).select_from(IngestionJob)) == jobs_before
    hits = client.get("/api/v1/search", params={"q": "operational simplicity"}).json()["hits"]
    assert hits[0]["source_id"] == source_id
    assert hits[0]["source_title"] == "renamed-architecture.txt"
    audit = client.get(
        "/api/v1/audit-events",
        params={"object_type": "source", "object_id": source_id},
    ).json()
    assert len(audit) == 1
    assert audit[0]["action"] == "source.renamed"
    assert audit[0]["before_json"] == {
        "uri": previous_uri,
        "title": "old-name.md",
        "kind": "markdown",
        "current_version_id": current_version_id,
    }
    assert audit[0]["after_json"] == {
        "uri": new_path.resolve().as_uri(),
        "title": "renamed-architecture.txt",
        "kind": "text",
        "current_version_id": current_version_id,
    }
    impact = client.get(f"/api/v1/sources/{source_id}/deletion-impact").json()
    assert impact["audit_events_to_delete"] == 1
    assert client.delete(f"/api/v1/sources/{source_id}").status_code == 204
    assert (
        client.get(
            "/api/v1/audit-events",
            params={"object_type": "source", "object_id": source_id},
        ).json()
        == []
    )


def test_folder_scan_does_not_guess_ambiguous_identical_renames(client, monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    content = "Decision: Keep identical content distinct"
    first_path = root / "first.md"
    second_path = root / "second.md"
    first_path.write_text(content, encoding="utf-8")
    second_path.write_text(content, encoding="utf-8")
    register_roots(monkeypatch, root)
    first_scan = client.post("/api/v1/folder-scans", json={}).json()
    original_ids = {item["source_id"] for item in first_scan["files"]}
    assert len(original_ids) == 2

    first_path.unlink()
    second_path.unlink()
    replacement = root / "replacement.md"
    replacement.write_text(content, encoding="utf-8")
    report = client.post("/api/v1/folder-scans", json={}).json()

    assert report["renamed_count"] == 0
    assert report["created_count"] == 1
    assert report["missing_count"] == 2
    assert set(report["missing_source_ids"]) == original_ids
    assert report["files"][0]["status"] == "created"
    assert report["files"][0]["previous_uri"] is None
    assert report["files"][0]["source_id"] not in original_ids
    assert len(client.get("/api/v1/sources").json()) == 3


def test_folder_scan_does_not_choose_between_two_identical_new_paths(client, monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    content = "Decision: Avoid guessing a rename target"
    original = root / "original.md"
    original.write_text(content, encoding="utf-8")
    register_roots(monkeypatch, root)
    original_scan = client.post("/api/v1/folder-scans", json={}).json()
    original_id = original_scan["files"][0]["source_id"]

    original.unlink()
    (root / "candidate-a.md").write_text(content, encoding="utf-8")
    (root / "candidate-b.md").write_text(content, encoding="utf-8")
    report = client.post("/api/v1/folder-scans", json={}).json()

    assert report["renamed_count"] == 0
    assert report["created_count"] == 2
    assert report["missing_source_ids"] == [original_id]
    assert all(item["status"] == "created" for item in report["files"])
    assert all(item["previous_uri"] is None for item in report["files"])
    assert len(client.get("/api/v1/sources").json()) == 3


def test_folder_scan_continues_after_safe_per_file_failures(client, monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "good.md").write_text("Decision: ok", encoding="utf-8")
    (root / "invalid.txt").write_bytes(b"\xff\xfe")
    (root / "oversized.markdown").write_text("x" * 33, encoding="utf-8")
    register_roots(monkeypatch, root)
    monkeypatch.setattr(folder_scanning, "MAX_IMPORT_BYTES", 32)

    report = client.post("/api/v1/folder-scans", json={}).json()

    assert report["discovered_count"] == 3
    assert report["created_count"] == 1
    assert report["failed_count"] == 2
    assert {item["error_code"] for item in report["files"] if item["status"] == "failed"} == {
        "file_encoding_invalid",
        "file_too_large",
    }
    assert [source["title"] for source in client.get("/api/v1/sources").json()] == ["good.md"]
    jobs = client.get("/api/v1/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["state"] == "succeeded"
    assert all("Decision: ok" not in str(item) for item in report["files"])


def test_folder_scan_reports_persisted_identity_conflict_job(client, monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "conflict.md").write_text("Decision: Keep identity", encoding="utf-8")
    register_roots(monkeypatch, root)

    def conflict(*_args, **_kwargs):
        raise IngestionConflict("safe identity conflict", job_id="conflict-job")

    monkeypatch.setattr(folder_scanning, "run_ingestion_job", conflict)
    report = client.post("/api/v1/folder-scans", json={}).json()

    assert report["failed_count"] == 1
    assert report["files"][0]["error_code"] == "source_identity_conflict"
    assert report["files"][0]["job_id"] == "conflict-job"


def test_folder_scan_only_previews_missing_sources(client, monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    source_path = root / "removed.md"
    source_path.write_text("Decision: Preserve history", encoding="utf-8")
    register_roots(monkeypatch, root)
    created = client.post("/api/v1/folder-scans", json={}).json()
    source_id = created["files"][0]["source_id"]
    malformed = client.post(
        "/api/v1/sources",
        json={
            "title": "Malformed legacy URI",
            "uri": "file:///%00",
            "content": "Decision: Ignore malformed URI during missing preview",
        },
    )
    assert malformed.status_code == 201
    source_path.unlink()

    report = client.post(
        "/api/v1/folder-scans",
        json={"delete_missing": True},
    ).json()

    assert report["delete_missing_requested"] is True
    assert report["deletion_mode"] == "preview_only"
    assert report["deleted_count"] == 0
    assert report["missing_count"] == 1
    assert report["missing_source_ids"] == [source_id]
    assert client.get(f"/api/v1/sources/{source_id}").status_code == 200
    assert client.get("/api/v1/search", params={"q": "Preserve history"}).json()["hits"]


def test_folder_scan_exact_confirmation_deletes_with_complete_cascade(
    client, session, monkeypatch, tmp_path
):
    root = tmp_path / "vault"
    root.mkdir()
    source_path = root / "removed.md"
    source_path.write_text(
        "Decision: Preserve exact deletion evidence\nReason: local ownership.",
        encoding="utf-8",
    )
    register_roots(monkeypatch, root)
    created = client.post("/api/v1/folder-scans", json={}).json()
    source_id = created["files"][0]["source_id"]
    job_id = created["files"][0]["job_id"]
    memory = client.get("/api/v1/memories").json()[0]
    assert (
        client.patch(f"/api/v1/memories/{memory['id']}", json={"status": "accepted"}).status_code
        == 200
    )
    source_path.unlink()

    preview = client.post("/api/v1/folder-scans", json={}).json()
    confirmed = client.post(
        "/api/v1/folder-scans",
        json={
            "delete_missing": True,
            "confirmed_missing_source_ids": preview["missing_source_ids"],
        },
    )

    assert confirmed.status_code == 200
    report = confirmed.json()
    assert report["deletion_mode"] == "confirmed_delete"
    assert report["deleted_count"] == 1
    assert report["missing_source_ids"] == [source_id]
    assert client.get(f"/api/v1/sources/{source_id}").status_code == 404
    assert (
        client.get("/api/v1/search", params={"q": "exact deletion evidence"}).json()["hits"] == []
    )
    assert (
        session.scalar(select(func.count()).select_from(Chunk).where(Chunk.source_id == source_id))
        == 0
    )
    assert (
        session.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.source_id == source_id)
        )
        == 0
    )
    assert (
        client.get(
            "/api/v1/audit-events", params={"object_type": "memory", "object_id": memory["id"]}
        ).json()
        == []
    )
    job = session.get(IngestionJob, job_id)
    assert job.source_id is None
    assert job.source_version_id is None


def test_folder_scan_confirmation_fails_closed_when_missing_set_changes(
    client, monkeypatch, tmp_path
):
    root = tmp_path / "vault"
    root.mkdir()
    first = root / "first.md"
    second = root / "second.md"
    first.write_text("Decision: Keep first source", encoding="utf-8")
    second.write_text("Decision: Keep second source", encoding="utf-8")
    register_roots(monkeypatch, root)
    created = client.post("/api/v1/folder-scans", json={}).json()
    source_ids = {item["relative_path"]: item["source_id"] for item in created["files"]}
    first.unlink()
    preview = client.post("/api/v1/folder-scans", json={}).json()
    assert preview["missing_source_ids"] == [source_ids["first.md"]]
    second.unlink()

    stale = client.post(
        "/api/v1/folder-scans",
        json={
            "delete_missing": True,
            "confirmed_missing_source_ids": preview["missing_source_ids"],
        },
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "missing_confirmation_mismatch"
    assert all(
        client.get(f"/api/v1/sources/{source_id}").status_code == 200
        for source_id in source_ids.values()
    )


def test_folder_scan_rejects_unowned_malformed_or_unrequested_confirmation(
    client, monkeypatch, tmp_path
):
    root = tmp_path / "vault"
    root.mkdir()
    register_roots(monkeypatch, root)
    outside = tmp_path / "outside.md"
    outside_source = client.post(
        "/api/v1/sources",
        json={
            "title": "Outside",
            "uri": outside.resolve().as_uri(),
            "content": "Decision: Remain outside the registered scan",
        },
    ).json()

    without_delete = client.post(
        "/api/v1/folder-scans",
        json={"confirmed_missing_source_ids": []},
    )
    duplicate = client.post(
        "/api/v1/folder-scans",
        json={
            "delete_missing": True,
            "confirmed_missing_source_ids": [outside_source["id"], outside_source["id"]],
        },
    )
    empty = client.post(
        "/api/v1/folder-scans",
        json={"delete_missing": True, "confirmed_missing_source_ids": []},
    )
    unowned = client.post(
        "/api/v1/folder-scans",
        json={
            "delete_missing": True,
            "confirmed_missing_source_ids": [outside_source["id"]],
        },
    )

    assert without_delete.status_code == 422
    assert without_delete.json()["detail"]["code"] == "missing_confirmation_without_delete"
    assert duplicate.status_code == 422
    assert duplicate.json()["detail"]["code"] == "missing_confirmation_invalid"
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "missing_confirmation_invalid"
    assert unowned.status_code == 422
    assert unowned.json()["detail"]["code"] == "missing_confirmation_invalid"
    assert client.get(f"/api/v1/sources/{outside_source['id']}").status_code == 200


def test_folder_scan_confirmation_fails_closed_on_scan_error(client, monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    removed = root / "removed.md"
    removed.write_text("Decision: Preserve source when another file fails", encoding="utf-8")
    register_roots(monkeypatch, root)
    created = client.post("/api/v1/folder-scans", json={}).json()
    source_id = created["files"][0]["source_id"]
    removed.unlink()
    preview = client.post("/api/v1/folder-scans", json={}).json()
    (root / "invalid.md").write_bytes(b"\xff\xfe")

    response = client.post(
        "/api/v1/folder-scans",
        json={
            "delete_missing": True,
            "confirmed_missing_source_ids": preview["missing_source_ids"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "missing_deletion_scan_failed"
    assert client.get(f"/api/v1/sources/{source_id}").status_code == 200
