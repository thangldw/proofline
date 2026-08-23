import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE_SPEC = importlib.util.spec_from_file_location(
    "check_documentation", ROOT / "scripts/check_documentation.py"
)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(CHECKER)
FORBIDDEN_PATHS = CHECKER.FORBIDDEN_PATHS
REQUIRED_DIAGRAMS = CHECKER.REQUIRED_DIAGRAMS
REQUIRED_TRILINGUAL = CHECKER.REQUIRED_TRILINGUAL
check_documentation = CHECKER.check_documentation


TRILINGUAL = "## English\nEnglish.\n\n## Tiếng Việt\nTiếng Việt.\n\n## 日本語\n日本語。\n"
DIAGRAM = (
    "<!doctype html><html><head><style>svg{display:block}</style></head><body>"
    '<section lang="en"><svg role="img"><title>Title</title>'
    "<desc>Description</desc></svg></section>"
    '<section lang="vi"><svg role="img"><title>Tiêu đề</title><desc>Mô tả</desc></svg></section>'
    '<section lang="ja"><svg role="img"><title>タイトル</title><desc>説明</desc></svg></section>'
    "</body></html>"
)


@pytest.fixture
def documentation_tree(tmp_path: Path) -> Path:
    for relative in REQUIRED_TRILINGUAL:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TRILINGUAL, encoding="utf-8")
    for relative in REQUIRED_DIAGRAMS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DIAGRAM, encoding="utf-8")
    return tmp_path


def test_checker_accepts_minimal_complete_tree(documentation_tree: Path) -> None:
    assert check_documentation(documentation_tree) == []


def test_checker_rejects_missing_required_file(documentation_tree: Path) -> None:
    missing = documentation_tree / REQUIRED_TRILINGUAL[0]
    missing.unlink()

    assert check_documentation(documentation_tree) == [
        f"{REQUIRED_TRILINGUAL[0]}: required file is missing"
    ]


def test_checker_rejects_wrong_language_order(documentation_tree: Path) -> None:
    readme = documentation_tree / "README.md"
    readme.write_text("## Tiếng Việt\nvi\n## English\nen\n## 日本語\nja\n", encoding="utf-8")

    assert "README.md: language sections must be English, Tiếng Việt, 日本語" in (
        check_documentation(documentation_tree)
    )


def test_checker_rejects_mermaid_fence(documentation_tree: Path) -> None:
    readme = documentation_tree / "README.md"
    readme.write_text(f"{TRILINGUAL}\n```mermaid\ngraph LR\n```\n", encoding="utf-8")

    assert "README.md: Mermaid fences are forbidden" in check_documentation(documentation_tree)


def test_checker_rejects_documentation_raster(documentation_tree: Path) -> None:
    raster = documentation_tree / "docs/assets/legacy.png"
    raster.parent.mkdir(parents=True, exist_ok=True)
    raster.write_bytes(b"legacy")

    assert "docs/assets/legacy.png: documentation raster is forbidden" in check_documentation(
        documentation_tree
    )


def test_checker_rejects_broken_relative_link(documentation_tree: Path) -> None:
    readme = documentation_tree / "README.md"
    readme.write_text(f"{TRILINGUAL}\n[missing](docs/missing.md)\n", encoding="utf-8")

    assert "README.md: broken relative link docs/missing.md" in check_documentation(
        documentation_tree
    )


def test_checker_rejects_forbidden_legacy_path(documentation_tree: Path) -> None:
    legacy = documentation_tree / FORBIDDEN_PATHS[0]
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("legacy", encoding="utf-8")

    assert f"{FORBIDDEN_PATHS[0]}: forbidden legacy path exists" in check_documentation(
        documentation_tree
    )


def test_checker_rejects_external_diagram_dependency(documentation_tree: Path) -> None:
    diagram = documentation_tree / REQUIRED_DIAGRAMS[0]
    diagram.write_text(DIAGRAM.replace("</body>", '<img src="https://example.com/x.png"></body>'))

    assert f"{REQUIRED_DIAGRAMS[0]}: external or active content is forbidden" in (
        check_documentation(documentation_tree)
    )
