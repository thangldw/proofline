import json

import proofline.api as api_module
from proofline.model_gateway import FakeGenerationProvider


def test_memory_routes_filter_review_audit_and_delete_without_leakage(client):
    content = (
        "Decision: Use SQLite for local state\nReason: no service dependency.\n\n"
        "Assumption: A single writer owns the database."
    )
    created = client.post(
        "/api/v1/sources",
        json={"title": "Memory ADR", "content": content, "uri": "file:///memory.md"},
    )
    assert created.status_code == 201
    source = created.json()
    assert source["decision_count"] == 1
    assert source["memory_count"] == 2
    overview = client.get("/api/v1/overview").json()
    assert overview["decisions"] == 1
    assert overview["memories"] == 2
    assert overview["evidence"] == 2

    memories = client.get("/api/v1/memories").json()
    assert {memory["kind"] for memory in memories} == {"decision", "assumption"}
    for memory in memories:
        evidence = memory["evidence"][0]
        assert content[evidence["start_offset"] : evidence["end_offset"]] == evidence["quote"]

    assumptions = client.get("/api/v1/memories", params={"kind": "assumption"}).json()
    assert len(assumptions) == 1
    assumption = assumptions[0]
    decisions = client.get("/api/v1/decisions").json()
    assert len(decisions) == 1
    assert decisions[0]["kind"] == "decision"
    assert client.get(f"/api/v1/decisions/{assumption['id']}").status_code == 404
    assert (
        client.patch(
            f"/api/v1/decisions/{assumption['id']}", json={"status": "accepted"}
        ).status_code
        == 404
    )
    assert client.get("/api/v1/memories", params={"kind": "incident"}).status_code == 422

    reviewed = client.patch(
        f"/api/v1/memories/{assumption['id']}",
        json={"status": "accepted", "rationale": "Confirmed by the owner."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["kind"] == "assumption"
    assert reviewed.json()["status"] == "accepted"
    assert len(client.get("/api/v1/memories", params={"status": "accepted"}).json()) == 1
    audit = client.get(
        "/api/v1/audit-events",
        params={"object_type": "memory", "object_id": assumption["id"]},
    ).json()
    assert len(audit) == 1
    assert audit[0]["action"] == "memory.updated"
    assert audit[0]["before_json"]["kind"] == "assumption"
    assert audit[0]["after_json"]["status"] == "accepted"

    impact = client.get(f"/api/v1/sources/{source['id']}/deletion-impact").json()
    assert impact["decisions"] == 1
    assert impact["memories"] == 2
    assert impact["audit_events_to_delete"] == 1
    assert client.delete(f"/api/v1/sources/{source['id']}").status_code == 204
    assert (
        client.get(
            "/api/v1/audit-events",
            params={"object_type": "memory", "object_id": assumption["id"]},
        ).json()
        == []
    )


def test_generalized_model_endpoint_and_decision_compatibility_filter(client, monkeypatch):
    created = client.post(
        "/api/v1/sources",
        json={
            "title": "Unstructured architecture note",
            "content": "SQLite is local and currently has one writer.",
        },
    ).json()
    chunk_id = client.get("/api/v1/search", params={"q": "SQLite writer"}).json()["hits"][0][
        "chunk_id"
    ]
    provider = FakeGenerationProvider(
        json.dumps(
            {
                "candidates": [
                    {
                        "kind": "decision",
                        "statement": "Use SQLite locally",
                        "confidence": 0.9,
                        "evidence_ids": [chunk_id],
                    },
                    {
                        "kind": "assumption",
                        "statement": "There is one writer",
                        "confidence": 0.8,
                        "evidence_ids": [chunk_id],
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(api_module, "build_generation_provider", lambda _settings: provider)

    rejected_legacy = client.post(f"/api/v1/sources/{created['id']}/extract-decisions")
    assert rejected_legacy.status_code == 502
    assert client.get("/api/v1/memories").json() == []

    generalized = client.post(f"/api/v1/sources/{created['id']}/extract-memories")
    decision_only_provider = FakeGenerationProvider(
        json.dumps(
            {
                "candidates": [
                    {
                        "kind": "decision",
                        "statement": "Use SQLite locally",
                        "confidence": 0.9,
                        "evidence_ids": [chunk_id],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(
        api_module,
        "build_generation_provider",
        lambda _settings: decision_only_provider,
    )
    compatibility = client.post(f"/api/v1/sources/{created['id']}/extract-decisions")

    assert generalized.status_code == 200
    assert {item["kind"] for item in generalized.json()} == {"decision", "assumption"}
    assert all(item["status"] == "candidate" for item in generalized.json())
    assert compatibility.status_code == 200
    assert [item["kind"] for item in compatibility.json()] == ["decision"]
    assert {item["kind"] for item in client.get("/api/v1/memories").json()} == {
        "decision",
        "assumption",
    }
    assert [item["kind"] for item in client.get("/api/v1/decisions").json()] == ["decision"]
