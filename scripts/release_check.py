#!/usr/bin/env python3
"""Validate that a Proofline Git tag matches every published version surface."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path

TAG_PATTERN = re.compile(
    r"^v(?P<base>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<phase>alpha|beta|rc)\.(?P<number>[1-9]\d*))?$"
)


def python_version_for(tag: str) -> str:
    match = TAG_PATTERN.fullmatch(tag)
    if not match:
        raise ValueError("tag must match vMAJOR.MINOR.PATCH[-alpha|beta|rc.N]")
    base = f"{match['base']}.{match['minor']}.{match['patch']}"
    phase = match["phase"]
    if phase is None:
        return base
    marker = {"alpha": "a", "beta": "b", "rc": "rc"}[phase]
    return f"{base}{marker}{match['number']}"


def package_version_for(tag: str) -> str:
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError("tag must match vMAJOR.MINOR.PATCH[-alpha|beta|rc.N]")
    return tag.removeprefix("v")


def read_dunder_version(path: Path) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise ValueError(f"{path} does not define a literal __version__")


def validate_release(repository: Path, tag: str) -> list[str]:
    try:
        expected_python = python_version_for(tag)
        expected_package = package_version_for(tag)
    except ValueError as exc:
        return [str(exc)]

    errors: list[str] = []
    project = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))
    web = json.loads((repository / "apps/web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((repository / "package-lock.json").read_text(encoding="utf-8"))
    runtime_version = read_dunder_version(repository / "apps/api/proofline/__init__.py")

    observed = {
        "pyproject.toml": project["project"]["version"],
        "proofline.__version__": runtime_version,
        "apps/web/package.json": web["version"],
        "package-lock.json workspace": lock["packages"]["apps/web"]["version"],
    }
    for surface, value in observed.items():
        expected = (
            expected_python
            if surface in {"pyproject.toml", "proofline.__version__"}
            else expected_package
        )
        if value != expected:
            errors.append(f"{surface} is {value!r}; expected {expected!r} for {tag}")

    changelog = (repository / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = rf"^## \[{re.escape(expected_package)}\] - \d{{4}}-\d{{2}}-\d{{2}}$"
    if not re.search(heading, changelog, re.MULTILINE):
        errors.append(f"CHANGELOG.md has no dated [{expected_package}] release heading")

    notes = repository / "docs/releases" / f"{tag}.md"
    if not notes.is_file():
        errors.append(f"release notes are missing: {notes.relative_to(repository)}")
    return errors


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[1]
    errors = validate_release(repository, args.tag)
    if errors:
        for error in errors:
            print(f"release check failed: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"tag": args.tag, "status": "ready"}, sort_keys=True))


if __name__ == "__main__":
    main()
