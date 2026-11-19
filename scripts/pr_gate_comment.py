#!/usr/bin/env python3
"""Create or update the single Proofline decision-gate comment on a pull request.

Reads the content-free JSON reports written by ``proofline check-decisions --format json`` and
``proofline check-impacts --format json`` and posts only counts, reasons, line ranges and ids.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

MARKER = "<!-- proofline-decision-gate -->"
MAX_ROWS = 20
Request = Callable[[str, str, dict[str, Any] | None], Any]


def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else None


def build_comment(decisions: dict[str, Any] | None, impacts: dict[str, Any] | None) -> str:
    lines = [MARKER, "## Proofline decision check", ""]
    if decisions is None:
        lines.append("No decision report was produced.")
        return "\n".join(lines) + "\n"
    findings = decisions.get("findings") or []
    blocking = decisions.get("blocking_count", 0)
    if decisions.get("valid") and not findings:
        lines.append("All approved decisions still cite unchanged evidence.")
    else:
        lines.append(
            f"**{len(findings)}** decision(s) cite evidence that changed; "
            f"**{blocking}** blocking under the repository policy."
        )
        lines += ["", "| Decision | Lines | State |", "| --- | --- | --- |"]
        for finding in findings[:MAX_ROWS]:
            lines.append(
                f"| `{str(finding.get('decision_id', ''))[:12]}` "
                f"| {finding.get('start_line')}-{finding.get('end_line')} "
                f"| {finding.get('reason')} |"
            )
        if len(findings) > MAX_ROWS:
            lines.append(f"| … | … | {len(findings) - MAX_ROWS} more in the SARIF report |")
    if impacts is not None and impacts.get("findings"):
        lines += [
            "",
            f"Downstream impact: **{impacts.get('impacted_decision_count', 0)}** decision(s) "
            f"depend on **{impacts.get('root_review_count', 0)}** reviewed root(s).",
        ]
    lines += [
        "",
        "_Content-free summary: titles and quotes stay in the SARIF report. "
        "The check shows that cited evidence changed, not whether the change is acceptable._",
    ]
    return "\n".join(lines) + "\n"


def upsert_comment(request: Request, repo: str, pull_number: int, body: str) -> str:
    base = f"/repos/{repo}/issues"
    comments = request("GET", f"{base}/{pull_number}/comments?per_page=100", None)
    for comment in comments:
        if MARKER in (comment.get("body") or ""):
            request("PATCH", f"{base}/comments/{comment['id']}", {"body": body})
            return "updated"
    request("POST", f"{base}/{pull_number}/comments", {"body": body})
    return "created"


def github_request(api_url: str, token: str) -> Request:
    parsed = urllib.parse.urlparse(api_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("github_api_url_must_be_https")

    def call(method: str, path: str, payload: dict[str, Any] | None) -> Any:
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(
            api_url.rstrip("/") + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:  # noqa: S310 - https only
            return json.load(response)

    return call


def pull_number_from_event(path: Path) -> int | None:
    event = json.loads(path.read_text(encoding="utf-8"))
    number = (event.get("pull_request") or {}).get("number")
    return number if isinstance(number, int) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--impacts", type=Path)
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not (token and repo and event_path):
        print("pr comment skipped: missing token, repository or event", file=sys.stderr)
        return 0
    number = pull_number_from_event(Path(event_path))
    if number is None:
        print("pr comment skipped: not a pull_request event", file=sys.stderr)
        return 0
    body = build_comment(_load(args.decisions), _load(args.impacts))
    request = github_request(os.environ.get("GITHUB_API_URL", "https://api.github.com"), token)
    print(f"pr comment {upsert_comment(request, repo, number, body)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
