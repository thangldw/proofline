from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .decision_expiry import ExpiryFinding

TIMEOUT_SECONDS = 10
MAX_ITEMS = 50


class NotifyError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class NotifyResult:
    sent: bool
    overdue: int
    due_soon: int
    status: int | None = None


def validate_webhook_url(url: str) -> str:
    """https anywhere; plain http only to a loopback host. No credentials in the URL."""

    parts = urllib.parse.urlsplit(url)
    if parts.username or parts.password or not parts.hostname:
        raise NotifyError("webhook_url_invalid")
    if parts.scheme == "https":
        return url
    if parts.scheme == "http":
        host = parts.hostname
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if loopback:
            return url
    raise NotifyError("webhook_url_insecure")


def build_payload(findings: list[ExpiryFinding], *, as_of: str, style: str) -> dict[str, object]:
    overdue = [item for item in findings if item.state == "overdue"]
    soon = [item for item in findings if item.state == "due_soon"]
    if style == "slack":
        lines = [
            f"Proofline: {len(overdue)} decision review(s) overdue, "
            f"{len(soon)} due soon (as of {as_of})."
        ]
        lines += [
            f"- {item.decision_id[:8]} {item.state} (review by {item.review_by})"
            for item in findings[:MAX_ITEMS]
        ]
        return {"text": "\n".join(lines)}
    return {
        "event": "proofline.expiry",
        "as_of": as_of,
        "overdue": len(overdue),
        "due_soon": len(soon),
        "items": [item.content_free_model_dump() for item in findings[:MAX_ITEMS]],
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def send_expiry_notification(
    url: str,
    findings: list[ExpiryFinding],
    *,
    as_of: str,
    style: str = "generic",
    always: bool = False,
) -> NotifyResult:
    validate_webhook_url(url)
    overdue = sum(1 for item in findings if item.state == "overdue")
    soon = sum(1 for item in findings if item.state == "due_soon")
    if not findings and not always:
        return NotifyResult(False, overdue, soon)
    body = json.dumps(build_payload(findings, as_of=as_of, style=style)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "proofline-notify"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        raise NotifyError(f"webhook_http_{exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise NotifyError("webhook_unreachable") from exc
    return NotifyResult(True, overdue, soon, status)
