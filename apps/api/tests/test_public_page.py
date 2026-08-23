from pathlib import Path

import yaml

from proofline.decision_policy import load_decision_policy

ROOT = Path(__file__).resolve().parents[3]


def test_public_docs_are_current_trilingual_and_release_scoped():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs/releases/v2.0.1.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    evidence_packages = (ROOT / "docs/evidence-packages.md").read_text(encoding="utf-8")

    assert "binds decisions to immutable source versions and exact citation spans" in readme
    for language in ("English", "Tiếng Việt", "日本語"):
        assert language in readme
        assert language in release_notes
    assert "```mermaid" not in readme
    assert "v2.0.1" in release_notes
    assert "make test" in contributing
    for target in (
        "docs/getting-started.md",
        "docs/architecture.md",
        "docs/evidence-packages.md",
        "docs/submission/openai-plugin.md",
    ):
        assert target in readme
    assert "PyPI distribution is `proofline-evidence`" in readme
    assert "CLI and Python package are `proofline`" in readme
    assert "integrity, not authenticity" in evidence_packages
    assert "proofline-decision-review-receipt-v1" in evidence_packages
    assert "proofline-signed-attestation-v1" in evidence_packages
    assert "trusted public key" in evidence_packages
    assert "transitive impact" in readme.lower()
    assert "single-user" in evidence_packages
    assert "v2.0.1" in readme


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


def test_ci_can_verify_an_explicit_immutable_ref():
    workflow = yaml.load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    source_ref = workflow["on"]["workflow_dispatch"]["inputs"]["source_ref"]
    assert source_ref["required"] == "false"
    assert source_ref["type"] == "string"

    expected_ref = "${{ inputs.source_ref || github.sha }}"
    jobs = workflow["jobs"]
    assert set(jobs) == {
        "python-test-and-quality",
        "web-test-build-egress",
        "package-conformance",
        "release-artifacts",
        "decision-health-sarif",
        "decision-impact-sarif",
    }
    for name, job in jobs.items():
        checkouts = [
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        ]
        assert len(checkouts) == 1, name
        assert checkouts[0]["with"]["ref"] == expected_ref, name
