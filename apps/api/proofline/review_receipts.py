from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import DecisionReview
from .portability import canonical_json_bytes

REVIEW_RECEIPT_SCHEMA = "proofline-decision-review-receipt-v1"
MAX_REVIEW_RECEIPT_BYTES = 1024 * 1024
HASH_FIELDS = {
    "finding_fingerprint": "fingerprint_invalid",
    "cited_content_sha256": "content_hash_invalid",
    "current_content_sha256": "content_hash_invalid",
    "policy_sha256": "policy_hash_invalid",
    "dep_root_hash": "dep_root_hash_invalid",
    "receipt_hash": "receipt_hash_invalid",
}
RECEIPT_KEYS = {
    "schema",
    "review_id",
    "workspace_id",
    "decision_id",
    "evidence_id",
    "finding_fingerprint",
    "cited_source_version_id",
    "cited_content_sha256",
    "current_source_version_id",
    "current_content_sha256",
    "anchor_state",
    "policy_sha256",
    "state",
    "resolution",
    "opened_at",
    "updated_at",
    "closed_at",
    "dep_root_hash",
    "receipt_hash",
}
ANCHOR_STATES = {"moved", "ambiguous", "changed", "deleted"}
REVIEW_STATES = {"open", "acknowledged", "resolved", "waived", "superseded"}
TERMINAL_STATES = {"resolved", "waived", "superseded"}


class ReviewReceiptError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _is_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_uuid(value: Any, code: str) -> None:
    if not isinstance(value, str):
        raise ReviewReceiptError(code)
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ReviewReceiptError(code) from exc
    if str(parsed) != value:
        raise ReviewReceiptError(code)


def _parse_timestamp(value: Any, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ReviewReceiptError("timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReviewReceiptError("timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise ReviewReceiptError("timestamp_invalid")
    return parsed.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _receipt_hash(document: dict[str, Any]) -> str:
    body = {key: value for key, value in document.items() if key != "receipt_hash"}
    return hashlib.sha256(b"proofline/review-receipt/v1\0" + canonical_json_bytes(body)).hexdigest()


def build_review_receipt(
    review: DecisionReview,
    dep_root_hash: str,
    *,
    cited_content_sha256: str,
    current_content_sha256: str,
) -> dict[str, Any]:
    document = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "review_id": review.id,
        "workspace_id": review.workspace_id,
        "decision_id": review.decision_id,
        "evidence_id": review.evidence_id,
        "finding_fingerprint": review.finding_fingerprint,
        "cited_source_version_id": review.cited_source_version_id,
        "cited_content_sha256": cited_content_sha256,
        "current_source_version_id": review.current_source_version_id,
        "current_content_sha256": current_content_sha256,
        "anchor_state": review.anchor_state,
        "policy_sha256": review.policy_hash,
        "state": review.state,
        "resolution": review.resolution,
        "opened_at": _iso(review.opened_at),
        "updated_at": _iso(review.updated_at),
        "closed_at": _iso(review.closed_at),
        "dep_root_hash": dep_root_hash,
    }
    document["receipt_hash"] = _receipt_hash(document)
    verify_review_receipt(document)
    return document


def verify_review_receipt(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != RECEIPT_KEYS:
        raise ReviewReceiptError("receipt_shape_invalid")
    if document["schema"] != REVIEW_RECEIPT_SCHEMA:
        raise ReviewReceiptError("schema_unsupported")
    for field, code in (
        ("review_id", "review_id_invalid"),
        ("workspace_id", "workspace_id_invalid"),
        ("decision_id", "decision_id_invalid"),
        ("evidence_id", "evidence_id_invalid"),
        ("cited_source_version_id", "source_version_id_invalid"),
        ("current_source_version_id", "source_version_id_invalid"),
    ):
        _require_uuid(document[field], code)
    for field, code in HASH_FIELDS.items():
        if not _is_hash(document[field]):
            raise ReviewReceiptError(code)
    if document["anchor_state"] not in ANCHOR_STATES:
        raise ReviewReceiptError("anchor_state_invalid")
    state = document["state"]
    if state not in REVIEW_STATES:
        raise ReviewReceiptError("review_state_invalid")
    resolution = document["resolution"]
    if state in TERMINAL_STATES:
        if not isinstance(resolution, str) or not resolution.strip():
            raise ReviewReceiptError("resolution_invalid")
    elif resolution is not None:
        raise ReviewReceiptError("resolution_invalid")
    opened = _parse_timestamp(document["opened_at"])
    updated = _parse_timestamp(document["updated_at"])
    closed = _parse_timestamp(document["closed_at"], nullable=True)
    if opened is None or updated is None or opened > updated:
        raise ReviewReceiptError("timestamp_invalid")
    if state in TERMINAL_STATES:
        if closed is None or opened > closed or closed > updated:
            raise ReviewReceiptError("timestamp_invalid")
    elif closed is not None:
        raise ReviewReceiptError("timestamp_invalid")
    if document["receipt_hash"] != _receipt_hash(document):
        raise ReviewReceiptError("receipt_hash_mismatch")
    return {
        "valid": True,
        "schema": REVIEW_RECEIPT_SCHEMA,
        "review_id": document["review_id"],
        "receipt_hash": document["receipt_hash"],
        "dep_root_hash": document["dep_root_hash"],
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewReceiptError("duplicate_json_key")
        result[key] = value
    return result


def load_and_verify_review_receipt(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        data = path.read_bytes()
        if len(data) > MAX_REVIEW_RECEIPT_BYTES:
            raise ReviewReceiptError("receipt_too_large")
        document = json.loads(data, object_pairs_hook=_unique_object)
    except ReviewReceiptError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewReceiptError("receipt_unreadable") from exc
    return document, verify_review_receipt(document)
