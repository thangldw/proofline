from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from .attestations import (
    MAX_ATTESTATION_BYTES,
    SIGNATURE_ALGORITHM,
    AttestationError,
    _is_hash,
    _iso,
    _issued_at,
    _key_id,
    _unique_object,
)
from .decision_enforce import check_enforcement
from .decision_ledger import current_state, read_ledger
from .models import Decision
from .portability import canonical_json_bytes

RELEASE_SCHEMA = "proofline-release-attestation-v1"
STATEMENT_SCHEMA = "proofline-release-statement-v1"
RELEASE_DOMAIN = b"proofline/release-attestation/v1\0"
ENVELOPE_KEYS = {"schema", "algorithm", "key_id", "statement", "signature"}
STATEMENT_KEYS = {
    "schema",
    "algorithm",
    "key_id",
    "issued_at",
    "commit",
    "tag",
    "dirty",
    "compliant",
    "decisions",
    "ledger_head",
}
DECISION_KEYS = {"approved", "stale", "enforcement_findings", "digest"}
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
APPROVED = ("active", "accepted")


def _git(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AttestationError("git_unavailable") from exc
    if completed.returncode != 0:
        raise AttestationError("git_failed")
    return completed.stdout.strip()


def collect_state(
    session: Session, root: Path, ledger: Path | None, *, tag: str | None
) -> dict[str, Any]:
    """Content-free facts about the decisions at the checked-out commit."""

    if tag is not None and not _TAG.match(tag):
        raise AttestationError("tag_invalid")
    commit = _git(root, "rev-parse", "HEAD")
    if not _COMMIT.match(commit):
        raise AttestationError("git_failed")
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no"))
    approved, _reasons, stale_ids = current_state(session)
    findings = len(check_enforcement(session, root))
    rows = session.execute(
        select(Decision.id, Decision.status, Decision.source_version_id).where(
            Decision.status.in_(APPROVED)
        )
    ).all()
    digest = hashlib.sha256(
        "\n".join(sorted(f"{row[0]}:{row[1]}:{row[2]}" for row in rows)).encode("utf-8")
    ).hexdigest()
    entries = read_ledger(ledger) if ledger is not None else []
    return {
        "commit": commit,
        "tag": tag,
        "dirty": dirty,
        "compliant": not stale_ids and findings == 0 and not dirty,
        "decisions": {
            "approved": approved,
            "stale": len(stale_ids),
            "enforcement_findings": findings,
            "digest": digest,
        },
        "ledger_head": entries[-1].hash if entries else None,
    }


def build_release_attestation(
    state: dict[str, Any], private_key: Ed25519PrivateKey, issued_at: datetime
) -> dict[str, Any]:
    key_id = _key_id(private_key.public_key())
    statement = {
        "schema": STATEMENT_SCHEMA,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "issued_at": _iso(issued_at),
        **state,
    }
    signature = private_key.sign(RELEASE_DOMAIN + canonical_json_bytes(statement))
    envelope = {
        "schema": RELEASE_SCHEMA,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "statement": statement,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    verify_release_attestation(envelope, private_key.public_key())
    return envelope


def _count(value: Any, code: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AttestationError(code)


def _validate(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != ENVELOPE_KEYS:
        raise AttestationError("attestation_shape_invalid")
    if document["schema"] != RELEASE_SCHEMA:
        raise AttestationError("schema_unsupported")
    if document["algorithm"] != SIGNATURE_ALGORITHM:
        raise AttestationError("algorithm_unsupported")
    if not _is_hash(document["key_id"]):
        raise AttestationError("key_id_invalid")
    statement = document["statement"]
    if not isinstance(statement, dict) or set(statement) != STATEMENT_KEYS:
        raise AttestationError("statement_shape_invalid")
    if statement["schema"] != STATEMENT_SCHEMA:
        raise AttestationError("statement_schema_unsupported")
    if statement["algorithm"] != document["algorithm"] or statement["key_id"] != document["key_id"]:
        raise AttestationError("key_id_mismatch")
    _issued_at(statement["issued_at"])
    if not isinstance(statement["commit"], str) or not _COMMIT.match(statement["commit"]):
        raise AttestationError("commit_invalid")
    tag = statement["tag"]
    if tag is not None and (not isinstance(tag, str) or not _TAG.match(tag)):
        raise AttestationError("tag_invalid")
    if not isinstance(statement["dirty"], bool) or not isinstance(statement["compliant"], bool):
        raise AttestationError("flags_invalid")
    decisions = statement["decisions"]
    if not isinstance(decisions, dict) or set(decisions) != DECISION_KEYS:
        raise AttestationError("decisions_invalid")
    for key in ("approved", "stale", "enforcement_findings"):
        _count(decisions[key], "decisions_invalid")
    if not _is_hash(decisions["digest"]):
        raise AttestationError("decisions_invalid")
    head = statement["ledger_head"]
    if head is not None and not _is_hash(head):
        raise AttestationError("ledger_head_invalid")
    clean = decisions["stale"] == 0 and decisions["enforcement_findings"] == 0
    if statement["compliant"] != (clean and not statement["dirty"]):
        raise AttestationError("compliant_inconsistent")
    return statement


def verify_release_attestation(
    document: Any,
    public_key: Ed25519PublicKey,
    *,
    revoked_key_ids: frozenset[str] = frozenset(),
    expected_commit: str | None = None,
) -> dict[str, Any]:
    statement = _validate(document)
    if not isinstance(public_key, Ed25519PublicKey):
        raise AttestationError("public_key_type_invalid")
    if document["key_id"] != _key_id(public_key):
        raise AttestationError("key_id_mismatch")
    if document["key_id"] in revoked_key_ids:
        raise AttestationError("key_revoked")
    try:
        signature = base64.b64decode(str(document["signature"]), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttestationError("signature_encoding_invalid") from exc
    if len(signature) != 64:
        raise AttestationError("signature_encoding_invalid")
    try:
        public_key.verify(signature, RELEASE_DOMAIN + canonical_json_bytes(statement))
    except InvalidSignature as exc:
        raise AttestationError("signature_invalid") from exc
    if expected_commit is not None and statement["commit"] != expected_commit:
        raise AttestationError("commit_mismatch")
    return {
        "valid": True,
        "schema": RELEASE_SCHEMA,
        "key_id": document["key_id"],
        "commit": statement["commit"],
        "tag": statement["tag"],
        "compliant": statement["compliant"],
        "approved": statement["decisions"]["approved"],
        "stale": statement["decisions"]["stale"],
        "enforcement_findings": statement["decisions"]["enforcement_findings"],
        "ledger_head": statement["ledger_head"],
        "issued_at": statement["issued_at"],
    }


def load_and_verify_release(
    path: Path,
    public_key: Ed25519PublicKey,
    *,
    revoked_key_ids: frozenset[str] = frozenset(),
    expected_commit: str | None = None,
) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        if len(data) > MAX_ATTESTATION_BYTES:
            raise AttestationError("attestation_too_large")
        document = json.loads(data, object_pairs_hook=_unique_object)
    except AttestationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttestationError("attestation_unreadable") from exc
    return verify_release_attestation(
        document, public_key, revoked_key_ids=revoked_key_ids, expected_commit=expected_commit
    )
