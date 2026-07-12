def test_complete_workflow(client):
    content = (
        "# ADR-007\n\n"
        "## Decision: Use SQLite for the local job queue\n"
        "Rationale: It offers transactional recovery without another service.\n"
        "Status: active\n\n"
        "Kafka remains an alternative for hosted scale."
    )
    created = client.post(
        "/api/v1/sources",
        json={"title": "ADR-007", "content": content, "uri": "file:///adr-007.md"},
    )
    assert created.status_code == 201
    source = created.json()
    assert source["chunk_count"] >= 1
    assert source["decision_count"] == 1

    search = client.get("/api/v1/search", params={"q": "transactional recovery"})
    assert search.status_code == 200
    assert search.json()["hits"][0]["source_title"] == "ADR-007"

    decisions = client.get("/api/v1/decisions").json()
    assert decisions[0]["statement"] == "Use SQLite for the local job queue"
    evidence = decisions[0]["evidence"][0]
    assert content[evidence["start_offset"] : evidence["end_offset"]] == evidence["quote"]

    source_detail = client.get(f"/api/v1/sources/{source['id']}").json()
    assert source_detail["content"] == content

    deleted = client.delete(f"/api/v1/sources/{source['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/search", params={"q": "transactional recovery"}).json()["hits"] == []
    assert client.get("/api/v1/decisions").json() == []


def test_duplicate_import_returns_existing_source(client):
    payload = {"title": "same", "content": "Decision: keep exact evidence"}
    assert client.post("/api/v1/sources", json=payload).status_code == 201
    assert client.post("/api/v1/sources", json=payload).status_code == 200
    assert client.get("/api/v1/overview").json()["sources"] == 1


def test_updating_same_uri_searches_current_version_and_lists_history(client):
    first = client.post(
        "/api/v1/sources",
        json={
            "title": "Queue ADR",
            "uri": "file:///queue.md",
            "content": "Decision: Use Kafka for throughput",
        },
    ).json()
    old_decision = client.get("/api/v1/decisions").json()[0]

    updated = client.post(
        "/api/v1/sources",
        json={
            "title": "Queue ADR revised",
            "uri": "file:///queue.md",
            "content": "Decision: Use NATS for operational simplicity",
        },
    )

    assert updated.status_code == 200
    assert updated.json()["id"] == first["id"]
    assert updated.json()["version_count"] == 2
    assert client.get("/api/v1/search", params={"q": "Kafka"}).json()["hits"] == []
    assert len(client.get("/api/v1/search", params={"q": "NATS"}).json()["hits"]) == 1
    assert [item["statement"] for item in client.get("/api/v1/decisions").json()] == [
        "Use NATS for operational simplicity"
    ]
    assert client.get("/api/v1/overview").json() == {
        "sources": 1,
        "chunks": 1,
        "decisions": 1,
        "evidence": 1,
    }
    assert client.get(f"/api/v1/decisions/{old_decision['id']}").status_code == 200
    versions = client.get(f"/api/v1/sources/{first['id']}/versions").json()
    assert len(versions) == 2
    assert len({version["content_hash"] for version in versions}) == 2
    historical = client.get(
        f"/api/v1/sources/{first['id']}/versions/{old_decision['source_version_id']}"
    ).json()
    old_evidence = old_decision["evidence"][0]
    assert (
        historical["content"][old_evidence["start_offset"] : old_evidence["end_offset"]]
        == old_evidence["quote"]
    )


def test_identical_content_at_distinct_uris_creates_distinct_sources(client):
    payload = {"title": "ADR", "content": "Decision: keep source identity"}
    first = client.post("/api/v1/sources", json={**payload, "uri": "file:///team-a/adr.md"})
    second = client.post("/api/v1/sources", json={**payload, "uri": "file:///team-b/adr.md"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_search_escapes_fts_syntax(client):
    client.post(
        "/api/v1/sources",
        json={"title": "Syntax", "content": "A decision about queues and workers."},
    )
    response = client.get("/api/v1/search", params={"q": 'queues OR "workers" -broken'})
    assert response.status_code == 200
    assert response.json()["hits"]
