from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .decision_health import check_decision_health
from .models import Decision, Source


class DecisionExportError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ExportedAdr:
    decision_id: str
    path: Path


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:60].strip("-")
    return slug or "decision"


def render_adr(decision: Decision, source: Source, health: str) -> str:
    evidence = min(
        (item for item in decision.evidence if item.binding_state == "active"),
        key=lambda item: (item.start_offset, item.id),
    )
    quote = "\n".join(f"> {line}" for line in evidence.quote.splitlines())
    return (
        f"# {decision.title}\n\n"
        f"* Status: {decision.status}\n"
        f"* Decision ID: {decision.id}\n"
        f"* Source: {source.title}:{evidence.start_line}-{evidence.end_line}\n"
        f"* Citation health: {health}\n\n"
        f"## Decision\n\n{decision.statement}\n\n"
        f"## Rationale\n\n{decision.rationale or 'Not recorded.'}\n\n"
        f"## Evidence\n\n{quote}\n"
    )


def export_adrs(session: Session, output_dir: Path, *, force: bool = False) -> list[ExportedAdr]:
    """Write one Markdown ADR per approved decision. Read-only toward the database."""

    decisions = session.scalars(
        select(Decision)
        .options(selectinload(Decision.evidence))
        .where(Decision.status.in_(("active", "accepted")))
        .order_by(Decision.created_at, Decision.id)
    ).all()
    health = {finding.decision_id: finding.reason for finding in check_decision_health(session)}
    sources = {
        item.id: item
        for item in session.scalars(
            select(Source).where(Source.id.in_({d.source_id for d in decisions}))
        ).all()
    }
    plan: list[tuple[Decision, Path]] = []
    for number, decision in enumerate(decisions, start=1):
        if not any(item.binding_state == "active" for item in decision.evidence):
            continue
        plan.append((decision, output_dir / f"{number:04d}-{slugify(decision.title)}.md"))
    output_dir.mkdir(parents=True, exist_ok=True)
    if not force and any(path.exists() for _, path in plan):
        raise DecisionExportError("output_exists")
    exported: list[ExportedAdr] = []
    for decision, path in plan:
        text = render_adr(decision, sources[decision.source_id], health.get(decision.id, "current"))
        descriptor, temporary = tempfile.mkstemp(dir=output_dir, prefix=".adr-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        exported.append(ExportedAdr(decision_id=decision.id, path=path))
    return exported
