import base64
import copy
import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import proofline.cli as cli_module
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from proofline.attestations import (
    ATTESTATION_SCHEMA,
    AttestationError,
    atomic_write_attestation,
    build_signed_attestation,
    generate_attestation_keypair,
    load_and_verify_attestation,
    load_attestation_private_key,
    load_attestation_public_key,
    verify_signed_attestation,
)
from proofline.cli import main

ISSUED_AT = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
PACKAGE = {
    "root_hash": "a" * 64,
    "artifact_id": "00000000-0000-0000-0000-000000000101",
}
REVIEW = {
    "receipt_hash": "b" * 64,
    "review_id": "00000000-0000-0000-0000-000000000102",
    "dep_root_hash": "a" * 64,
}
ROOT = Path(__file__).resolve().parents[3]


def _private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def _attestation():
    return build_signed_attestation(
        package_report=PACKAGE,
        review_report=REVIEW,
        private_key=_private_key(),
        issued_at=ISSUED_AT,
    )


def test_attestation_is_deterministic_strict_and_content_free():
    first = _attestation()
    second = _attestation()

    assert first == second
    assert first["schema"] == ATTESTATION_SCHEMA
    report = verify_signed_attestation(first, _private_key().public_key())
    assert report == {
        "valid": True,
        "schema": ATTESTATION_SCHEMA,
        "algorithm": "ed25519",
        "key_id": first["key_id"],
        "package_root_hash": PACKAGE["root_hash"],
        "artifact_id": PACKAGE["artifact_id"],
        "review_receipt_hash": REVIEW["receipt_hash"],
        "issued_at": "2026-08-23T12:00:00+00:00",
    }
    serialized = json.dumps(first, sort_keys=True)
    assert "PRIVATE KEY" not in serialized
    assert "quote" not in serialized
    assert "source content" not in serialized


def test_attestation_rejects_wrong_key_tampering_and_invalid_base64():
    envelope = _attestation()
    wrong_key = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(AttestationError, match="^key_id_mismatch$"):
        verify_signed_attestation(envelope, wrong_key)

    tampered = copy.deepcopy(envelope)
    tampered["statement"]["package"]["root_hash"] = "c" * 64
    with pytest.raises(AttestationError, match="^signature_invalid$"):
        verify_signed_attestation(tampered, _private_key().public_key())

    invalid_signature = copy.deepcopy(envelope)
    signature = base64.b64decode(invalid_signature["signature"], validate=True)
    invalid_signature["signature"] = base64.b64encode(
        bytes([signature[0] ^ 1]) + signature[1:]
    ).decode()
    with pytest.raises(AttestationError, match="^signature_invalid$"):
        verify_signed_attestation(invalid_signature, _private_key().public_key())

    malformed = copy.deepcopy(envelope)
    malformed["signature"] = "not/base64!"
    with pytest.raises(AttestationError, match="^signature_encoding_invalid$"):
        verify_signed_attestation(malformed, _private_key().public_key())


def test_attestation_rejects_receipt_bound_to_another_package():
    with pytest.raises(AttestationError, match="^subject_link_invalid$"):
        build_signed_attestation(
            package_report=PACKAGE,
            review_report={**REVIEW, "dep_root_hash": "d" * 64},
            private_key=_private_key(),
            issued_at=ISSUED_AT,
        )


def test_attestation_verifies_supplied_subject_reports():
    envelope = _attestation()
    public_key = _private_key().public_key()

    assert (
        verify_signed_attestation(
            envelope,
            public_key,
            package_report=PACKAGE,
            review_report=REVIEW,
        )["valid"]
        is True
    )
    with pytest.raises(AttestationError, match="^package_subject_mismatch$"):
        verify_signed_attestation(
            envelope,
            public_key,
            package_report={**PACKAGE, "root_hash": "e" * 64},
        )
    with pytest.raises(AttestationError, match="^review_subject_mismatch$"):
        verify_signed_attestation(
            envelope,
            public_key,
            package_report=PACKAGE,
            review_report={**REVIEW, "receipt_hash": "f" * 64},
        )


def test_attestation_loader_rejects_duplicate_keys_oversize_and_shape(tmp_path):
    public_key = _private_key().public_key()
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
    with pytest.raises(AttestationError, match="^duplicate_json_key$"):
        load_and_verify_attestation(duplicate, public_key)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(AttestationError, match="^attestation_too_large$"):
        load_and_verify_attestation(oversized, public_key)

    malformed = tmp_path / "malformed.json"
    malformed.write_text("[]", encoding="utf-8")
    with pytest.raises(AttestationError, match="^attestation_shape_invalid$"):
        load_and_verify_attestation(malformed, public_key)


def test_key_generation_permissions_loading_and_no_overwrite(tmp_path):
    private_path = tmp_path / "keys" / "attestation-private.pem"
    public_path = tmp_path / "keys" / "attestation-public.pem"

    report = generate_attestation_keypair(private_path, public_path)

    assert len(report["key_id"]) == 64
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    assert "PRIVATE KEY" in private_path.read_text(encoding="ascii")
    assert "PUBLIC KEY" in public_path.read_text(encoding="ascii")
    private_before = private_path.read_bytes()
    with pytest.raises(AttestationError, match="^output_exists$"):
        generate_attestation_keypair(private_path, public_path)
    assert private_path.read_bytes() == private_before
    assert load_attestation_private_key(private_path).public_key().public_bytes_raw() == (
        load_attestation_public_key(public_path).public_bytes_raw()
    )


def test_atomic_attestation_output_refuses_overwrite_and_loads(tmp_path):
    output = tmp_path / "attestation.json"
    envelope = _attestation()

    atomic_write_attestation(output, envelope)

    before = output.read_bytes()
    with pytest.raises(AttestationError, match="^output_exists$"):
        atomic_write_attestation(output, envelope)
    assert output.read_bytes() == before
    _document, report = load_and_verify_attestation(output, _private_key().public_key())
    assert report["valid"] is True


def test_tracked_ed25519_conformance_vector_matches_implementation():
    vector_dir = ROOT / "spec/signed-attestation/v1/test-vectors"
    document, report = load_and_verify_attestation(
        vector_dir / "valid-ed25519.json",
        load_attestation_public_key(vector_dir / "valid-ed25519-public.pem"),
    )

    assert document == _attestation()
    assert report["key_id"] == "56475aa75463474c0285df5dbf2bcab73da651358839e9b77481b2eab107708c"


def test_attestation_cli_generates_signs_and_verifies_exact_package(tmp_path, capsys):
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
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
    key_report = json.loads(capsys.readouterr().out)
    assert len(key_report["key_id"]) == 64
    main(
        [
            "attest",
            "--package",
            str(package),
            "--private-key",
            str(private_path),
            "--issued-at",
            ISSUED_AT.isoformat(),
            "--output",
            str(output),
        ]
    )
    sign_report = json.loads(capsys.readouterr().out)
    assert (
        sign_report["package_root_hash"]
        == "742b23b7338c0b5e66cd78a0a2aab394ad3bf6af8470416f80554305f1787da5"
    )
    main(
        [
            "verify-attestation",
            str(output),
            "--public-key",
            str(public_path),
            "--package",
            str(package),
        ]
    )
    verify_report = json.loads(capsys.readouterr().out)
    assert verify_report["valid"] is True
    assert verify_report["key_id"] == key_report["key_id"]


def test_attestation_cli_rejects_mismatched_review_receipt(tmp_path):
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    generate_attestation_keypair(private_path, public_path)
    package = ROOT / "spec/decision-evidence-package/v1/test-vectors/valid-minimal.json"
    receipt = ROOT / "spec/decision-review-receipt/v1/test-vectors/valid-minimal.json"

    with pytest.raises(SystemExit, match="attestation failed: subject_link_invalid"):
        main(
            [
                "attest",
                "--package",
                str(package),
                "--review-receipt",
                str(receipt),
                "--private-key",
                str(private_path),
                "--output",
                str(tmp_path / "invalid.json"),
            ]
        )


def test_attestation_cli_does_not_initialize_database(tmp_path, monkeypatch):
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    generate_attestation_keypair(private_path, public_path)
    package = ROOT / "spec/decision-evidence-package/v1/test-vectors/valid-minimal.json"

    monkeypatch.setattr(
        cli_module,
        "initialize_database",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("database opened")),
    )
    main(
        [
            "attest",
            "--package",
            str(package),
            "--private-key",
            str(private_path),
            "--output",
            str(tmp_path / "attestation.json"),
        ]
    )
