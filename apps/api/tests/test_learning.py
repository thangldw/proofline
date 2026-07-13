import hashlib

from proofline.models import StudyCard, StudyReview
from sqlalchemy import func, select


def test_deterministic_study_cards_have_exact_immutable_evidence(client):
    content = "Context first.\nQ: Why use durable queues?\nA: They preserve work across restarts.\n"
    source = client.post(
        "/api/v1/sources", json={"title": "Queue lesson", "content": content}
    ).json()

    response = client.post(f"/api/v1/sources/{source['id']}/study-cards")
    assert response.status_code == 200
    card = response.json()[0]
    assert card["question"] == "Why use durable queues?"
    assert card["answer"] == "They preserve work across restarts."
    assert card["source_id"] == source["id"]
    assert card["source_version_id"] == source["current_version_id"]
    assert content[card["start_offset"] : card["end_offset"]] == card["answer"]
    assert card["start_line"] == 3
    assert card["quote_hash"] == hashlib.sha256(card["answer"].encode()).hexdigest()

    repeated = client.post(f"/api/v1/sources/{source['id']}/study-cards").json()
    assert repeated[0]["id"] == card["id"]


def test_review_history_and_source_revision_supersede_old_cards(client, session):
    source = client.post(
        "/api/v1/sources",
        json={"title": "Storage", "uri": "lesson://storage", "content": "Q: Store?\nA: SQLite."},
    ).json()
    card = client.post(f"/api/v1/sources/{source['id']}/study-cards").json()[0]
    review = client.post(f"/api/v1/study-cards/{card['id']}/reviews", json={"rating": "good"})
    assert review.status_code == 200
    assert review.json()["previous_interval_days"] == 0
    assert review.json()["next_interval_days"] == 1

    revised = client.post(
        "/api/v1/sources",
        json={
            "title": "Storage",
            "uri": "lesson://storage",
            "content": "Q: Store locally?\nA: SQLite with backups.",
        },
    ).json()
    new_card = client.post(f"/api/v1/sources/{revised['id']}/study-cards").json()[0]
    assert new_card["source_version_id"] == revised["current_version_id"]
    assert (
        client.post(
            f"/api/v1/study-cards/{card['id']}/reviews", json={"rating": "easy"}
        ).status_code
        == 409
    )
    assert [item["id"] for item in client.get("/api/v1/study-cards").json()] == [new_card["id"]]
    assert session.scalar(select(func.count()).select_from(StudyReview)) == 1


def test_study_failures_scope_and_deletion_are_explicit(client, session):
    source = client.post(
        "/api/v1/sources", json={"title": "No cards", "content": "ordinary prose"}
    ).json()
    failure = client.post(f"/api/v1/sources/{source['id']}/study-cards")
    assert failure.status_code == 422
    assert "Q: and A:" in failure.json()["detail"]

    lesson = client.post(
        "/api/v1/sources", json={"title": "Lesson", "content": "Q: What?\nA: Evidence."}
    ).json()
    card = client.post(f"/api/v1/sources/{lesson['id']}/study-cards").json()[0]
    client.post(f"/api/v1/study-cards/{card['id']}/reviews", json={"rating": "hard"})
    impact = client.get(f"/api/v1/sources/{lesson['id']}/deletion-impact").json()
    assert impact["study_cards"] == 1
    assert impact["study_reviews"] == 1
    assert client.delete(f"/api/v1/sources/{lesson['id']}").status_code == 204
    assert session.scalar(select(func.count()).select_from(StudyCard)) == 0
    assert session.scalar(select(func.count()).select_from(StudyReview)) == 0
