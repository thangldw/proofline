from pathlib import Path

from proofline.decision_policy import load_decision_policy

ROOT = Path(__file__).resolve().parents[3]


def test_public_docs_are_current_trilingual_and_release_scoped():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs/releases/v1.0.1.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    evidence_packages = (ROOT / "docs/evidence-packages.md").read_text(encoding="utf-8")

    assert "Proofline shows which immutable evidence justified an engineering decision" in readme
    for language in ("English", "Tiếng Việt", "日本語"):
        assert language in readme
        assert language in release_notes
    assert "```mermaid" in readme
    assert "v1.0.1" in release_notes
    assert "make test" in contributing
    assert "[evidence package formats](docs/evidence-packages.md)" in readme
    assert "Accepted · review required" in readme
    assert "integrity, not authenticity" in evidence_packages
    assert "proofline-decision-review-receipt-v1" in evidence_packages
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
    ):
        assert required in workflow
