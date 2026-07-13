from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from proofline.models import Source
from sqlalchemy import select
from sqlalchemy.orm import Session


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repository(tmp_path: Path) -> Path:
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture Author")
    git(repo, "config", "user.email", "fixture@example.test")
    (repo / "adr.md").write_text(
        "# Cache decision\n\nDecision: Use Redis for bounded cache entries.\n", encoding="utf-8"
    )
    (repo / "ignored.bin").write_bytes(b"\x00\xff")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "record cache decision", "-m", "Keeps cache policy explicit.")
    return repo


def test_git_repository_import_is_immutable_idempotent_and_searchable(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    repo = make_repository(tmp_path)
    sha = git(repo, "rev-parse", "HEAD")

    created = client.post("/api/v1/git-repositories", json={"path": str(repo)})
    assert created.status_code == 201
    payload = created.json()
    assert payload["commit_sha"] == sha
    assert payload["created_count"] == 2
    assert payload["failed_count"] == 0
    assert payload["repository"]["file_count"] == 1
    assert payload["repository"]["commit_count"] == 1

    sources = client.get("/api/v1/sources").json()
    file_source = next(source for source in sources if source["kind"] == "git_file")
    assert file_source["git_commit_sha"] == sha
    assert file_source["git_path"] == "adr.md"
    hit = client.get("/api/v1/search", params={"q": "Redis"}).json()["hits"][0]
    assert hit["source_id"] == file_source["id"]
    assert hit["start_line"] == 1
    assert hit["end_line"] == 3
    assert hit["source_kind"] == "git_file"
    assert hit["git_commit_sha"] == sha
    assert hit["git_path"] == "adr.md"

    repeated = client.post("/api/v1/git-repositories", json={"path": str(repo)})
    assert repeated.status_code == 200
    assert repeated.json()["created_count"] == 0
    assert repeated.json()["unchanged_count"] == 2
    assert len(client.get("/api/v1/sources").json()) == 2


def test_git_rescan_preserves_old_commit_and_repository_delete_cascades(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    repo = make_repository(tmp_path)
    first_sha = git(repo, "rev-parse", "HEAD")
    first = client.post("/api/v1/git-repositories", json={"path": str(repo)}).json()
    (repo / "adr.md").write_text(
        "# Cache decision\n\nDecision: Use SQLite for the local cache.\n", encoding="utf-8"
    )
    git(repo, "add", "adr.md")
    git(repo, "commit", "-q", "-m", "replace cache implementation")
    second_sha = git(repo, "rev-parse", "HEAD")

    second = client.post("/api/v1/git-repositories", json={"path": str(repo)}).json()
    assert second["commit_sha"] == second_sha
    sources = client.get("/api/v1/sources").json()
    assert {source["git_commit_sha"] for source in sources} == {first_sha, second_sha}
    old_source = next(
        source
        for source in sources
        if source["kind"] == "git_file" and source["git_commit_sha"] == first_sha
    )
    old_version = client.get(
        f"/api/v1/sources/{old_source['id']}/versions/{old_source['current_version_id']}"
    ).json()
    assert "Redis" in old_version["content"]

    deleted = client.delete(f"/api/v1/git-repositories/{first['repository']['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/sources").json() == []
    assert session.scalars(select(Source)).all() == []


def test_git_import_reports_invalid_repository(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "not-git"
    folder.mkdir()
    response = client.post("/api/v1/git-repositories", json={"path": str(folder)})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "git_command_failed"
