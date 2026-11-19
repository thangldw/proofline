import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.decision_expiry import ExpiryFinding
from proofline.decision_notify import (
    NotifyError,
    build_payload,
    send_expiry_notification,
    validate_webhook_url,
)
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

FINDINGS = [
    ExpiryFinding("a" * 36, "Secret title", "2020-01-01", 5, "overdue"),
    ExpiryFinding("b" * 36, "Other secret", "2026-01-05", -2, "due_soon"),
]


class _Server:
    def __init__(self, status=200):
        outer = self
        outer.requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                outer.requests.append(json.loads(self.rfile.read(length)))
                self.send_response(outer.status)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.status = status
        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/hook"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    instance = _Server()
    yield instance
    instance.close()


def test_url_policy_allows_https_and_loopback_http_only():
    assert validate_webhook_url("https://hooks.example.com/x")
    assert validate_webhook_url("http://127.0.0.1:9/x") and validate_webhook_url(
        "http://localhost/x"
    )
    for bad in ("http://example.com/x", "ftp://x/y", "https://u:p@example.com/x", "nonsense"):
        with pytest.raises(NotifyError):
            validate_webhook_url(bad)


def test_payload_is_content_free_in_both_styles():
    generic = build_payload(FINDINGS, as_of="2026-01-01", style="generic")
    assert generic["overdue"] == 1 and generic["due_soon"] == 1
    assert "secret" not in json.dumps(generic).lower()
    slack = build_payload(FINDINGS, as_of="2026-01-01", style="slack")
    assert "secret" not in json.dumps(slack).lower() and "aaaaaaaa overdue" in slack["text"]


def test_sends_once_and_skips_when_nothing_is_due(server):
    result = send_expiry_notification(server.url, FINDINGS, as_of="2026-01-01")
    assert (
        result.sent and result.status == 200 and server.requests[0]["event"] == "proofline.expiry"
    )
    quiet = send_expiry_notification(server.url, [], as_of="2026-01-01")
    assert not quiet.sent and len(server.requests) == 1
    assert send_expiry_notification(server.url, [], as_of="2026-01-01", always=True).sent


def test_failures_are_reported_as_codes():
    failing = _Server(status=500)
    try:
        with pytest.raises(NotifyError) as caught:
            send_expiry_notification(failing.url, FINDINGS, as_of="2026-01-01")
        assert caught.value.code == "webhook_http_500"
    finally:
        failing.close()
    with pytest.raises(NotifyError) as down:
        send_expiry_notification("http://127.0.0.1:1/x", FINDINGS, as_of="2026-01-01")
    assert down.value.code == "webhook_unreachable"


def test_cli_notify(session, monkeypatch, server, capsys):
    source, _ = ingest_source(
        session,
        SourceCreate(
            title="a", uri="file:///1.md", content="Decision: Use X.\nReview by: 2020-01-01"
        ),
    )
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    main(["notify", "--webhook", server.url, "--as-of", "2026-01-01"])
    assert json.loads(capsys.readouterr().out)["sent"] is True
    assert server.requests[0]["items"][0]["decision_id"] == decision.id
    with pytest.raises(SystemExit) as caught:
        main(["notify", "--webhook", "http://example.com/x"])
    assert caught.value.code == 2
