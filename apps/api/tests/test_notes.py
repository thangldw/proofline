from proofline.models import DEFAULT_WORKSPACE_ID


def test_note_versions_search_links_and_backlinks(client):
    first = client.post(
        "/api/v1/notes",
        json={"title": "Queue design", "content": "Choose durable queues. #architecture"},
    )
    assert first.status_code == 201
    note = first.json()
    assert note["uri"].startswith("note://")
    assert note["version_count"] == 1
    assert note["tags"][0]["name"] == "architecture"
    original_version = note["current_version_id"]

    linking = client.post(
        "/api/v1/notes",
        json={
            "title": "Worker rollout",
            "content": "This implements [[Queue design]] safely.",
        },
    ).json()
    link = linking["links"][0]
    assert link["resolved_source_id"] == note["id"]
    assert linking["content"][link["start_offset"] : link["end_offset"]] == link["quote"]

    backlinks = client.get(f"/api/v1/notes/{note['id']}/backlinks").json()
    assert len(backlinks) == 1
    assert backlinks[0]["source_id"] == linking["id"]
    assert backlinks[0]["source_version_id"] == linking["current_version_id"]
    assert backlinks[0]["quote"] == "[[Queue design]]"

    updated = client.put(
        f"/api/v1/notes/{note['id']}",
        json={"title": "Queue design", "content": "Choose durable queues with retries."},
    )
    assert updated.status_code == 200
    revised = updated.json()
    assert revised["id"] == note["id"]
    assert revised["uri"] == note["uri"]
    assert revised["version_count"] == 2
    assert revised["current_version_id"] != original_version

    historical = client.get(f"/api/v1/sources/{note['id']}/versions/{original_version}")
    assert historical.status_code == 200
    assert historical.json()["content"] == "Choose durable queues. #architecture"

    hits = client.get("/api/v1/search", params={"q": "retries"}).json()["hits"]
    assert hits[0]["source_id"] == note["id"]
    assert hits[0]["source_version_id"] == revised["current_version_id"]


def test_notes_are_workspace_scoped_and_non_notes_are_rejected(client):
    workspace = client.post(
        "/api/v1/workspaces", json={"slug": "learning", "title": "Learning"}
    ).json()
    note = client.post("/api/v1/notes", json={"title": "Private", "content": "Scoped note"}).json()
    other_headers = {"X-Proofline-Workspace-ID": workspace["id"]}
    assert client.get("/api/v1/notes", headers=other_headers).json() == []
    assert client.get(f"/api/v1/notes/{note['id']}", headers=other_headers).status_code == 404

    source = client.post(
        "/api/v1/sources",
        json={"title": "Imported", "content": "ordinary markdown"},
    ).json()
    assert client.get(f"/api/v1/notes/{source['id']}").status_code == 404
    assert DEFAULT_WORKSPACE_ID == note["workspace_id"]


def test_deleting_note_removes_all_versions_and_search_rows(client):
    note = client.post(
        "/api/v1/notes", json={"title": "Disposable", "content": "rare-note-token"}
    ).json()
    assert client.delete(f"/api/v1/sources/{note['id']}").status_code == 204
    assert client.get(f"/api/v1/notes/{note['id']}").status_code == 404
    assert client.get("/api/v1/search", params={"q": "rare-note-token"}).json()["hits"] == []


def test_duplicate_titles_leave_wiki_links_explicitly_unresolved(client):
    first = client.post("/api/v1/notes", json={"title": "Shared title", "content": "First"}).json()
    client.post("/api/v1/notes", json={"title": "Shared title", "content": "Second"})
    linking = client.post(
        "/api/v1/notes", json={"title": "Linking", "content": "[[Shared title]]"}
    ).json()
    assert linking["links"][0]["resolved_source_id"] is None
    assert client.get(f"/api/v1/notes/{first['id']}/backlinks").json() == []
