from pathlib import Path

from proofline.decision_policy import load_decision_policy

ROOT = Path(__file__).resolve().parents[3]


def test_public_docs_are_current_trilingual_and_release_scoped():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs/releases/v2.0.0.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    evidence_packages = (ROOT / "docs/evidence-packages.md").read_text(encoding="utf-8")

    assert "Proofline shows which immutable evidence justified an engineering decision" in readme
    for language in ("English", "Tiếng Việt", "日本語"):
        assert language in readme
        assert language in release_notes
    assert "```mermaid" in readme
    assert "v2.0.0" in release_notes
    assert "make test" in contributing
    assert "[evidence package formats](docs/evidence-packages.md)" in readme
    assert "Accepted · review required" in readme
    assert "integrity, not authenticity" in evidence_packages
    assert "proofline-decision-review-receipt-v1" in evidence_packages
    assert "proofline-signed-attestation-v1" in evidence_packages
    assert "trusted public key" in evidence_packages
    assert "transitive impact" in readme.lower()
    assert "single-user" in evidence_packages


def test_default_decision_policy_and_ci_contract_are_committed():
    policy = load_decision_policy(ROOT / "proofline.toml")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert policy.fail_on == {"moved", "ambiguous", "changed", "deleted"}
    for required in (
        "python-test-and-quality",
        "web-test-build-egress",
        "package-conformance",
        "decision-health-sarif",
        "artifacts/decision-health.sarif",
        "decision-impact-sarif",
        "artifacts/decision-impact.sarif",
        "verify-attestation",
    ):
        assert required in workflow
    assert workflow.count("python -m venv .venv") == 5
    assert workflow.count(".venv/bin/proofline") == 10
    assert ".venv/bin/python -m build --outdir dist" in workflow
    assert ".venv/bin/python scripts/verify_release_artifacts.py" in workflow
    assert "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
