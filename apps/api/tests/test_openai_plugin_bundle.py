import copy
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/manage-evidence-decisions/scripts/proofline_package.py"
VECTORS = ROOT / "spec/decision-evidence-package/v1/test-vectors"
REVIEW_VECTORS = ROOT / "spec/decision-review-receipt/v1/test-vectors"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def replace_pointer(document, pointer: str, value) -> None:
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    cursor = document
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    final = parts[-1]
    if isinstance(cursor, list):
        cursor[int(final)] = value
    else:
        cursor[final] = value


def test_bundled_verifier_matches_reference_vector() -> None:
    completed = run("verify", str(VECTORS / "valid-minimal.json"))
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == json.loads((VECTORS / "expected.json").read_text())


def test_bundled_verifier_preserves_mutation_error_codes(tmp_path: Path) -> None:
    original = json.loads((VECTORS / "valid-minimal.json").read_text())
    for mutation in json.loads((VECTORS / "mutations.json").read_text()):
        candidate = copy.deepcopy(original)
        replace_pointer(candidate, mutation["pointer"], mutation["value"])
        path = tmp_path / f"{mutation['name']}.json"
        path.write_text(json.dumps(candidate), encoding="utf-8")
        completed = run("verify", str(path))
        assert completed.returncode == 2
        assert json.loads(completed.stderr)["error"] == mutation["expected_error"]


def test_bundled_verifier_accepts_canonical_zip(tmp_path: Path) -> None:
    package = tmp_path / "evidence.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.write(VECTORS / "valid-minimal.json", "evidence.json")
    completed = run("verify", str(package))
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["valid"] is True


def test_explanation_does_not_return_source_or_quote_content() -> None:
    completed = run("explain", str(VECTORS / "valid-minimal.json"))
    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert "content" not in result["source"]
    assert all("quote" not in citation for citation in result["citations"])


def test_bundled_verifier_checks_review_receipt_vector() -> None:
    completed = run("verify-review", str(REVIEW_VECTORS / "valid-minimal.json"))
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == json.loads(
        (REVIEW_VECTORS / "expected.json").read_text()
    )


def test_bundled_review_verifier_preserves_mutation_codes(tmp_path: Path) -> None:
    original = json.loads((REVIEW_VECTORS / "valid-minimal.json").read_text())
    for mutation in json.loads((REVIEW_VECTORS / "mutations.json").read_text()):
        candidate = copy.deepcopy(original)
        replace_pointer(candidate, mutation["pointer"], mutation["value"])
        path = tmp_path / f"review-{mutation['name']}.json"
        path.write_text(json.dumps(candidate), encoding="utf-8")
        completed = run("verify-review", str(path))
        assert completed.returncode == 2
        assert json.loads(completed.stderr)["error"] == mutation["expected_error"]


def test_plugin_documents_signed_attestation_boundary_without_private_keys() -> None:
    skill = (ROOT / "skills/manage-evidence-decisions/SKILL.md").read_text(encoding="utf-8")
    commands = (ROOT / "skills/manage-evidence-decisions/references/commands.md").read_text(
        encoding="utf-8"
    )
    combined = f"{skill}\n{commands}"

    assert "proofline verify-attestation" in combined
    assert "trusted public key" in combined
    assert "Proofline 2.0.1" in combined
    assert "bundled verifier does not verify Ed25519" in combined
    assert "BEGIN PRIVATE KEY" not in combined


def test_openai_plugin_manifest_has_at_most_three_default_prompts() -> None:
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))

    assert len(manifest["interface"]["defaultPrompt"]) <= 3
