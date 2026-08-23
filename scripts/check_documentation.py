#!/usr/bin/env python3
"""Deterministically validate Proofline's documentation contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REQUIRED_TRILINGUAL = (
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "PRIVACY.md",
    "SECURITY.md",
    "SUPPORT.md",
    "TERMS.md",
    "docs/README.md",
    "docs/getting-started.md",
    "docs/architecture.md",
    "docs/decision-lifecycle.md",
    "docs/evidence-packages.md",
    "docs/cli-reference.md",
    "docs/api-reference.md",
    "docs/operations.md",
    "docs/release-process.md",
    "docs/releases/v2.0.0.md",
    "docs/submission/openai-plugin.md",
    "skills/manage-evidence-decisions/SKILL.md",
    "skills/manage-evidence-decisions/references/commands.md",
    "spec/decision-evidence-package/README.md",
    "spec/decision-evidence-package/VERSIONING.md",
    "spec/decision-evidence-package/v1/test-vectors/README.md",
    "spec/decision-review-receipt/README.md",
    "spec/signed-attestation/README.md",
)

REQUIRED_DIAGRAMS = (
    "docs/diagrams/system-architecture.html",
    "docs/diagrams/decision-review-lifecycle.html",
    "docs/diagrams/evidence-verification.html",
)

FORBIDDEN_PATHS = (
    "docs/assets/stale-decision-demo.gif",
    "docs/assets/stale-decision-report.jpg",
    "docs/assets/stale-decision-terminal.png",
    "docs/releases/v1.0.0.md",
    "docs/releases/v1.0.1.md",
    "docs/OPERATIONS.md",
    "docs/submission/DIRECTORY_SUBMISSION.md",
    "docs/superpowers/plans/2026-08-23-proofline-v1-1-decision-health.md",
    "docs/superpowers/plans/2026-08-23-proofline-v1-2-v2-impact-attestations.md",
    "docs/superpowers/specs/2026-08-23-proofline-v1-1-decision-health-design.md",
    "docs/superpowers/specs/2026-08-23-proofline-v1-2-v2-impact-attestations-design.md",
    "scripts/render_readme_demo_gif.py",
)

LANGUAGE_HEADING = re.compile(r"^#{1,6} (English|Tiếng Việt|日本語)\s*$", re.MULTILINE)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
MERMAID_FENCE = re.compile(r"^\s*```mermaid\s*$", re.MULTILINE | re.IGNORECASE)
IGNORED_PARTS = {".git", ".venv", ".worktrees", "node_modules"}
RASTER_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png"}


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _exact_path(root: Path, relative: str) -> Path | None:
    current = root
    for part in Path(relative).parts:
        if not current.is_dir():
            return None
        match = next((child for child in current.iterdir() if child.name == part), None)
        if match is None:
            return None
        current = match
    return current


def check_required_paths(root: Path) -> list[str]:
    errors = [
        f"{relative}: required file is missing"
        for relative in (*REQUIRED_TRILINGUAL, *REQUIRED_DIAGRAMS)
        if (path := _exact_path(root, relative)) is None or not path.is_file()
    ]
    errors.extend(
        f"{relative}: forbidden legacy path exists"
        for relative in FORBIDDEN_PATHS
        if _exact_path(root, relative) is not None
    )
    return errors


def check_language_order(root: Path) -> list[str]:
    errors: list[str] = []
    expected = ["English", "Tiếng Việt", "日本語"]
    for relative in REQUIRED_TRILINGUAL:
        path = _exact_path(root, relative)
        if path is None or not path.is_file():
            continue
        observed = LANGUAGE_HEADING.findall(path.read_text(encoding="utf-8"))
        if observed != expected:
            errors.append(f"{relative}: language sections must be English, Tiếng Việt, 日本語")
    return errors


def _link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split(maxsplit=1)[0]


def check_markdown_links(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_TRILINGUAL:
        path = _exact_path(root, relative)
        if path is None or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = _link_target(match.group(1))
            parsed = urlsplit(raw_target)
            if parsed.scheme or parsed.netloc or raw_target.startswith(("#", "mailto:")):
                continue
            target_path = unquote(parsed.path)
            if not target_path:
                continue
            resolved = (
                (root / target_path.lstrip("/"))
                if target_path.startswith("/")
                else (path.parent / target_path)
            )
            if not resolved.exists():
                errors.append(f"{relative}: broken relative link {raw_target}")
    return errors


def _iter_markdown(root: Path):
    for path in root.rglob("*.md"):
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if relative.parts[:2] == ("docs", "superpowers"):
            continue
        yield path


def check_forbidden_content(root: Path) -> list[str]:
    errors: list[str] = []
    for path in _iter_markdown(root):
        if MERMAID_FENCE.search(path.read_text(encoding="utf-8")):
            errors.append(f"{_relative(path, root)}: Mermaid fences are forbidden")
    docs = root / "docs"
    if docs.is_dir():
        for path in docs.rglob("*"):
            if path.is_file() and path.suffix.lower() in RASTER_SUFFIXES:
                errors.append(f"{_relative(path, root)}: documentation raster is forbidden")
    return errors


def check_diagrams(root: Path) -> list[str]:
    errors: list[str] = []
    forbidden = ("http://", "https://", "<img", "<script", "<animate", "<set", "<link", "@import")
    language_sections = ('<section lang="en"', '<section lang="vi"', '<section lang="ja"')
    for relative in REQUIRED_DIAGRAMS:
        path = _exact_path(root, relative)
        if path is None or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        if any(token in lower for token in forbidden):
            errors.append(f"{relative}: external or active content is forbidden")
        if "<style" not in lower or text.count('<svg role="img"') != 3:
            errors.append(f"{relative}: expected embedded CSS and three accessible SVG figures")
        if text.count("<title>") < 3 or text.count("<desc>") < 3:
            errors.append(f"{relative}: every SVG requires title and description")
        positions = [text.find(section) for section in language_sections]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            errors.append(f"{relative}: figure order must be English, Vietnamese, Japanese")
    return errors


def check_documentation(root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(check_required_paths(root))
    errors.extend(check_language_order(root))
    errors.extend(check_markdown_links(root))
    errors.extend(check_forbidden_content(root))
    errors.extend(check_diagrams(root))
    return sorted(set(errors))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    errors = check_documentation(root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)
    print("documentation contract valid")


if __name__ == "__main__":
    main()
