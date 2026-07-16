import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"


class PageAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.references: list[tuple[str, str, str]] = []
        self.external_targets: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if attributes.get("id"):
            self.ids.append(attributes["id"])
        for key in ("href", "src"):
            if attributes.get(key):
                self.references.append((tag, key, attributes[key]))
        if attributes.get("target") == "_blank":
            self.external_targets.append(attributes)


def test_public_page_tells_the_stale_decision_story_without_remote_assets():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    css = (DOCS / "proofline-page.css").read_text(encoding="utf-8")
    script = (DOCS / "proofline-page.js").read_text(encoding="utf-8")

    assert "Know what justified a decision" in html
    assert "Decision requires review" in html
    assert "requirement.md:42-48 changed after this decision was approved." in html
    assert "proofline demo stale-decision" in html
    assert "SQLite mode=ro" in html
    assert "Merkle DAG" not in html
    assert "proofline demo stale-decision" in script
    assert "@import" not in css
    assert "url(http" not in css


def test_public_page_local_references_resolve_and_external_tabs_are_safe():
    audit = PageAudit()
    audit.feed((DOCS / "index.html").read_text(encoding="utf-8"))

    assert len(audit.ids) == len(set(audit.ids))
    missing: list[str] = []
    for _tag, _key, reference in audit.references:
        parsed = urlparse(reference)
        if parsed.scheme or reference.startswith(("#", "mailto:")):
            continue
        if not (DOCS / parsed.path).exists():
            missing.append(reference)
    assert missing == []
    assert audit.external_targets
    assert all(
        {"noopener", "noreferrer"}.issubset(target.get("rel", "").split())
        for target in audit.external_targets
    )


def test_public_page_benchmark_values_match_committed_receipt():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    receipt = json.loads(
        (ROOT / "evals/benchmarks/decision-evidence-package-v1.json").read_text(encoding="utf-8")
    )

    assert f"{receipt['ingest_latency_ms']:.2f}" in html
    assert f"{receipt['package_build_latency_ms']:.2f}" in html
    assert f"{receipt['verify_latency_ms_median']:.2f}" in html
    assert f"{receipt['package_zip_bytes']:,}" in html
