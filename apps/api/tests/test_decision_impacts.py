import json
from datetime import UTC, datetime, timedelta

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_impacts import compute_decision_impacts
from proofline.decision_reviews import refresh_decision_reviews
from proofline.ingestion import ingest_source
from proofline.models import Decision, DecisionRelation, DecisionReview
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ORIGINAL = "# Root\n\nDecision: Keep local writes.\nReason: deterministic recovery."
CHANGED = "# Root\n\nDecision: Use remote writes.\nReason: shared recovery."
AS_OF = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def _decision(session, name: str, workspace_id: str | None = None) -> Decision:
    source_values = {
        "title": name,
        "uri": f"file:///{name}.md",
        "content": f"Decision: {name}.",
    }
    if workspace_id is not None:
        source_values["workspace_id"] = workspace_id
    source, _created = ingest_source(
        session,
        SourceCreate(**source_values),
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
    return decision


def _root_with_review(session) -> tuple[Decision, DecisionReview, str]:
    source, _created = ingest_source(
        session,
        SourceCreate(title="root", uri="file:///root-impact.md", content=ORIGINAL),
    )
    root = session.scalar(
        select(Decision).where(
            Decision.source_version_id == source.current_version_id,
            Decision.kind == "decision",
        )
    )
    assert root is not None
    root.status = "accepted"
    session.commit()
    source, _created = ingest_source(
        session,
        SourceCreate(title="root", uri=source.uri, content=CHANGED),
    )
    refresh_decision_reviews(session, workspace_id=source.workspace_id)
    session.commit()
    review = session.scalar(select(DecisionReview).where(DecisionReview.decision_id == root.id))
    assert review is not None
    return root, review, source.workspace_id


def _relation(
    session,
    relation_id: str,
    source: Decision,
    target: Decision,
    kind: str,
    *,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> None:
    session.add(
        DecisionRelation(
            id=relation_id,
            source_decision_id=source.id,
            target_decision_id=target.id,
            kind=kind,
            valid_from=valid_from,
            valid_to=valid_to,
        )
    )
    session.commit()


def test_impact_propagates_target_to_source_only_through_dependency_kinds(session):
    root, review, workspace_id = _root_with_review(session)
    based = _decision(session, "based")
    implemented = _decision(session, "implemented")
    considered = _decision(session, "considered")
    contradicted = _decision(session, "contradicted")
    superseding = _decision(session, "superseding")
    _relation(session, "00000000-0000-0000-0000-000000000011", based, root, "based_on")
    _relation(session, "00000000-0000-0000-0000-000000000012", implemented, based, "implements")
    _relation(session, "00000000-0000-0000-0000-000000000013", considered, root, "considered")
    _relation(session, "00000000-0000-0000-0000-000000000014", contradicted, root, "contradicts")
    _relation(session, "00000000-0000-0000-0000-000000000015", superseding, root, "supersedes")

    findings = compute_decision_impacts(session, workspace_id=workspace_id, as_of=AS_OF)

    assert [item.impacted_decision_id for item in findings] == [based.id, implemented.id]
    assert findings[0].root_review_id == review.id
    assert findings[0].decision_path == (root.id, based.id)
    assert findings[0].relation_kinds == ("based_on",)
    assert findings[1].decision_path == (root.id, based.id, implemented.id)
    assert findings[1].relation_kinds == ("based_on", "implements")
    assert findings[1].depth == 2
    assert len(findings[1].fingerprint) == 64
    assert findings[1].model_dump()["decision_path"] == [root.id, based.id, implemented.id]


def test_impact_is_cycle_safe_and_chooses_canonical_shortest_path(session):
    root, _review, workspace_id = _root_with_review(session)
    left = _decision(session, "left")
    right = _decision(session, "right")
    leaf = _decision(session, "leaf")
    _relation(session, "00000000-0000-0000-0000-000000000021", left, root, "based_on")
    _relation(session, "00000000-0000-0000-0000-000000000022", right, root, "based_on")
    _relation(session, "00000000-0000-0000-0000-000000000024", leaf, left, "implements")
    _relation(session, "00000000-0000-0000-0000-000000000023", leaf, right, "implements")
    _relation(session, "00000000-0000-0000-0000-000000000025", root, leaf, "based_on")

    first = compute_decision_impacts(session, workspace_id=workspace_id, as_of=AS_OF)
    second = compute_decision_impacts(session, workspace_id=workspace_id, as_of=AS_OF)
    leaf_finding = next(item for item in first if item.impacted_decision_id == leaf.id)

    assert leaf_finding.relation_path == (
        "00000000-0000-0000-0000-000000000021",
        "00000000-0000-0000-0000-000000000024",
    )
    assert [item.fingerprint for item in first] == [item.fingerprint for item in second]
    assert root.id not in [item.impacted_decision_id for item in first]


def test_impact_honors_temporal_bounds_and_current_decision_status(session):
    root, _review, workspace_id = _root_with_review(session)
    expired = _decision(session, "expired")
    future = _decision(session, "future")
    obsolete = _decision(session, "obsolete")
    active = _decision(session, "active")
    obsolete.status = "obsolete"
    session.commit()
    _relation(
        session,
        "00000000-0000-0000-0000-000000000031",
        expired,
        root,
        "based_on",
        valid_to=AS_OF - timedelta(seconds=1),
    )
    _relation(
        session,
        "00000000-0000-0000-0000-000000000032",
        future,
        root,
        "based_on",
        valid_from=AS_OF + timedelta(seconds=1),
    )
    _relation(session, "00000000-0000-0000-0000-000000000033", obsolete, root, "based_on")
    _relation(session, "00000000-0000-0000-0000-000000000034", active, root, "based_on")

    findings = compute_decision_impacts(session, workspace_id=workspace_id, as_of=AS_OF)

    assert [item.impacted_decision_id for item in findings] == [active.id]
    root.status = "obsolete"
    session.commit()
    assert compute_decision_impacts(session, workspace_id=workspace_id, as_of=AS_OF) == []


def test_impact_disappears_when_review_closes_and_is_workspace_scoped(session):
    root, review, workspace_id = _root_with_review(session)
    dependent = _decision(session, "dependent")
    _relation(session, "00000000-0000-0000-0000-000000000041", dependent, root, "based_on")

    assert len(compute_decision_impacts(session, workspace_id=workspace_id, as_of=AS_OF)) == 1
    assert (
        compute_decision_impacts(
            session,
            workspace_id="00000000-0000-0000-0000-000000000099",
            as_of=AS_OF,
        )
        == []
    )
    review.state = "resolved"
    review.resolution = "source_restored"
    review.closed_at = AS_OF
    review.updated_at = AS_OF
    session.commit()
    assert compute_decision_impacts(session, workspace_id=workspace_id, as_of=AS_OF) == []


def test_impact_api_lists_summary_and_enforces_workspace_and_timezone(client, session):
    root, review, workspace_id = _root_with_review(session)
    dependent = _decision(session, "api-dependent")
    _relation(session, "00000000-0000-0000-0000-000000000051", dependent, root, "based_on")

    response = client.get("/api/v1/decision-impacts", params={"as_of": AS_OF.isoformat()})

    assert response.status_code == 200
    assert response.json()[0]["root_review_id"] == review.id
    assert response.json()[0]["impacted_decision_id"] == dependent.id
    assert "quote" not in json.dumps(response.json(), sort_keys=True)
    summary = client.get("/api/v1/decision-impacts/summary", params={"as_of": AS_OF.isoformat()})
    assert summary.json() == {
        "root_review_count": 1,
        "impacted_decision_count": 1,
        "finding_count": 1,
        "max_depth": 1,
        "evaluated_at": AS_OF.isoformat().replace("+00:00", "Z"),
    }
    assert (
        client.get("/api/v1/decision-impacts", params={"as_of": "2026-08-23T12:00:00"}).status_code
        == 422
    )
    other_workspace = client.post(
        "/api/v1/workspaces", json={"slug": "impact-other", "title": "Impact Other"}
    ).json()
    assert (
        client.get(
            "/api/v1/decision-impacts",
            headers={"X-Proofline-Workspace-ID": other_workspace["id"]},
        ).json()
        == []
    )
    assert workspace_id != other_workspace["id"]


def test_check_impacts_cli_json_sarif_and_exit_codes(session, monkeypatch, tmp_path, capsys):
    root, _review, workspace_id = _root_with_review(session)
    dependent = _decision(session, "cli-dependent")
    _relation(session, "00000000-0000-0000-0000-000000000061", dependent, root, "implements")
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)

    with pytest.raises(SystemExit) as blocked:
        main(["check-impacts", "--format", "json", "--as-of", AS_OF.isoformat()])

    assert blocked.value.code == 1
    document = json.loads(capsys.readouterr().out)
    assert document["valid"] is False
    assert document["finding_count"] == 1
    assert document["findings"][0]["impacted_decision_id"] == dependent.id
    sarif_path = tmp_path / "impact.sarif"
    with pytest.raises(SystemExit) as sarif_blocked:
        main(
            [
                "check-impacts",
                "--format",
                "sarif",
                "--as-of",
                AS_OF.isoformat(),
                "--output",
                str(sarif_path),
            ]
        )
    assert sarif_blocked.value.code == 1
    sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
    assert sarif["runs"][0]["results"][0]["ruleId"] == "proofline/transitive-impact"
    assert "cli-dependent" not in json.dumps(sarif, sort_keys=True)
    review = session.scalar(
        select(DecisionReview).where(DecisionReview.workspace_id == workspace_id)
    )
    assert review is not None
    review.state = "resolved"
    review.resolution = "source_restored"
    review.closed_at = AS_OF
    review.updated_at = AS_OF
    session.commit()

    main(["check-impacts", "--format", "sarif", "--as-of", AS_OF.isoformat()])

    empty_sarif = json.loads(capsys.readouterr().out)
    assert empty_sarif["runs"][0]["properties"]["evaluatedAt"] == AS_OF.isoformat()
    main(["check-impacts", "--as-of", AS_OF.isoformat()])

    assert capsys.readouterr().out.strip().splitlines() == [
        f"Evaluated at {AS_OF.isoformat()}",
        "No decisions are transitively impacted.",
    ]


def test_check_impacts_cli_fails_closed_on_invalid_review_provenance(session, monkeypatch, capsys):
    _root, review, _workspace_id = _root_with_review(session)
    review.finding_fingerprint = "0" * 64
    session.commit()
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)

    with pytest.raises(SystemExit) as invalid:
        main(["check-impacts", "--as-of", AS_OF.isoformat()])

    assert invalid.value.code == 2
    assert (
        capsys.readouterr().err.strip()
        == "impact check failed: decision_review_fingerprint_invalid"
    )


def test_check_impacts_cli_rejects_naive_as_of_before_database(monkeypatch, capsys):
    def database_must_not_open():
        raise AssertionError("database opened before timestamp validation")

    monkeypatch.setattr(cli_module, "SessionLocal", database_must_not_open)
    with pytest.raises(SystemExit) as invalid:
        main(["check-impacts", "--as-of", "2026-08-23T12:00:00"])

    assert invalid.value.code == 2
    assert capsys.readouterr().err.strip() == "impact check failed: as_of_timezone_required"
