import copy
import json
from pathlib import Path

import jsonschema
import pytest
from proofline.evidence_packages import EvidencePackageError, verify_decision_package

ROOT = Path(__file__).resolve().parents[3]
FORMAT = ROOT / "spec/decision-evidence-package/v1"
VECTORS = FORMAT / "test-vectors"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _replace_pointer(document, pointer: str, value):
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    cursor = document
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    final = parts[-1]
    if isinstance(cursor, list):
        cursor[int(final)] = value
    else:
        cursor[final] = value


def test_dep_v1_schema_accepts_valid_vector_and_reference_verifier_matches_expected():
    schema = _load(FORMAT / "schema.json")
    vector = _load(VECTORS / "valid-minimal.json")
    expected = _load(VECTORS / "expected.json")

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        vector
    )
    assert verify_decision_package(vector) == expected


def test_dep_v1_invalid_mutation_vectors_fail_with_stable_codes():
    original = _load(VECTORS / "valid-minimal.json")

    for mutation in _load(VECTORS / "mutations.json"):
        candidate = copy.deepcopy(original)
        _replace_pointer(candidate, mutation["pointer"], mutation["value"])
        with pytest.raises(EvidencePackageError) as raised:
            verify_decision_package(candidate)
        assert raised.value.code == mutation["expected_error"], mutation["name"]
