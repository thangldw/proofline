import os

import proofline.folder_scanning as folder_scanning
import pytest
from proofline.config import get_settings
from proofline.ingestion import IngestionConflict


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
    assert client.get(f"/api/v1/sources/{source_id}").json()["content"] == first_content

    unchanged = client.post("/api/v1/folder-scans", json={}).json()
    assert unchanged["unchanged_count"] == 1
    assert unchanged["files"][0]["source_version_id"] == first_version_id
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
