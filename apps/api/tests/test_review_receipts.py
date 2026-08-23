import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_reviews import refresh_decision_reviews
from proofline.evidence_packages import atomic_write_package, build_decision_package
from proofline.ingestion import ingest_source
from proofline.models import Decision, DecisionReview
from proofline.review_receipts import (
    REVIEW_RECEIPT_SCHEMA,
    ReviewReceiptError,
    build_review_receipt,
    verify_review_receipt,
)
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _review(**overrides):
    values = {
        "id": "00000000-0000-0000-0000-000000000101",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "decision_id": "00000000-0000-0000-0000-000000000102",
        "evidence_id": "00000000-0000-0000-0000-000000000103",
        "cited_source_version_id": "00000000-0000-0000-0000-000000000104",
        "current_source_version_id": "00000000-0000-0000-0000-000000000105",
        "finding_fingerprint": "a" * 64,
        "anchor_state": "changed",
        "policy_hash": "b" * 64,
        "state": "open",
        "resolution": None,
        "opened_at": datetime(2026, 8, 23, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 23, tzinfo=UTC),
        "closed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _receipt():
    return build_review_receipt(
        _review(),
        "c" * 64,
        cited_content_sha256="d" * 64,
        current_content_sha256="e" * 64,
    )


def test_review_receipt_is_canonical_content_free_and_verifiable():
    first = _receipt()
    second = _receipt()

    assert first == second
    assert first["schema"] == REVIEW_RECEIPT_SCHEMA
    report = verify_review_receipt(first)
    assert report == {
        "valid": True,
        "schema": REVIEW_RECEIPT_SCHEMA,
        "review_id": first["review_id"],
        "receipt_hash": first["receipt_hash"],
        "dep_root_hash": first["dep_root_hash"],
    }
    serialized = json.dumps(first, sort_keys=True)
    assert "quote" not in serialized
    assert "requirement text" not in serialized


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("finding_fingerprint", "0" * 64, "receipt_hash_mismatch"),
        ("cited_content_sha256", "0" * 64, "receipt_hash_mismatch"),
        ("current_content_sha256", "0" * 64, "receipt_hash_mismatch"),
        (
            "current_source_version_id",
            "00000000-0000-0000-0000-000000000106",
            "receipt_hash_mismatch",
        ),
        ("anchor_state", "unknown", "anchor_state_invalid"),
        ("policy_sha256", "short", "policy_hash_invalid"),
        ("state", "unknown", "review_state_invalid"),
        ("opened_at", "not-a-time", "timestamp_invalid"),
        ("dep_root_hash", "short", "dep_root_hash_invalid"),
        ("receipt_hash", "0" * 64, "receipt_hash_mismatch"),
    ],
)
def test_review_receipt_rejects_mutations_with_stable_codes(field, value, code):
    receipt = copy.deepcopy(_receipt())
    receipt[field] = value

    with pytest.raises(ReviewReceiptError, match=f"^{code}$"):
        verify_review_receipt(receipt)


def test_terminal_receipt_requires_resolution_and_closed_timestamp():
    invalid = _receipt()
    invalid["state"] = "resolved"

    with pytest.raises(ReviewReceiptError, match="^resolution_invalid$"):
        verify_review_receipt(invalid)


def test_terminal_receipt_accepts_closed_before_final_row_update():
    review = _review(
        state="resolved",
        resolution="reanchored",
        opened_at=datetime(2026, 8, 23, 0, 0, tzinfo=UTC),
        closed_at=datetime(2026, 8, 23, 0, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 23, 0, 2, tzinfo=UTC),
    )

    receipt = build_review_receipt(
        review,
        "c" * 64,
        cited_content_sha256="d" * 64,
        current_content_sha256="e" * 64,
    )

    assert verify_review_receipt(receipt)["valid"] is True


def test_review_receipt_cli_verifies_dep_and_exports_content_free_receipt(
    session, tmp_path, monkeypatch, capsys
):
    source, _created = ingest_source(
        session,
        SourceCreate(
            title="Requirement",
            uri="file:///requirement.md",
            content="Decision: Use SQLite for durable local state.\n",
        ),
    )
    decision = session.scalar(select(Decision).where(Decision.source_id == source.id))
    assert decision is not None
    decision.status = "accepted"
    session.commit()
    package = build_decision_package(session, decision.id)
    package_path = tmp_path / "decision.json"
    atomic_write_package(package_path, package)

    ingest_source(
        session,
        SourceCreate(
            title="Requirement revised",
            uri="file:///requirement.md",
            content="Decision: Use PostgreSQL for shared hosted state.\n",
        ),
    )
    refresh_decision_reviews(session, workspace_id=source.workspace_id)
    review = session.scalar(select(DecisionReview).where(DecisionReview.decision_id == decision.id))
    assert review is not None
    session.commit()
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    monkeypatch.setattr(cli_module, "initialize_database", lambda: None)
    output = tmp_path / "review-receipt.json"

    main(
        [
            "export-review-receipt",
            review.id,
            "--package",
            str(package_path),
            "--output",
            str(output),
        ]
    )
    exported = json.loads(capsys.readouterr().out)
    assert exported["review_id"] == review.id
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["dep_root_hash"] == package["manifest"]["root_hash"]
    assert "SQLite" not in json.dumps(document)
    assert "PostgreSQL" not in json.dumps(document)

    main(["verify-review-receipt", str(output)])
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_review_receipt_cli_rejects_package_for_another_decision(session, tmp_path, monkeypatch):
    source, _created = ingest_source(
        session,
        SourceCreate(
            title="Requirement",
            uri="file:///requirement.md",
            content="Decision: Use SQLite.\nDecision: Keep data local.\n",
        ),
    )
    decisions = list(session.scalars(select(Decision).where(Decision.source_id == source.id)))
    assert len(decisions) == 2
    decisions[0].status = "accepted"
    session.commit()
    wrong_package = build_decision_package(session, decisions[1].id)
    package_path = tmp_path / "wrong.json"
    atomic_write_package(package_path, wrong_package)
    ingest_source(
        session,
        SourceCreate(
            title="Requirement revised",
            uri="file:///requirement.md",
            content="Decision: Use PostgreSQL.\nDecision: Keep data local.\n",
        ),
    )
    refresh_decision_reviews(session, workspace_id=source.workspace_id)
    review = session.scalar(
        select(DecisionReview).where(DecisionReview.decision_id == decisions[0].id)
    )
    assert review is not None
    session.commit()
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    monkeypatch.setattr(cli_module, "initialize_database", lambda: None)

    with pytest.raises(SystemExit, match="review receipt export failed: package_artifact_mismatch"):
        main(
            [
                "export-review-receipt",
                review.id,
                "--package",
                str(package_path),
                "--output",
                str(tmp_path / "receipt.json"),
            ]
        )
