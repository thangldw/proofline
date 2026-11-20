from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Decision

APPROVED = ("active", "accepted")
_DEP_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_REQUIREMENT = re.compile(rf"^\s*({_DEP_NAME})\s*(?:\[[^\]]*\])?\s*(?:[=<>!~;@]|$)")
_PYPROJECT = re.compile(rf'^\s*"({_DEP_NAME})\s*(?:\[[^\]]*\])?\s*(?:[=<>!~;,"@])')
_PACKAGE_JSON = re.compile(r'^\s*"(@?[a-z0-9][a-z0-9._/-]*)"\s*:\s*"[\^~<>=*\dv][^"]*"\s*,?\s*$')
_CARGO = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*=\s*(?:"[^"]+"|\{)')
_GO_MOD = re.compile(r"^\s*(?:require\s+)?([a-z0-9][a-z0-9.\-]*\.[a-z]+/[A-Za-z0-9._/\-]+)\s+v\d")
_NOT_DEPENDENCIES = frozenset(
    {
        "version",
        "name",
        "edition",
        "authors",
        "description",
        "license",
        "repository",
        "homepage",
        "rust-version",
        "readme",
        "publish",
        "resolver",
        "path",
        "default",
        "features",
        "documentation",
        "keywords",
        "categories",
        "include",
        "exclude",
        "node",
        "npm",
        "main",
        "module",
        "types",
        "type",
        "private",
        "files",
        "bin",
    }
)
_INFRA = (
    (re.compile(r"(^|/)Dockerfile(\.[\w.-]+)?$"), "docker"),
    (re.compile(r"(^|/)docker-compose[\w.-]*\.ya?ml$"), "docker"),
    (re.compile(r"\.tf$"), "terraform"),
    (re.compile(r"(^|/)Chart\.yaml$"), "helm"),
    (re.compile(r"(^|/)serverless\.ya?ml$"), "serverless"),
)


@dataclass(frozen=True)
class Candidate:
    path: str
    kind: str  # dependency | infrastructure
    name: str

    def model_dump(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class Undocumented(Candidate):
    pass


def _normalise(text: str) -> str:
    return text.casefold().replace("_", "-")


def _manifest_names(path: str, added: list[str]) -> list[str]:
    base = PurePosixPath(path).name
    if base.startswith("requirements") and base.endswith(".txt"):
        names = []
        for line in added:
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", "-")):
                match = _REQUIREMENT.match(stripped)
                if match:
                    names.append(match.group(1))
        return names
    if base == "pyproject.toml":
        return [m.group(1) for line in added if (m := _PYPROJECT.match(line))]
    if base == "package.json":
        return [
            m.group(1)
            for line in added
            if (m := _PACKAGE_JSON.match(line)) and m.group(1) not in _NOT_DEPENDENCIES
        ]
    if base == "Cargo.toml":
        return [
            m.group(1)
            for line in added
            if (m := _CARGO.match(line)) and m.group(1) not in _NOT_DEPENDENCIES
        ]
    if base == "go.mod":
        return [m.group(1) for line in added if (m := _GO_MOD.match(line))]
    return []


def candidates_from_diff(diff: str) -> list[Candidate]:
    """Dependencies and infrastructure files that a unified diff adds."""

    found: dict[tuple[str, str, str], Candidate] = {}
    path: str | None = None
    is_new = False
    added: dict[str, list[str]] = {}
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path, is_new = None, False
        elif line.startswith("new file mode"):
            is_new = True
        elif line.startswith("+++ "):
            name = line[4:].strip()
            path = None if name == "/dev/null" else name.removeprefix("b/")
            if path is not None:
                added.setdefault(path, [])
                if is_new:
                    for pattern, label in _INFRA:
                        if pattern.search(path):
                            found[(path, "infrastructure", label)] = Candidate(
                                path, "infrastructure", label
                            )
        elif line.startswith("+") and not line.startswith("+++") and path is not None:
            added[path].append(line[1:])
    for file_path, lines in added.items():
        for name in _manifest_names(file_path, lines):
            found[(file_path, "dependency", name)] = Candidate(file_path, "dependency", name)
    return sorted(found.values(), key=lambda c: (c.path, c.kind, c.name))


def _aliases(candidate: Candidate) -> list[str]:
    name = _normalise(candidate.name)
    aliases = [name]
    if "/" in name:
        aliases.append(name.rsplit("/", 1)[-1])
    return aliases


def find_undocumented(
    session: Session, candidates: list[Candidate], *, ignore: frozenset[str] = frozenset()
) -> list[Undocumented]:
    """Candidates that no approved decision mentions, by whole-word match on its text."""

    corpus = _normalise(
        "\n".join(
            f"{row.title}\n{row.statement}\n{row.rationale or ''}"
            for row in session.scalars(select(Decision).where(Decision.status.in_(APPROVED)))
        )
    )
    skipped = {_normalise(item) for item in ignore}
    missing: list[Undocumented] = []
    for candidate in candidates:
        aliases = _aliases(candidate)
        if any(alias in skipped for alias in aliases):
            continue
        if any(re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", corpus) for alias in aliases):
            continue
        missing.append(Undocumented(candidate.path, candidate.kind, candidate.name))
    return missing


def candidates_from_lines(path: str, added: list[str], *, whole_file: bool) -> list[Candidate]:
    """Candidates in text an agent just wrote (infrastructure only for whole-file writes)."""

    found: list[Candidate] = []
    if whole_file:
        for pattern, label in _INFRA:
            if pattern.search(path):
                found.append(Candidate(path, "infrastructure", label))
    else:
        found.extend(Candidate(path, "dependency", name) for name in _manifest_names(path, added))
    return sorted(set(found), key=lambda c: (c.path, c.kind, c.name))
