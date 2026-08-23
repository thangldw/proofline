from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .portability import canonical_json_bytes

ATTESTATION_SCHEMA = "proofline-signed-attestation-v1"
STATEMENT_SCHEMA = "proofline-attestation-statement-v1"
SIGNATURE_ALGORITHM = "ed25519"
SIGNATURE_DOMAIN = b"proofline/signed-attestation/v1\0"
MAX_ATTESTATION_BYTES = 1024 * 1024
MAX_KEY_BYTES = 64 * 1024
ENVELOPE_KEYS = {"schema", "algorithm", "key_id", "statement", "signature"}
STATEMENT_KEYS = {
    "schema",
    "algorithm",
    "key_id",
    "issued_at",
    "package",
    "review_receipt",
}
PACKAGE_KEYS = {"root_hash", "artifact_id"}
REVIEW_KEYS = {"receipt_hash", "review_id", "dep_root_hash"}
CANONICAL_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{0,5}[1-9])?Z$")


class AttestationError(RuntimeError):
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
        raise AttestationError(code)
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise AttestationError(code) from exc
    if str(parsed) != value:
        raise AttestationError(code)


def _require_nonempty_string(value: Any, code: str) -> None:
    if not isinstance(value, str) or not value:
        raise AttestationError(code)


def _issued_at(value: Any) -> datetime:
    if not isinstance(value, str) or CANONICAL_UTC_PATTERN.fullmatch(value) is None:
        raise AttestationError("issued_at_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AttestationError("issued_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AttestationError("issued_at_invalid")
    normalized = parsed.astimezone(UTC)
    if value != _iso(normalized):
        raise AttestationError("issued_at_invalid")
    return normalized


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AttestationError("issued_at_invalid")
    normalized = value.astimezone(UTC)
    rendered = normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if normalized.microsecond == 0:
        return rendered.replace(".000000Z", "Z")
    return f"{rendered[:-1].rstrip('0')}Z"


def _key_id(public_key: Ed25519PublicKey) -> str:
    return hashlib.sha256(
        public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).hexdigest()


def attestation_paths_conflict(first: Path, second: Path) -> bool:
    first_path = Path(os.path.abspath(first.expanduser()))
    second_path = Path(os.path.abspath(second.expanduser()))
    try:
        if (
            first_path.exists()
            and second_path.exists()
            and os.path.samefile(first_path, second_path)
        ):
            return True
    except OSError:
        pass
    if first_path.resolve(strict=False) == second_path.resolve(strict=False):
        return True
    first_parent = first_path.parent.resolve(strict=False)
    second_parent = second_path.parent.resolve(strict=False)
    same_parent = first_parent == second_parent
    if not same_parent:
        try:
            same_parent = os.path.samefile(first_parent, second_parent)
        except OSError:
            same_parent = False
    first_name = unicodedata.normalize("NFC", first_path.name).casefold()
    second_name = unicodedata.normalize("NFC", second_path.name).casefold()
    return same_parent and first_name == second_name


def _validate_report(report: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(report, dict) or not keys.issubset(report):
        raise AttestationError(code)
    return report


def build_signed_attestation(
    *,
    package_report: dict[str, Any],
    private_key: Ed25519PrivateKey,
    issued_at: datetime,
    review_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package = _validate_report(package_report, PACKAGE_KEYS, "package_subject_invalid")
    review = (
        _validate_report(review_report, REVIEW_KEYS, "review_subject_invalid")
        if review_report is not None
        else None
    )
    if review is not None and review["dep_root_hash"] != package["root_hash"]:
        raise AttestationError("subject_link_invalid")
    public_key = private_key.public_key()
    key_id = _key_id(public_key)
    statement = {
        "schema": STATEMENT_SCHEMA,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "issued_at": _iso(issued_at),
        "package": {
            "root_hash": package["root_hash"],
            "artifact_id": package["artifact_id"],
        },
        "review_receipt": (
            {
                "receipt_hash": review["receipt_hash"],
                "review_id": review["review_id"],
                "dep_root_hash": review["dep_root_hash"],
            }
            if review is not None
            else None
        ),
    }
    signature = private_key.sign(SIGNATURE_DOMAIN + canonical_json_bytes(statement))
    envelope = {
        "schema": ATTESTATION_SCHEMA,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "statement": statement,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    verify_signed_attestation(envelope, public_key)
    return envelope


def _validate_envelope(document: Any) -> tuple[dict[str, Any], dict[str, Any] | None, datetime]:
    if not isinstance(document, dict) or set(document) != ENVELOPE_KEYS:
        raise AttestationError("attestation_shape_invalid")
    if document["schema"] != ATTESTATION_SCHEMA:
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
    if statement["algorithm"] != document["algorithm"]:
        raise AttestationError("algorithm_mismatch")
    if statement["key_id"] != document["key_id"]:
        raise AttestationError("key_id_mismatch")
    issued_at = _issued_at(statement["issued_at"])
    package = statement["package"]
    if not isinstance(package, dict) or set(package) != PACKAGE_KEYS:
        raise AttestationError("package_subject_invalid")
    if not _is_hash(package["root_hash"]):
        raise AttestationError("package_root_hash_invalid")
    _require_nonempty_string(package["artifact_id"], "artifact_id_invalid")
    review = statement["review_receipt"]
    if review is not None:
        if not isinstance(review, dict) or set(review) != REVIEW_KEYS:
            raise AttestationError("review_subject_invalid")
        if not _is_hash(review["receipt_hash"]):
            raise AttestationError("receipt_hash_invalid")
        if not _is_hash(review["dep_root_hash"]):
            raise AttestationError("dep_root_hash_invalid")
        _require_uuid(review["review_id"], "review_id_invalid")
    return package, review, issued_at


def verify_signed_attestation(
    document: Any,
    public_key: Ed25519PublicKey,
    *,
    package_report: dict[str, Any] | None = None,
    review_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package, review, issued_at = _validate_envelope(document)
    if len(canonical_json_bytes(document)) + 1 > MAX_ATTESTATION_BYTES:
        raise AttestationError("attestation_too_large")
    if not isinstance(public_key, Ed25519PublicKey):
        raise AttestationError("public_key_type_invalid")
    if document["key_id"] != _key_id(public_key):
        raise AttestationError("key_id_mismatch")
    signature_value = document["signature"]
    if not isinstance(signature_value, str):
        raise AttestationError("signature_encoding_invalid")
    try:
        signature = base64.b64decode(signature_value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttestationError("signature_encoding_invalid") from exc
    if len(signature) != 64:
        raise AttestationError("signature_encoding_invalid")
    try:
        public_key.verify(
            signature,
            SIGNATURE_DOMAIN + canonical_json_bytes(document["statement"]),
        )
    except InvalidSignature as exc:
        raise AttestationError("signature_invalid") from exc
    if review is not None and review["dep_root_hash"] != package["root_hash"]:
        raise AttestationError("subject_link_invalid")
    if package_report is not None:
        supplied_package = _validate_report(package_report, PACKAGE_KEYS, "package_subject_invalid")
        if any(supplied_package[key] != package[key] for key in PACKAGE_KEYS):
            raise AttestationError("package_subject_mismatch")
    if review_report is not None:
        if review is None:
            raise AttestationError("review_subject_mismatch")
        supplied_review = _validate_report(review_report, REVIEW_KEYS, "review_subject_invalid")
        if any(supplied_review[key] != review[key] for key in REVIEW_KEYS):
            raise AttestationError("review_subject_mismatch")
    return {
        "valid": True,
        "schema": ATTESTATION_SCHEMA,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": document["key_id"],
        "package_root_hash": package["root_hash"],
        "artifact_id": package["artifact_id"],
        "review_receipt_hash": review["receipt_hash"] if review is not None else None,
        "issued_at": issued_at.isoformat(),
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AttestationError("duplicate_json_key")
        result[key] = value
    return result


def load_and_verify_attestation(
    path: Path,
    public_key: Ed25519PublicKey,
    *,
    package_report: dict[str, Any] | None = None,
    review_report: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        data = path.read_bytes()
        if len(data) > MAX_ATTESTATION_BYTES:
            raise AttestationError("attestation_too_large")
        document = json.loads(data, object_pairs_hook=_unique_object)
    except AttestationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttestationError("attestation_unreadable") from exc
    return document, verify_signed_attestation(
        document,
        public_key,
        package_report=package_report,
        review_report=review_report,
    )


def _read_key(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AttestationError("key_unreadable") from exc
    if len(data) > MAX_KEY_BYTES:
        raise AttestationError("key_too_large")
    return data


def load_attestation_private_key(path: Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(_read_key(path), password=None)
    except (TypeError, ValueError, UnsupportedAlgorithm) as exc:
        raise AttestationError("private_key_invalid") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise AttestationError("private_key_type_invalid")
    return key


def load_attestation_public_key(path: Path) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(_read_key(path))
    except (TypeError, ValueError, UnsupportedAlgorithm) as exc:
        raise AttestationError("public_key_invalid") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise AttestationError("public_key_type_invalid")
    return key


def _stage_bytes(path: Path, data: bytes, *, mode: int) -> Path:
    if mode == 0o600 and getattr(os, "fchmod", None) is None:
        raise AttestationError("secure_permissions_unsupported")
    target = Path(os.path.abspath(path.expanduser()))
    descriptor = -1
    temporary: Path | None = None
    completed = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(temporary_name)
        fchmod = getattr(os, "fchmod", None)
        if fchmod is not None:
            fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        completed = True
        return temporary
    except OSError as exc:
        raise AttestationError("output_unwritable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not completed and temporary is not None and temporary.exists():
            temporary.unlink()


def _backup_target(target: Path) -> Path | None:
    if not target.exists():
        return None
    descriptor = -1
    backup: Path | None = None
    try:
        descriptor, backup_name = tempfile.mkstemp(
            prefix=f".{target.name}.rollback.", dir=target.parent
        )
        os.close(descriptor)
        descriptor = -1
        backup = Path(backup_name)
        shutil.copy2(target, backup)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        if backup is not None:
            backup.unlink(missing_ok=True)
        raise AttestationError("output_unwritable") from exc
    return backup


def _unlink_installed_link(target: Path, staged: Path) -> None:
    try:
        if target.exists() and os.path.samefile(target, staged):
            target.unlink()
    except OSError:
        return


def _install_keypair(
    private_target: Path,
    public_target: Path,
    private_staged: Path,
    public_staged: Path,
    *,
    force: bool,
) -> None:
    private_backup: Path | None = None
    public_backup: Path | None = None
    private_linked = False
    public_linked = False
    try:
        if force:
            private_backup = _backup_target(private_target)
            public_backup = _backup_target(public_target)
            try:
                os.replace(private_staged, private_target)
                os.replace(public_staged, public_target)
            except OSError as exc:
                try:
                    if private_backup is None:
                        private_target.unlink(missing_ok=True)
                    else:
                        os.replace(private_backup, private_target)
                        private_backup = None
                    if public_backup is None:
                        public_target.unlink(missing_ok=True)
                    else:
                        os.replace(public_backup, public_target)
                        public_backup = None
                except OSError as rollback_exc:
                    raise AttestationError("output_rollback_failed") from rollback_exc
                raise AttestationError("output_unwritable") from exc
        else:
            try:
                os.link(private_staged, private_target)
                private_linked = True
                os.link(public_staged, public_target)
                public_linked = True
            except FileExistsError as exc:
                raise AttestationError("output_exists") from exc
            except OSError as exc:
                raise AttestationError("output_unwritable") from exc
    except AttestationError:
        if private_linked:
            _unlink_installed_link(private_target, private_staged)
        if public_linked:
            _unlink_installed_link(public_target, public_staged)
        raise
    finally:
        private_staged.unlink(missing_ok=True)
        public_staged.unlink(missing_ok=True)
        if private_backup is not None:
            private_backup.unlink(missing_ok=True)
        if public_backup is not None:
            public_backup.unlink(missing_ok=True)


def generate_attestation_keypair(
    private_path: Path,
    public_path: Path,
    *,
    force: bool = False,
) -> dict[str, str]:
    private_target = Path(os.path.abspath(private_path.expanduser())).resolve(strict=False)
    public_target = Path(os.path.abspath(public_path.expanduser())).resolve(strict=False)
    if attestation_paths_conflict(private_path, public_path):
        raise AttestationError("key_output_conflict")
    if not force and (private_target.exists() or public_target.exists()):
        raise AttestationError("output_exists")
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_staged = _stage_bytes(private_target, private_bytes, mode=0o600)
    try:
        public_staged = _stage_bytes(public_target, public_bytes, mode=0o644)
    except AttestationError:
        private_staged.unlink(missing_ok=True)
        raise
    _install_keypair(
        private_target,
        public_target,
        private_staged,
        public_staged,
        force=force,
    )
    return {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": _key_id(private_key.public_key()),
        "private_key": str(private_target),
        "public_key": str(public_target),
    }


def atomic_write_attestation(
    path: Path,
    document: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    data = canonical_json_bytes(document) + b"\n"
    if len(data) > MAX_ATTESTATION_BYTES:
        raise AttestationError("attestation_too_large")
    target = Path(os.path.abspath(path.expanduser()))
    staged = _stage_bytes(target, data, mode=0o644)
    try:
        if force:
            os.replace(staged, target)
        else:
            try:
                os.link(staged, target)
            except FileExistsError as exc:
                raise AttestationError("output_exists") from exc
    except AttestationError:
        raise
    except OSError as exc:
        raise AttestationError("output_unwritable") from exc
    finally:
        staged.unlink(missing_ok=True)
