from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .decision_conflicts import find_conflict_candidates
from .decision_health import check_decision_health
from .models import Decision, DecisionRelation

MAX_NODES = 500


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    stale: bool


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str


@dataclass(frozen=True)
class DecisionGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def build_graph(
    session: Session,
    *,
    include_titles: bool = True,
    include_conflicts: bool = True,
    include_isolated: bool = False,
) -> DecisionGraph:
    decisions = {
        item.id: item
        for item in session.scalars(
            select(Decision)
            .where(Decision.status.in_(("active", "accepted")), Decision.kind == "decision")
            .order_by(Decision.id)
            .limit(MAX_NODES)
        ).all()
    }
    edges = [
        GraphEdge(row.source_decision_id, row.target_decision_id, row.kind)
        for row in session.scalars(select(DecisionRelation).order_by(DecisionRelation.id)).all()
        if row.source_decision_id in decisions and row.target_decision_id in decisions
    ]
    if include_conflicts:
        edges += [
            GraphEdge(item.first_id, item.second_id, "possible_conflict")
            for item in find_conflict_candidates(session, min_similarity=0.5)
            if item.first_id in decisions and item.second_id in decisions
        ]
    stale = {finding.decision_id for finding in check_decision_health(session)}
    linked = {edge.source for edge in edges} | {edge.target for edge in edges}
    nodes = [
        GraphNode(
            item.id,
            item.title if include_titles else item.id[:8],
            item.id in stale,
        )
        for item in decisions.values()
        if include_isolated or item.id in linked
    ]
    return DecisionGraph(nodes, edges)


def _alias(node_id: str) -> str:
    return "n" + re.sub(r"[^A-Za-z0-9]", "", node_id)[:12]


def _mermaid_label(text: str) -> str:
    cleaned = re.sub(r"[\r\n]+", " ", text)[:80]
    return (
        cleaned.replace("&", "#amp;")
        .replace('"', "#quot;")
        .replace("<", "#lt;")
        .replace(">", "#gt;")
    )


def render_mermaid(graph: DecisionGraph) -> str:
    lines = ["graph LR"]
    for node in graph.nodes:
        lines.append(f'  {_alias(node.id)}["{_mermaid_label(node.label)}"]')
    for edge in graph.edges:
        arrow = "-.->" if edge.kind == "possible_conflict" else "-->"
        lines.append(f"  {_alias(edge.source)} {arrow}|{edge.kind}| {_alias(edge.target)}")
    stale = [_alias(node.id) for node in graph.nodes if node.stale]
    if stale:
        lines.append("  classDef stale fill:#fdd,stroke:#c00;")
        lines.append(f"  class {','.join(stale)} stale;")
    return "\n".join(lines) + "\n"


def _dot_label(text: str) -> str:
    cleaned = re.sub(r"[\r\n]+", " ", text)[:80]
    return cleaned.replace("\\", "\\\\").replace('"', '\\"')


def render_dot(graph: DecisionGraph) -> str:
    lines = ["digraph decisions {", "  rankdir=LR;", "  node [shape=box];"]
    for node in graph.nodes:
        extra = ' style=filled fillcolor="#ffdddd" color="#cc0000"' if node.stale else ""
        lines.append(f'  {_alias(node.id)} [label="{_dot_label(node.label)}"{extra}];')
    for edge in graph.edges:
        style = ' style=dashed color="#cc0000"' if edge.kind == "possible_conflict" else ""
        lines.append(
            f'  {_alias(edge.source)} -> {_alias(edge.target)} [label="{edge.kind}"{style}];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"
