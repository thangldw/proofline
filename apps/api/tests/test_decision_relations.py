from datetime import UTC, datetime


def _decision(client, uri: str, statement: str) -> dict:
    created = client.post(
        "/api/v1/sources",
        json={"title": statement, "content": f"Decision: {statement}", "uri": uri},
    )
    assert created.status_code == 201
    return next(
        item for item in client.get("/api/v1/decisions").json() if item["statement"] == statement
    )


def test_supersedes_relation_closes_old_validity_and_exposes_timeline(client):
    old = _decision(client, "file:///old.md", "Use Redis cache")
    new = _decision(client, "file:///new.md", "Use SQLite cache")
    effective = datetime(2026, 7, 14, 4, 30, tzinfo=UTC).isoformat()
    created = client.post(
        "/api/v1/decision-relations",
        json={
            "source_decision_id": new["id"],
            "target_decision_id": old["id"],
            "kind": "supersedes",
            "valid_from": effective,
        },
    )
    assert created.status_code == 201
    old_after = client.get(f"/api/v1/decisions/{old['id']}").json()
    new_after = client.get(f"/api/v1/decisions/{new['id']}").json()
    assert old_after["status"] == "obsolete"
    assert old_after["valid_to"] == "2026-07-14T04:30:00"
    assert new_after["valid_from"] == "2026-07-14T04:30:00"
    timeline = client.get(f"/api/v1/decisions/{old['id']}/timeline").json()
    assert [item["source_decision_id"] for item in timeline["incoming"]] == [new["id"]]
    assert timeline["outgoing"] == []
    audit = client.get(
        "/api/v1/audit-events", params={"object_type": "decision", "object_id": old["id"]}
    ).json()
    assert audit[0]["action"] == "decision.superseded"
    assert audit[0]["before_json"]["valid_to"] is None
    assert audit[0]["after_json"]["valid_to"] == effective
    hits = client.get("/api/v1/search", params={"q": "cache"}).json()["hits"]
    assert hits[0]["source_id"] == new["source_id"]
    assert hits[0]["temporal_priority"] == "current_decision"
    impact = client.get(f"/api/v1/sources/{old['source_id']}/deletion-impact").json()
    assert impact["decision_relations"] == 1
    assert client.delete(f"/api/v1/sources/{old['source_id']}").status_code == 204
    assert client.get("/api/v1/decision-relations").json() == []


def test_relation_contract_rejects_self_missing_duplicate_and_invalid_kind(client):
    first = _decision(client, "file:///first.md", "Keep REST")
    second = _decision(client, "file:///second.md", "Add events")
    payload = {
        "source_decision_id": first["id"],
        "target_decision_id": second["id"],
        "kind": "implements",
    }
    assert client.post("/api/v1/decision-relations", json=payload).status_code == 201
    assert client.post("/api/v1/decision-relations", json=payload).status_code == 409
    assert (
        client.post(
            "/api/v1/decision-relations", json={**payload, "target_decision_id": first["id"]}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/v1/decision-relations", json={**payload, "kind": "unknown"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/decision-relations", json={**payload, "target_decision_id": "missing"}
        ).status_code
        == 404
    )


def test_contradiction_candidates_are_reported_without_mutating_decisions(client):
    first = _decision(client, "file:///candidate-a.md", "Keep polling")
    second = _decision(client, "file:///candidate-b.md", "Stop polling")
    created = client.post(
        "/api/v1/decision-relations",
        json={
            "source_decision_id": first["id"],
            "target_decision_id": second["id"],
            "kind": "contradicts",
        },
    )
    assert created.status_code == 201
    candidates = client.get("/api/v1/decision-relation-candidates").json()
    assert candidates == [
        {
            "kind": "contradiction",
            "decision_ids": [first["id"], second["id"]],
            "relation_id": created.json()["id"],
            "reason": "Both contradictory decisions are still non-obsolete; review required.",
        }
    ]
    assert client.get(f"/api/v1/decisions/{first['id']}").json()["status"] == "active"
    assert client.get(f"/api/v1/decisions/{second['id']}").json()["status"] == "active"
