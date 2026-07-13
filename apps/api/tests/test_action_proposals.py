import json

from proofline.model_gateway import FakeGenerationProvider
from proofline.models import ActionProposal, AuditEvent, Chunk, ProposalCitation
from sqlalchemy import func, select


def grounded_provider(chunk_id: str) -> FakeGenerationProvider:
    return FakeGenerationProvider(
        json.dumps(
            {
                "statements": [
                    {
                        "text": "Add bounded retries before changing the queue architecture.",
                        "kind": "inference",
                        "evidence_ids": [chunk_id],
                    }
                ]
            }
        )
    )


def test_action_proposal_is_grounded_candidate_and_requires_review(client, session, monkeypatch):
    content = "The queue loses work on transient failure. Add bounded retries first."
    source = client.post(
        "/api/v1/sources", json={"title": "Queue evidence", "content": content}
    ).json()
    chunk = session.scalar(select(Chunk).where(Chunk.source_id == source["id"]))
    monkeypatch.setattr(
        "proofline.api.build_generation_provider", lambda _settings: grounded_provider(chunk.id)
    )

    created = client.post(
        "/api/v1/action-proposals", json={"question": "What should change in the queue?"}
    )
    assert created.status_code == 201
    proposal = created.json()
    assert proposal["status"] == "candidate"
    assert proposal["model_run_id"]
    assert proposal["body"].startswith("Add bounded retries")
    citation = proposal["citations"][0]
    assert citation["chunk_id"] == chunk.id
    assert citation["source_version_id"] == source["current_version_id"]
    assert content[citation["start_offset"] : citation["end_offset"]] == citation["quote"]

    accepted = client.patch(
        f"/api/v1/action-proposals/{proposal['id']}", json={"status": "accepted"}
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert (
        client.patch(
            f"/api/v1/action-proposals/{proposal['id']}", json={"status": "rejected"}
        ).status_code
        == 409
    )
    events = session.scalars(
        select(AuditEvent).where(
            AuditEvent.object_type == "action_proposal", AuditEvent.object_id == proposal["id"]
        )
    ).all()
    assert [event.action for event in events] == [
        "action_proposal.created",
        "action_proposal.reviewed",
    ]


def test_action_proposal_requires_provider_and_is_workspace_scoped(client):
    client.post("/api/v1/sources", json={"title": "Evidence", "content": "Grounded context."})
    unavailable = client.post(
        "/api/v1/action-proposals", json={"question": "What is the grounded context?"}
    )
    assert unavailable.status_code == 409
    workspace = client.post(
        "/api/v1/workspaces", json={"slug": "other-brain", "title": "Other Brain"}
    ).json()
    assert (
        client.get(
            "/api/v1/action-proposals", headers={"X-Proofline-Workspace-ID": workspace["id"]}
        ).json()
        == []
    )


def test_source_deletion_removes_entire_multi_source_proposal(client, session, monkeypatch):
    first = client.post(
        "/api/v1/sources", json={"title": "First", "content": "Retries reduce queue loss."}
    ).json()
    second = client.post(
        "/api/v1/sources", json={"title": "Second", "content": "Bound retries to three attempts."}
    ).json()
    chunks = session.scalars(select(Chunk).order_by(Chunk.source_id)).all()
    provider = FakeGenerationProvider(
        json.dumps(
            {
                "statements": [
                    {
                        "text": "Use three bounded retry attempts.",
                        "kind": "synthesis",
                        "evidence_ids": [chunk.id for chunk in chunks],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr("proofline.api.build_generation_provider", lambda _settings: provider)
    client.post("/api/v1/action-proposals", json={"question": "How should retries work?"}).json()
    impact = client.get(f"/api/v1/sources/{first['id']}/deletion-impact").json()
    assert impact["action_proposals"] == 1
    assert impact["proposal_citations"] == 2
    assert client.delete(f"/api/v1/sources/{first['id']}").status_code == 204
    assert session.scalar(select(func.count()).select_from(ActionProposal)) == 0
    assert session.scalar(select(func.count()).select_from(ProposalCitation)) == 0
    assert client.get(f"/api/v1/sources/{second['id']}").status_code == 200
