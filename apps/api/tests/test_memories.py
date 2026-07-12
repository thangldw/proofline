import json

import proofline.api as api_module
from proofline.model_gateway import (
    FakeGenerationProvider,
    GenerationResult,
    ModelCapabilities,
    ProviderRequestError,
)


class ScriptedGenerationProvider:
    id = "scripted"
    model = "scripted-memory-api-test"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def capabilities(self):
        return ModelCapabilities()

    def health(self):
        return True

    def generate(self, _request):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return GenerationResult(content=outcome)


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

    candidate = client.patch(f"/api/v1/memories/{assumption['id']}", json={"status": "candidate"})
    assert candidate.status_code == 200
    assert candidate.json()["status"] == "candidate"
    assert candidate.json()["evidence"] == assumption["evidence"]
    active = client.patch(f"/api/v1/memories/{assumption['id']}", json={"status": "active"})
    assert active.status_code == 200
    assert active.json()["status"] == "active"
    assert active.json()["evidence"] == assumption["evidence"]
    audit = client.get(
        "/api/v1/audit-events",
        params={"object_type": "memory", "object_id": assumption["id"]},
    ).json()
    assert [event["before_json"]["status"] for event in audit] == [
        "candidate",
        "accepted",
        "active",
    ]
    assert [event["after_json"]["status"] for event in audit] == [
        "active",
        "candidate",
        "accepted",
    ]

    impact = client.get(f"/api/v1/sources/{source['id']}/deletion-impact").json()
    assert impact["decisions"] == 1
    assert impact["memories"] == 2
    assert impact["audit_events_to_delete"] == 3
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


def test_provider_failure_run_lineage_is_inspectable_and_source_remains_searchable(
    client, monkeypatch
):
    private_source_text = "SQLite is retained because local recovery must remain searchable."
    source = client.post(
        "/api/v1/sources",
        json={
            "title": "Recovery note",
            "content": private_source_text,
            "uri": "file:///recovery.md",
        },
    ).json()
    provider = ScriptedGenerationProvider(
        ["not valid JSON", ProviderRequestError("safe provider failure")]
    )
    monkeypatch.setattr(api_module, "build_generation_provider", lambda _settings: provider)

    failed = client.post(f"/api/v1/sources/{source['id']}/extract-memories")

    assert failed.status_code == 502
    last_run_id = failed.headers["x-proofline-model-run-id"]
    detail = client.get(f"/api/v1/model/runs/{last_run_id}")
    assert detail.status_code == 200
    run = detail.json()
    assert run["status"] == "failed"
    assert run["error_code"] == "provider_request_failed"
    assert run["attempt_number"] == 2
    assert run["repair_reason"] == "structured_output_invalid"
    assert run["parent_run_id"]
    assert private_source_text not in detail.text

    parent = client.get(f"/api/v1/model/runs/{run['parent_run_id']}").json()
    assert parent["status"] == "failed"
    assert parent["error_code"] == "structured_output_invalid"
    children = client.get(
        "/api/v1/model/runs",
        params={
            "parent_run_id": parent["id"],
            "operation": "generate",
            "provider_id": provider.id,
            "status": "failed",
            "limit": 1,
        },
    ).json()
    assert [child["id"] for child in children] == [last_run_id]
    assert client.get("/api/v1/model/runs/missing-run").status_code == 404
    assert client.get("/api/v1/model/runs", params={"limit": 201}).status_code == 422

    search = client.get("/api/v1/search", params={"q": "local recovery"})
    assert search.status_code == 200
    assert search.json()["hits"][0]["source_id"] == source["id"]
    assert client.get("/api/v1/memories").json() == []
