import hashlib

from proofline.models import StudioArtifact, StudioCitation
from proofline.studio import STUDIO_KINDS
from sqlalchemy import func, select

CONTENT = """# Queue architecture

Durable queues preserve work across process restarts.

## Delivery

Consumers acknowledge work only after the database transaction commits.

## Recovery

Failed work remains visible and can be retried explicitly.
"""


def test_all_studio_kinds_are_persistent_and_exactly_cited(client, session):
    source = client.post(
        "/api/v1/sources",
        json={"title": "Queue architecture", "content": CONTENT},
    ).json()

    for kind in STUDIO_KINDS:
        response = client.post(
            "/api/v1/studio-artifacts",
            json={"source_id": source["id"], "kind": kind},
        )
        assert response.status_code == 201
        artifact = response.json()
        assert artifact["kind"] == kind
        assert artifact["source_version_id"] == source["current_version_id"]
        assert artifact["generation_method"] == "deterministic-v1"
        assert artifact["content"]["items"]
        assert artifact["citations"]
        for citation in artifact["citations"]:
            quote = CONTENT[citation["start_offset"] : citation["end_offset"]]
            assert quote == citation["quote"]
            assert hashlib.sha256(quote.encode()).hexdigest() == citation["quote_hash"]

    listed = client.get("/api/v1/studio-artifacts")
    assert listed.status_code == 200
    assert {artifact["kind"] for artifact in listed.json()} == set(STUDIO_KINDS)
    assert session.scalar(select(func.count()).select_from(StudioArtifact)) == len(STUDIO_KINDS)


def test_studio_generation_is_idempotent_versioned_and_deleted_with_source(client, session):
    source = client.post(
        "/api/v1/sources",
        json={"title": "Queue architecture", "uri": "note://queue", "content": CONTENT},
    ).json()
    first = client.post(
        "/api/v1/studio-artifacts",
        json={"source_id": source["id"], "kind": "report"},
    ).json()
    repeated = client.post(
        "/api/v1/studio-artifacts",
        json={"source_id": source["id"], "kind": "report"},
    ).json()
    assert repeated["id"] == first["id"]

    revised_content = f"{CONTENT}\n## Operations\n\nOperators inspect retry state before replay.\n"
    revised = client.post(
        "/api/v1/sources",
        json={"title": "Queue architecture", "uri": "note://queue", "content": revised_content},
    ).json()
    current = client.post(
        "/api/v1/studio-artifacts",
        json={"source_id": source["id"], "kind": "report"},
    ).json()
    assert current["id"] != first["id"]
    assert current["source_version_id"] == revised["current_version_id"]

    impact = client.get(f"/api/v1/sources/{source['id']}/deletion-impact").json()
    assert impact["studio_artifacts"] == 2
    assert impact["studio_citations"] > 2
    assert client.delete(f"/api/v1/sources/{source['id']}").status_code == 204
    assert session.scalar(select(func.count()).select_from(StudioArtifact)) == 0
    assert session.scalar(select(func.count()).select_from(StudioCitation)) == 0


def test_studio_failures_are_explicit_and_workspace_scoped(client):
    empty = client.post(
        "/api/v1/sources",
        json={"title": "Whitespace", "content": "   \n  "},
    ).json()
    no_evidence = client.post(
        "/api/v1/studio-artifacts",
        json={"source_id": empty["id"], "kind": "report"},
    )
    assert no_evidence.status_code == 422
    assert "usable evidence" in no_evidence.json()["detail"]

    missing = client.post(
        "/api/v1/studio-artifacts",
        json={"source_id": "11111111-1111-1111-1111-111111111111", "kind": "report"},
    )
    assert missing.status_code == 404
