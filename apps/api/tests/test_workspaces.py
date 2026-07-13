from datetime import timedelta

import pytest
from proofline.folder_scanning import FolderScanCoordinator, FolderScanError
from proofline.models import DEFAULT_WORKSPACE_ID, WorkspaceLease, utc_now
from proofline.schemas import FolderScanRequest


def test_workspace_sources_search_jobs_and_deletion_are_isolated(client):
    workspace = client.post(
        "/api/v1/workspaces",
        json={"slug": "platform", "title": "Platform"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]
    headers = {"X-Proofline-Workspace-ID": workspace_id}

    default_source = client.post(
        "/api/v1/sources",
        json={
            "title": "Default ADR",
            "uri": "file:///shared.md",
            "content": "Decision: Keep the default sentinel route",
        },
    ).json()
    scoped = client.post(
        "/api/v1/sources",
        headers=headers,
        json={
            "title": "Platform ADR",
            "uri": "file:///shared.md",
            "content": "Decision: Keep the platform sentinel route",
        },
    )
    assert scoped.status_code == 201
    scoped_source = scoped.json()

    assert [item["id"] for item in client.get("/api/v1/sources").json()] == [default_source["id"]]
    assert [item["id"] for item in client.get("/api/v1/sources", headers=headers).json()] == [
        scoped_source["id"]
    ]
    assert client.get("/api/v1/overview").json()["sources"] == 1
    assert client.get("/api/v1/overview", headers=headers).json()["sources"] == 1

    default_hits = client.get("/api/v1/search", params={"q": "sentinel route"}).json()["hits"]
    scoped_hits = client.get(
        "/api/v1/search", headers=headers, params={"q": "sentinel route"}
    ).json()["hits"]
    assert {hit["source_id"] for hit in default_hits} == {default_source["id"]}
    assert {hit["source_id"] for hit in scoped_hits} == {scoped_source["id"]}
    assert len(client.get("/api/v1/jobs").json()) == 1
    assert len(client.get("/api/v1/jobs", headers=headers).json()) == 1

    assert client.get(f"/api/v1/sources/{scoped_source['id']}").status_code == 404
    assert client.delete(f"/api/v1/sources/{scoped_source['id']}").status_code == 404
    assert client.get(f"/api/v1/sources/{scoped_source['id']}", headers=headers).status_code == 200


def test_unknown_workspace_header_is_rejected(client):
    response = client.get(
        "/api/v1/sources",
        headers={"X-Proofline-Workspace-ID": "00000000-0000-0000-0000-000000000099"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found"


def test_folder_scan_lease_blocks_another_worker_and_preserves_owner(session):
    lease = WorkspaceLease(
        workspace_id=DEFAULT_WORKSPACE_ID,
        owner_id="worker-one",
        purpose="folder_scan",
        expires_at=utc_now() + timedelta(minutes=5),
    )
    session.add(lease)
    session.commit()

    coordinator = FolderScanCoordinator()
    with pytest.raises(FolderScanError, match="Another worker") as captured:
        coordinator.scan(session, FolderScanRequest(), ())

    assert captured.value.code == "scan_in_progress"
    assert session.get(WorkspaceLease, DEFAULT_WORKSPACE_ID).owner_id == "worker-one"
