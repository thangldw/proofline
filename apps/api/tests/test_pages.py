from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from proofline import __version__


class PageInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.references: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        for attribute in ("href", "src"):
            if values.get(attribute):
                self.references.append(values[attribute])


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_public_product_page_has_resolvable_local_assets_and_fragments() -> None:
    docs = repository_root() / "docs"
    page = docs / "index.html"
    content = page.read_text(encoding="utf-8")
    inventory = PageInventory()
    inventory.feed(content)

    assert f"v{__version__}" in content
    assert "experimental pre-alpha" in content.lower()
    assert "not a signed" not in content.lower()  # boundary uses affirmative factual wording
    assert "signed native installers" in content
    assert "exact source lines" in content

    for reference in inventory.references:
        if reference.startswith("#"):
            assert reference[1:] in inventory.ids
            continue
        parsed = urlparse(reference)
        if parsed.scheme or reference.startswith("//"):
            continue
        target = docs / parsed.path
        assert target.exists(), reference


def test_pages_source_disables_jekyll_processing() -> None:
    assert (repository_root() / "docs" / ".nojekyll").is_file()
