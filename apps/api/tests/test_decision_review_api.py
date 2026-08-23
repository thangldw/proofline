import json

from proofline.decision_reviews import refresh_decision_reviews
from proofline.ingestion import ingest_source
from proofline.models import AuditEvent, Decision, DecisionReview
from proofline.schemas import SourceCreate
from sqlalchemy import select

ORIGINAL = "# Queue\n\nDecision: Use SQLite.\nReason: local durability."
CHANGED = "# Queue\n\nDecision: Use NATS.\nReason: shared workload."


def _open_review(session):
    source, _created = ingest_source(
        session,
        SourceCreate(title="ADR", uri="file:///review-api.md", content=ORIGINAL),
    )
    decision = session.scalar(
        select(Decision).where(
            Decision.source_version_id == source.current_version_id,
            Decision.kind == "decision",
        )
    )
    assert decision is not None
    decision.status = "accepted"
    session.commit()
    source, _created = ingest_source(
        session,
        SourceCreate(title="ADR", uri=source.uri, content=CHANGED),
    )
    refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()
    review = session.scalar(select(DecisionReview).where(DecisionReview.decision_id == decision.id))
    assert review is not None
    return source, decision, review


def test_overview_list_and_detail_are_scoped_and_content_bounded(client, session):
    source, decision, review = _open_review(session)

    overview = client.get("/api/v1/decision-health/overview")
    assert overview.status_code == 200
    assert overview.json() == {
        "healthy_accepted": 0,
        "review_required": 1,
        "overdue": 0,
        "waived": 0,
    }
    response = client.get(
        "/api/v1/decision-reviews",
        params={"state": "open", "anchor_state": "changed", "severity": "warning", "limit": 1},
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [review.id]
    serialized = json.dumps(response.json(), sort_keys=True)
    assert "SQLite" not in serialized
    assert "NATS" not in serialized
    assert "quote" not in serialized

    detail = client.get(f"/api/v1/decision-reviews/{review.id}")
    assert detail.status_code == 200
    document = detail.json()
    assert document["review"]["id"] == review.id
    assert document["decision"]["id"] == decision.id
    assert document["cited"]["quote"] == ORIGINAL.split("\n\n", 1)[1]
    assert document["cited"]["content_sha256"] != document["current"]["content_sha256"]
    assert document["current"]["candidate"]["start_line"] >= 1
    assert document["audit_events"]

    workspace = client.post("/api/v1/workspaces", json={"slug": "other", "title": "Other"}).json()
    headers = {"X-Proofline-Workspace-ID": workspace["id"]}
    assert client.get("/api/v1/decision-reviews", headers=headers).json() == []
    assert client.get(f"/api/v1/decision-reviews/{review.id}", headers=headers).status_code == 404
    assert (
        client.get("/api/v1/decision-health/overview", headers=headers).json()["review_required"]
        == 0
    )
    assert source.workspace_id != workspace["id"]


def test_list_validates_limit(client):
    assert client.get("/api/v1/decision-reviews", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/decision-reviews", params={"limit": 201}).status_code == 422


def test_list_orders_error_before_warning_then_applies_limit(client, session):
    _source, _decision, warning = _open_review(session)
    error = DecisionReview(
        workspace_id=warning.workspace_id,
        decision_id=warning.decision_id,
        evidence_id=warning.evidence_id,
        cited_source_version_id=warning.cited_source_version_id,
        current_source_version_id=warning.current_source_version_id,
        finding_fingerprint="f" * 64,
        anchor_state="deleted",
        severity="error",
        policy_hash=warning.policy_hash,
        state="open",
        actor="local_system",
    )
    session.add(error)
    session.commit()

    response = client.get("/api/v1/decision-reviews", params={"limit": 1})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [error.id]


def test_refresh_and_acknowledge_are_audited_with_stable_conflict(client, session):
    _source, _decision, review = _open_review(session)

    refreshed = client.post("/api/v1/decision-reviews/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["unchanged"] == 1
    acknowledged = client.patch(
        f"/api/v1/decision-reviews/{review.id}",
        json={"action": "acknowledge"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["state"] == "acknowledged"
    conflict = client.patch(
        f"/api/v1/decision-reviews/{review.id}",
        json={"action": "acknowledge"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {"code": "review_state_conflict"}
    assert (
        session.scalar(
            select(AuditEvent).where(AuditEvent.action == "decision_review_acknowledged")
        )
        is not None
    )


def test_reanchor_maps_optimistic_version_conflict_then_resolves(client, session):
    source, decision, review = _open_review(session)
    start = CHANGED.index("Decision: Use NATS.")
    payload = {
        "expected_current_source_version_id": review.cited_source_version_id,
        "start_offset": start,
        "end_offset": start + len("Decision: Use NATS."),
        "reason": "requirement intentionally changed",
    }

    conflict = client.post(f"/api/v1/decision-reviews/{review.id}/reanchor", json=payload)
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {"code": "source_version_conflict"}

    payload["expected_current_source_version_id"] = source.current_version_id
    resolved = client.post(f"/api/v1/decision-reviews/{review.id}/reanchor", json=payload)
    assert resolved.status_code == 200
    assert resolved.json()["resolution"] == "reanchored"
    assert session.get(Decision, decision.id).source_version_id == source.current_version_id


def test_resolve_can_obsolete_decision(client, session):
    _source, decision, review = _open_review(session)

    response = client.post(
        f"/api/v1/decision-reviews/{review.id}/resolve",
        json={"action": "obsolete_decision", "reason": "no longer applies"},
    )

    assert response.status_code == 200
    assert response.json()["resolution"] == "obsolete_decision"
    assert session.get(Decision, decision.id).status == "obsolete"
