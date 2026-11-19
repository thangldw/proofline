import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from proofline.attestations import (
    REVOCATION_SCHEMA,
    AttestationError,
    build_signed_attestation,
    load_revoked_key_ids,
    verify_signed_attestation,
)
from proofline.cli import main

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = {"root_hash": "a" * 64, "artifact_id": "00000000-0000-0000-0000-000000000101"}
KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def _signed():
    return build_signed_attestation(
        package_report=PACKAGE,
        review_report=None,
        private_key=KEY,
        issued_at=datetime(2026, 8, 23, tzinfo=UTC),
    )


def _write(path, entries, schema=REVOCATION_SCHEMA):
    path.write_text(json.dumps({"schema": schema, "revoked": entries}), encoding="utf-8")
    return path


def test_revoked_key_is_rejected_whatever_issued_at_claims():
    document = _signed()
    assert verify_signed_attestation(document, KEY.public_key())["valid"] is True
    with pytest.raises(AttestationError) as caught:
        verify_signed_attestation(
            document, KEY.public_key(), revoked_key_ids=frozenset({document["key_id"]})
        )
    assert caught.value.code == "key_revoked"
    other = frozenset({"c" * 64})
    assert verify_signed_attestation(document, KEY.public_key(), revoked_key_ids=other)["valid"]


def test_revocation_list_loader_is_strict(tmp_path):
    ok = _write(
        tmp_path / "ok.json", [{"key_id": "d" * 64, "reason": "lost"}, {"key_id": "e" * 64}]
    )
    assert load_revoked_key_ids(ok) == frozenset({"d" * 64, "e" * 64})
    cases = {
        "wrong_schema": _write(tmp_path / "a.json", [], schema="other"),
        "bad_entry": _write(tmp_path / "b.json", [{"key_id": "nothex"}]),
        "not_object": _write(tmp_path / "c.json", ["x"]),
    }
    for path in cases.values():
        with pytest.raises(AttestationError):
            load_revoked_key_ids(path)
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(AttestationError, match="revocations_unreadable"):
        load_revoked_key_ids(broken)
    dup = tmp_path / "dup.json"
    dup.write_text('{"schema": "x", "schema": "y"}', encoding="utf-8")
    with pytest.raises(AttestationError):
        load_revoked_key_ids(dup)
    with pytest.raises(AttestationError, match="revocations_unreadable"):
        load_revoked_key_ids(tmp_path / "missing.json")


def test_cli_verify_attestation_honours_revocations(tmp_path, capsys):
    private_path, public_path = tmp_path / "private.pem", tmp_path / "public.pem"
    output = tmp_path / "attestation.json"
    package = ROOT / "spec/decision-evidence-package/v1/test-vectors/valid-minimal.json"
    main(
        [
            "generate-attestation-key",
            "--private-key",
            str(private_path),
            "--public-key",
            str(public_path),
        ]
    )
    key_id = json.loads(capsys.readouterr().out)["key_id"]
    main(
        [
            "attest",
            "--package",
            str(package),
            "--private-key",
            str(private_path),
            "--output",
            str(output),
        ]
    )
    capsys.readouterr()
    revocations = _write(tmp_path / "revoked.json", [{"key_id": key_id}])
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "verify-attestation",
                str(output),
                "--public-key",
                str(public_path),
                "--package",
                str(package),
                "--revocations",
                str(revocations),
            ]
        )
    assert "key_revoked" in str(caught.value)
    unrelated = _write(tmp_path / "other.json", [{"key_id": "f" * 64}])
    main(
        [
            "verify-attestation",
            str(output),
            "--public-key",
            str(public_path),
            "--package",
            str(package),
            "--revocations",
            str(unrelated),
        ]
    )
    assert json.loads(capsys.readouterr().out)["valid"] is True
