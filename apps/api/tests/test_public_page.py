import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"


def test_public_docs_include_real_demo_evidence_and_scoped_starter_tasks():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_notes = (DOCS / "releases/v1.1.0.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    description = (
        "Proofline shows what evidence justified an engineering decision and warns you when that "
        "evidence changes."
    )

    assert description in readme
    assert "Why Proofline instead of ADR-only, a wiki, or generic RAG?" in readme

    terminal = DOCS / "assets/stale-decision-terminal.png"
    report = DOCS / "assets/stale-decision-report.jpg"
    assert terminal.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert report.read_bytes().startswith(b"\xff\xd8\xff")
    assert "docs/assets/stale-decision-terminal.png" in readme
    assert "docs/assets/stale-decision-report.jpg" in readme
    release_asset_root = "https://github.com/thangldw/proofline/releases/download/v1.1.0/"
    assert f"{release_asset_root}stale-decision-terminal.png" in release_notes
    assert f"{release_asset_root}stale-decision-report.jpg" in release_notes

    starter_tasks = re.findall(r"^\d+\. \*\*.+?\*\*", contributing, re.MULTILINE)
    assert len(starter_tasks) == 2
