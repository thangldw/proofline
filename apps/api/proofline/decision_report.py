from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from .decision_conflicts import ConflictCandidate, find_conflict_candidates
from .decision_expiry import ExpiryFinding, check_expiry
from .decision_health import DecisionHealthFinding, check_decision_health
from .decision_trend import TrendPoint, render_markdown, trend
from .models import Decision

REDACTED = "(title withheld)"


@dataclass(frozen=True)
class HealthReport:
    as_of: str
    include_titles: bool
    stale: list[DecisionHealthFinding]
    expiring: list[ExpiryFinding]
    conflicts: list[ConflictCandidate]
    points: list[TrendPoint]
    titles: dict[str, str]


def build_report(
    session: Session,
    *,
    as_of: date,
    include_titles: bool = True,
    warn_within_days: int = 30,
    trend_limit: int = 30,
    min_similarity: float = 0.5,
) -> HealthReport:
    conflicts = find_conflict_candidates(session, min_similarity=min_similarity)
    ids = {item for c in conflicts for item in (c.first_id, c.second_id)}
    titles = (
        {row.id: row.title for row in session.scalars(select(Decision).where(Decision.id.in_(ids)))}
        if ids and include_titles
        else {}
    )
    return HealthReport(
        as_of=as_of.isoformat(),
        include_titles=include_titles,
        stale=check_decision_health(session),
        expiring=check_expiry(session, as_of=as_of, warn_within_days=warn_within_days),
        conflicts=conflicts,
        points=trend(session, limit=trend_limit),
        titles=titles,
    )


def _title(report: HealthReport, value: str) -> str:
    return value if report.include_titles else REDACTED


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _shared(report: HealthReport, candidate: ConflictCandidate) -> str:
    if report.include_titles:
        return ", ".join(candidate.shared_terms)
    return str(len(candidate.shared_terms))


def render_report_markdown(report: HealthReport) -> str:
    out = [f"# Decision health report ({report.as_of})", ""]
    out += [
        "## Trend",
        "",
        render_markdown(report.points) if report.points else "No snapshots yet.\n",
    ]
    out += ["## Stale citations", ""]
    if report.stale:
        out += ["| Decision | Reason | Where |", "| --- | --- | --- |"]
        out += [
            f"| {_cell(_title(report, f.decision_title))} (`{f.decision_id[:8]}`) | {f.reason} "
            f"| {_cell(f.source_title if report.include_titles else f.source_id[:8])}"
            f":{f.start_line}-{f.end_line} |"
            for f in report.stale
        ]
    else:
        out.append("None.")
    out += ["", "## Reviews due", ""]
    if report.expiring:
        out += ["| Decision | State | Review by | Days overdue |", "| --- | --- | --- | ---: |"]
        out += [
            f"| {_cell(_title(report, e.decision_title))} (`{e.decision_id[:8]}`) | {e.state} "
            f"| {e.review_by} | {max(e.days_overdue, 0)} |"
            for e in report.expiring
        ]
    else:
        out.append("None.")
    out += ["", "## Possible conflicts (for a person to judge)", ""]
    if report.conflicts:
        out += ["| First | Second | Shared words |", "| --- | --- | --- |"]
        out += [
            f"| {_cell(_title(report, report.titles.get(c.first_id, '')))} (`{c.first_id[:8]}`) "
            f"| {_cell(_title(report, report.titles.get(c.second_id, '')))} (`{c.second_id[:8]}`) "
            f"| {_cell(_shared(report, c))} |"
            for c in report.conflicts
        ]
    else:
        out.append("None.")
    return "\n".join(out) + "\n"


def _sparkline(points: list[TrendPoint]) -> str:
    if len(points) < 2:
        return ""
    width, height = 320, 60
    step = width / (len(points) - 1)
    top = max(point.stale_percent for point in points) or 1.0
    coords = " ".join(
        f"{index * step:.1f},{height - 4 - (point.stale_percent / top) * (height - 8):.1f}"
        for index, point in enumerate(points)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Stale percent over time">'
        f'<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="{coords}"/></svg>'
    )


def _table(headers: list[str], rows: list[list[str]], empty: str) -> str:
    if not rows:
        return f"<p>{escape(empty)}</p>"
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


_STYLE = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd;--accent:#0b6bcb}
@media (prefers-color-scheme:dark){
:root{--bg:#161616;--fg:#eee;--muted:#aaa;--line:#333;--accent:#6cb0ff}}
body{background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif;margin:0 auto;
max-width:960px;padding:24px 16px}
h1{font-size:1.5rem}h2{font-size:1.15rem;margin-top:2rem}
table{border-collapse:collapse;width:100%;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left}
.meta{color:var(--muted)}svg{width:100%;max-width:320px;height:auto}
"""


def render_report_html(report: HealthReport) -> str:
    summary = (
        f"{len(report.stale)} stale, {len(report.expiring)} reviews due, "
        f"{len(report.conflicts)} possible conflicts"
    )
    trend_rows = [
        [p.taken_at[:10], str(p.approved), str(p.findings), f"{p.stale_percent}%"]
        for p in report.points
    ]
    stale_rows = [
        [
            _title(report, f.decision_title),
            f.decision_id[:8],
            f.reason,
            f"{f.source_title if report.include_titles else f.source_id[:8]}"
            f":{f.start_line}-{f.end_line}",
        ]
        for f in report.stale
    ]
    expiry_rows = [
        [
            _title(report, e.decision_title),
            e.decision_id[:8],
            e.state,
            e.review_by,
            str(max(e.days_overdue, 0)),
        ]
        for e in report.expiring
    ]
    conflict_rows = [
        [
            _title(report, report.titles.get(c.first_id, "")),
            c.first_id[:8],
            _title(report, report.titles.get(c.second_id, "")),
            c.second_id[:8],
            _shared(report, c),
        ]
        for c in report.conflicts
    ]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Decision health report</title><style>{_STYLE}</style></head><body>"
        f'<h1>Decision health report</h1><p class="meta">As of {escape(report.as_of)}. '
        f"{escape(summary)}.</p>"
        f"<h2>Trend</h2>{_sparkline(report.points)}"
        + _table(["Date", "Approved", "Stale", "Stale %"], trend_rows, "No snapshots yet.")
        + "<h2>Stale citations</h2>"
        + _table(["Decision", "ID", "Reason", "Where"], stale_rows, "None.")
        + "<h2>Reviews due</h2>"
        + _table(["Decision", "ID", "State", "Review by", "Days overdue"], expiry_rows, "None.")
        + "<h2>Possible conflicts (for a person to judge)</h2>"
        + _table(["First", "ID", "Second", "ID", "Shared words"], conflict_rows, "None.")
        + "</body></html>\n"
    )
