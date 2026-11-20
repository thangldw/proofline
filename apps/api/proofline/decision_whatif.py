from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .decision_code_refs import scan_code_refs
from .decision_enforce import _files, parse_rule, rules_in_quote
from .models import Decision, DecisionRelation

DEPENDENCY_KINDS = frozenset({"based_on", "implements"})
MAX_DEPENDENTS = 500


class WhatIfError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Dependent:
    decision_id: str
    title: str
    status: str
    depth: int
    kinds: list[str]


@dataclass(frozen=True)
class WhatIf:
    decision_id: str
    title: str
    status: str
    dependents: list[Dependent]
    other_relations: list[dict[str, str]]
    code_refs: list[dict[str, object]]
    rules: list[dict[str, object]]
    notes: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, object]:
        return asdict(self)

    def content_free_model_dump(self) -> dict[str, object]:
        document = self.model_dump()
        document.pop("title")
        for item in document["dependents"]:  # type: ignore[attr-defined]
            item.pop("title")
        for item in document["rules"]:  # type: ignore[attr-defined]
            item.pop("rule")
        return document


def _resolve(decisions: list[Decision], reference: str) -> Decision:
    ref = reference.strip().lower()
    if len(ref) < 4:
        raise WhatIfError("decision_reference_invalid")
    matches = [item for item in decisions if item.id.startswith(ref)]
    if not matches:
        raise WhatIfError("decision_not_found")
    if len(matches) > 1:
        raise WhatIfError("decision_reference_ambiguous")
    return matches[0]


def what_if_superseded(session: Session, reference: str, root: Path) -> WhatIf:
    """Blast radius of retiring a decision: dependents, relations, code markers, lost rules."""

    if not root.is_dir():
        raise WhatIfError("root_not_found")
    decisions = list(
        session.scalars(
            select(Decision).options(selectinload(Decision.evidence)).order_by(Decision.id)
        ).all()
    )
    target = _resolve(decisions, reference)
    by_id = {item.id: item for item in decisions}
    now = datetime.now(UTC).replace(tzinfo=None)
    relations = [
        row
        for row in session.scalars(select(DecisionRelation).order_by(DecisionRelation.id))
        if row.valid_to is None or row.valid_to.replace(tzinfo=None) > now
    ]
    dependents_of: dict[str, list[DecisionRelation]] = {}
    for row in relations:
        if row.kind in DEPENDENCY_KINDS:
            dependents_of.setdefault(row.target_decision_id, []).append(row)
    seen = {target.id}
    queue: deque[tuple[str, int, list[str]]] = deque([(target.id, 0, [])])
    dependents: list[Dependent] = []
    while queue and len(dependents) < MAX_DEPENDENTS:
        current, depth, kinds = queue.popleft()
        for row in dependents_of.get(current, []):
            child = by_id.get(row.source_decision_id)
            if child is None or child.id in seen:
                continue
            seen.add(child.id)
            path = [*kinds, row.kind]
            dependents.append(Dependent(child.id, child.title, child.status, depth + 1, path))
            queue.append((child.id, depth + 1, path))
    others = [
        {
            "relation": row.kind,
            "direction": "outgoing" if row.source_decision_id == target.id else "incoming",
            "other_decision_id": (
                row.target_decision_id
                if row.source_decision_id == target.id
                else row.source_decision_id
            ),
        }
        for row in relations
        if row.kind not in DEPENDENCY_KINDS
        and target.id in (row.source_decision_id, row.target_decision_id)
    ]
    refs = [
        {"path": ref.path, "line": ref.line}
        for ref in scan_code_refs([root])
        if target.id.startswith(ref.reference)
    ]
    texts = [
        text
        for evidence in target.evidence
        if evidence.binding_state == "active"
        for text in rules_in_quote(evidence.quote)
    ]
    rules: list[dict[str, object]] = []
    for index, text in enumerate(dict.fromkeys(texts), start=1):
        parsed = parse_rule(text)
        covered = len(_files(root, parsed.glob)) if parsed and parsed.kind != "require_file" else 0
        rules.append({"index": index, "rule": text, "files_covered": covered})
    notes = []
    if target.status not in ("active", "accepted"):
        notes.append("This decision is not currently approved, so retiring it changes little.")
    if dependents:
        notes.append("Dependents were based on this decision and should be reviewed.")
    if rules:
        notes.append("These Enforce rules stop being checked once the decision is retired.")
    return WhatIf(target.id, target.title, target.status, dependents, others, refs, rules, notes)


def render_text(result: WhatIf, *, include_titles: bool = True) -> str:
    def label(decision_id: str, title: str) -> str:
        return f"{title} ({decision_id[:8]})" if include_titles else decision_id[:8]

    lines = [f"If {label(result.decision_id, result.title)} [{result.status}] were superseded:"]
    lines.append(f"- {len(result.dependents)} dependent decision(s)")
    lines += [
        f"    depth {d.depth}: {label(d.decision_id, d.title)} [{d.status}] via {'>'.join(d.kinds)}"
        for d in result.dependents
    ]
    lines.append(f"- {len(result.code_refs)} code reference(s)")
    lines += [f"    {ref['path']}:{ref['line']}" for ref in result.code_refs]
    lines.append(f"- {len(result.rules)} Enforce rule(s) would stop being checked")
    lines += [
        f"    rule {r['index']}: "
        + (f"{r['rule']} " if include_titles else "")
        + f"({r['files_covered']} file(s) covered)"
        for r in result.rules
    ]
    lines.append(f"- {len(result.other_relations)} other relation(s)")
    lines += [
        f"    {r['relation']} ({r['direction']}) {r['other_decision_id'][:8]}"
        for r in result.other_relations
    ]
    lines += [f"Note: {note}" for note in result.notes]
    return "\n".join(lines) + "\n"
