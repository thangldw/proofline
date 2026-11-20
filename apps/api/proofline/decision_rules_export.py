from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .decision_enforce import parse_rule, rules_in_quote
from .models import Decision

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ALNUM = re.compile(r"[A-Za-z0-9_]")


class RulesExportError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ExportedRule:
    decision_id: str
    rule_index: int
    text: str
    glob: str


@dataclass(frozen=True)
class SkippedRule:
    decision_id: str
    rule_index: int
    reason: str  # not_expressible | rule_invalid


def pcre_literal(text: str) -> str:
    """Escape every ASCII non-word character so the text can only match itself."""

    out: list[str] = []
    for char in text:
        if ord(char) > 126 or _ALNUM.match(char):
            out.append(char)
        elif char == " ":
            out.append(r"\x20")
        else:
            out.append(f"\\x{ord(char):02x}")
    return "".join(out)


def collect_rules(session: Session) -> tuple[list[ExportedRule], list[SkippedRule]]:
    decisions = session.scalars(
        select(Decision)
        .options(selectinload(Decision.evidence))
        .where(Decision.status.in_(("active", "accepted")))
        .order_by(Decision.id)
    ).all()
    exported: list[ExportedRule] = []
    skipped: list[SkippedRule] = []
    for decision in decisions:
        texts: list[str] = []
        for evidence in decision.evidence:
            if evidence.binding_state == "active":
                texts.extend(rules_in_quote(evidence.quote))
        for index, raw in enumerate(dict.fromkeys(texts), start=1):
            rule = parse_rule(raw)
            if rule is None:
                skipped.append(SkippedRule(decision.id, index, "rule_invalid"))
            elif rule.kind == "forbid":
                exported.append(ExportedRule(decision.id, index, rule.pattern, rule.glob))
            else:
                skipped.append(SkippedRule(decision.id, index, "not_expressible"))
    return exported, skipped


def render_semgrep(rules: list[ExportedRule]) -> str:
    """Semgrep rules (JSON is valid YAML, so every string is safely quoted)."""

    if not rules:
        raise RulesExportError("no_exportable_rules")
    lines = ["rules:"]
    for rule in rules:
        short = rule.decision_id[:8]
        lines += [
            f"  - id: {json.dumps(f'proofline-{short}-{rule.rule_index}')}",
            "    languages: [generic]",
            "    severity: ERROR",
            "    message: "
            + json.dumps(
                f"Forbidden by Proofline decision {short} (rule {rule.rule_index}). "
                f"Run proofline why {short} for the reason."
            ),
            f"    pattern-regex: {json.dumps(pcre_literal(_CONTROL.sub(' ', rule.text)))}",
            "    paths:",
            f"      include: [{json.dumps(rule.glob)}]",
            "    metadata:",
            f"      proofline_decision: {json.dumps(rule.decision_id)}",
        ]
    return "\n".join(lines) + "\n"
