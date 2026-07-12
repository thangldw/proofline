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


def test_search_escapes_fts_syntax(client):
    client.post(
        "/api/v1/sources",
        json={"title": "Syntax", "content": "A decision about queues and workers."},
    )
    response = client.get("/api/v1/search", params={"q": 'queues OR "workers" -broken'})
    assert response.status_code == 200
    assert response.json()["hits"]
