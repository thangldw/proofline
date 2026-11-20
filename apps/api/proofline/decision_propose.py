from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .decision_undocumented import Candidate

DEFAULT_DIR = ".proofline/proposals"
_SLUG = re.compile(r"[^a-z0-9]+")
_SAFE = re.compile(r"[^A-Za-z0-9._/@+-]")
KINDS = ("dependency", "infrastructure")


class ProposeError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Proposal:
    candidate: Candidate
    output: Path


def _safe(text: str, limit: int = 120) -> str:
    return _SAFE.sub("", text)[:limit]


def _slug(candidate: Candidate) -> str:
    base = _SLUG.sub("-", f"{candidate.kind}-{candidate.name}".casefold()).strip("-")
    return (base or candidate.kind)[:80]


def render_proposal(candidate: Candidate, reason: str | None = None) -> str:
    """A draft decision for a person to review. It is always a candidate, never accepted."""

    name, path = _safe(candidate.name), _safe(candidate.path, 200)
    if candidate.kind == "dependency":
        title = f"Adopt dependency {name}"
        statement = f"Use {name} as a dependency declared in {path}."
        suggestion = f'Enforce: require "{name}" in {path}'
    else:
        title = f"Adopt {name} infrastructure file {path}"
        statement = f"Keep {name} infrastructure defined in {path}."
        suggestion = f"Enforce: require file {path}"
    reason_line = (
        " ".join(reason.split())[:600] if reason else "TODO: why this was chosen over alternatives"
    )
    return (
        f"# Proposed: {title}\n\n"
        "Drafted by `proofline propose` because no approved decision mentions this addition. "
        "Review, edit the reason, then change the status to `accepted`; the status below is "
        "`candidate` on purpose.\n\n"
        f"Decision: {statement}\n"
        f"Rationale: {reason_line}\n"
        "Status: candidate\n\n"
        "Optional rule, to be copied above the Status line once reviewed (it is not active "
        "here):\n\n"
        f"    {suggestion}\n"
    )


def write_proposals(
    candidates: list[Candidate], output_dir: Path, *, reason: str | None = None
) -> list[Proposal]:
    """Write one draft per candidate. Never overwrites and never touches the database."""

    if not candidates:
        return []
    plan = [(c, output_dir / f"{_slug(c)}.md") for c in candidates]
    if any(target.exists() or target.is_symlink() for _, target in plan):
        raise ProposeError("proposal_exists")
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Proposal] = []
    for candidate, target in plan:
        descriptor, temporary = tempfile.mkstemp(dir=output_dir, prefix=".proposal-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(render_proposal(candidate, reason))
            os.link(temporary, target)
        except FileExistsError as exc:
            raise ProposeError("proposal_exists") from exc
        finally:
            Path(temporary).unlink(missing_ok=True)
        written.append(Proposal(candidate, target))
    return written
