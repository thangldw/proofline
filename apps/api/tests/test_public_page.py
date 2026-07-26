from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_public_docs_are_current_trilingual_and_release_scoped():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs/releases/v1.0.0.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert (
        "Proofline shows which immutable evidence justified an engineering decision"
        in readme
    )
    for language in ("English", "Tiếng Việt", "日本語"):
        assert language in readme
        assert language in release_notes
    assert "```mermaid" in readme
    assert "v1.0.0" in release_notes
    assert "make test" in contributing
