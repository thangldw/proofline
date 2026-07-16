import hashlib
import json
from pathlib import Path

from proofline.portability import canonical_json_bytes
from proofline.provenance_conformance import (
    CONFORMANCE_SCHEMA,
    run_provenance_conformance,
)


def _assert_valid_content_free_receipt(receipt):
    assert receipt["schema"] == CONFORMANCE_SCHEMA
    assert receipt["checks"]
    assert all(receipt["checks"].values())
    assert receipt["counts"]["source_versions"] == 2
    assert receipt["counts"]["decisions"] == 2
    assert receipt["counts"]["evidence"] == 2
    contract = {
        key: receipt[key]
        for key in ("schema", "package_schema", "checks", "counts", "qualification")
    }
    assert receipt["receipt_sha256"] == hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
    serialized = json.dumps(receipt)
    assert "immutable evidence identities" not in serialized
    assert "derived claims" not in serialized
    assert "proofline-conformance.md" not in serialized
    assert "does not establish authenticity" in receipt["qualification"]


def test_provenance_conformance_exercises_production_round_trips():
    _assert_valid_content_free_receipt(run_provenance_conformance())


def test_tracked_provenance_conformance_receipt_is_current_and_content_free():
    root = Path(__file__).resolve().parents[3]
    receipt = json.loads(
        (root / "evals/provenance/conformance-v1.json").read_text(encoding="utf-8")
    )
    _assert_valid_content_free_receipt(receipt)
