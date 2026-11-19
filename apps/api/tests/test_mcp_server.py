import io
import json
import os
import subprocess
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from proofline import mcp_server
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def rpc(method, params=None, request_id=1, **extra):
    message = {"jsonrpc": "2.0", "method": method, **extra}
    if request_id is not None:
        message["id"] = request_id
    if params is not None:
        message["params"] = params
    return message


def call(name, arguments=None, *, include_titles=False, include_excerpts=False):
    response = mcp_server.handle_message(
        rpc("tools/call", {"name": name, "arguments": arguments or {}}),
        include_titles=include_titles,
        include_excerpts=include_excerpts,
    )
    assert response is not None
    return response["result"]


def test_initialize_negotiates_protocol_and_advertises_tools_only():
    response = mcp_server.handle_message(rpc("initialize", {"protocolVersion": "2025-03-26"}))
    result = response["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "proofline"
    fallback = mcp_server.handle_message(rpc("initialize", {"protocolVersion": "1999-01-01"}))
    assert fallback["result"]["protocolVersion"] == mcp_server.PROTOCOL_VERSION


def test_notifications_get_no_reply_and_unknown_methods_error():
    assert mcp_server.handle_message(rpc("notifications/initialized", request_id=None)) is None
    assert mcp_server.handle_message(rpc("ping"))["result"] == {}
    assert mcp_server.handle_message(rpc("resources/list"))["error"]["code"] == -32601
    assert mcp_server.handle_message([1, 2])["error"]["code"] == -32600
    assert mcp_server.handle_message({"jsonrpc": "1.0", "id": 1})["error"]["code"] == -32600


def test_tool_list_is_read_only_and_closed():
    tools = mcp_server.handle_message(rpc("tools/list"))["result"]["tools"]
    assert {tool["name"] for tool in tools} == {
        "check_decisions",
        "check_impacts",
        "list_decisions",
        "search_evidence",
        "blame_location",
    }
    assert all(tool["inputSchema"]["additionalProperties"] is False for tool in tools)


@pytest.mark.parametrize(
    "params",
    [None, {}, {"name": 5}, {"name": "nope"}, {"name": "list_decisions", "arguments": []}],
)
def test_bad_tool_calls_return_tool_errors_not_crashes(params):
    result = mcp_server.handle_message(rpc("tools/call", params))["result"]
    assert result["isError"] is True
    assert set(json.loads(result["content"][0]["text"])) == {"error"}


@pytest.fixture()
def seeded(session, monkeypatch):
    bind = session.get_bind()
    monkeypatch.setattr(mcp_server, "SessionLocal", sessionmaker(bind=bind, expire_on_commit=False))
    monkeypatch.setattr(mcp_server, "engine", bind)
    content = "Decision: Use SQLite.\nReason: local."
    source, _ = ingest_source(
        session, SourceCreate(title="adr", uri="file:///adr.md", content=content)
    )
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    changed = "Decision: Use NATS.\nReason: network."
    ingest_source(session, SourceCreate(title="adr", uri=source.uri, content=changed))
    return decision.id, decision.title


def test_check_decisions_is_content_free_unless_titles_are_enabled(seeded):
    decision_id, title = seeded
    result = call("check_decisions")
    body = json.loads(result["content"][0]["text"])
    assert body["finding_count"] >= 1
    assert decision_id in {item["decision_id"] for item in body["findings"]}
    assert title not in result["content"][0]["text"]
    with_titles = call("check_decisions", include_titles=True)["content"][0]["text"]
    assert title in with_titles


def test_list_decisions_filters_validates_and_hides_titles(seeded):
    decision_id, title = seeded
    body = json.loads(call("list_decisions", {"status": "accepted"})["content"][0]["text"])
    assert decision_id in {item["id"] for item in body["decisions"]}
    assert all("title" not in item for item in body["decisions"])
    for bad in ({"limit": 0}, {"limit": 101}, {"limit": True}, {"status": 3}, {"extra": 1}):
        assert call("list_decisions", bad)["isError"] is True
    titled = json.loads(call("list_decisions", include_titles=True)["content"][0]["text"])
    assert title in {item["title"] for item in titled["decisions"]}


def test_check_impacts_runs_and_strips_titles(seeded):
    body = json.loads(call("check_impacts")["content"][0]["text"])
    assert body["finding_count"] == 0 and body["findings"] == []


def test_stdio_loop_survives_garbage_and_oversized_lines():
    lines = [
        "not json",
        "",
        json.dumps(rpc("ping", request_id=7)),
        "x" * (mcp_server.MAX_LINE_BYTES + 1),
        json.dumps(rpc("notifications/initialized", request_id=None)),
    ]
    out = io.StringIO()
    mcp_server.serve_stdio(io.StringIO("\n".join(lines) + "\n"), out)
    responses = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [item.get("error", {}).get("code") for item in responses] == [-32700, None, -32600]
    assert responses[1] == {"id": 7, "jsonrpc": "2.0", "result": {}}


def test_cli_mcp_speaks_json_rpc_over_a_real_subprocess(tmp_path):
    env = {**os.environ, "PROOFLINE_HOME": str(tmp_path), "PROOFLINE_AI_PROVIDER": "disabled"}
    requests = "\n".join(
        json.dumps(item)
        for item in (
            rpc("initialize", {"protocolVersion": mcp_server.PROTOCOL_VERSION}),
            rpc("notifications/initialized", request_id=None),
            rpc("tools/list", request_id=2),
        )
    )
    completed = subprocess.run(
        [sys.executable, "-m", "proofline.cli", "mcp"],
        input=requests + "\n",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [reply["id"] for reply in replies] == [1, 2]
    assert len(replies[1]["result"]["tools"]) == 5


JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=20),
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=10), children, max_size=4)
    ),
    max_leaves=12,
)


@settings(max_examples=200, deadline=None)
@given(
    message=JSON_VALUES
    | st.fixed_dictionaries(
        {"jsonrpc": st.just("2.0")},
        optional={"id": JSON_VALUES, "method": JSON_VALUES, "params": JSON_VALUES},
    )
)
def test_handle_message_never_raises_on_arbitrary_json(message):
    response = mcp_server.handle_message(message)
    assert response is None or response["jsonrpc"] == "2.0"


def test_search_evidence_returns_spans_and_discloses_text_only_when_enabled(seeded):
    arguments = {"query": "NATS network"}
    plain = call("search_evidence", arguments)["content"][0]["text"]
    body = json.loads(plain)
    assert body["result_count"] >= 1
    first = body["results"][0]
    assert {"chunk_id", "source_id", "start_line", "end_line"} <= set(first)
    assert "NATS" not in plain and "adr" not in first.values()
    assert "excerpt" not in first and "source_title" not in first
    with_excerpt = json.loads(
        call("search_evidence", arguments, include_excerpts=True)["content"][0]["text"]
    )
    assert "NATS" in with_excerpt["results"][0]["excerpt"]
    assert len(with_excerpt["results"][0]["excerpt"]) <= mcp_server.MAX_EXCERPT_CHARS
    titled = json.loads(
        call("search_evidence", arguments, include_titles=True)["content"][0]["text"]
    )
    assert titled["results"][0]["source_title"] == "adr"


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": ""},
        {"query": "  "},
        {"query": 3},
        {"query": "x" * 501},
        {"query": "a", "limit": 0},
        {"query": "a", "limit": 21},
        {"query": "a", "extra": 1},
    ],
)
def test_search_evidence_rejects_bad_arguments(arguments):
    assert call("search_evidence", arguments)["isError"] is True


def test_blame_location_is_content_free_unless_titles_are_enabled(seeded):
    decision_id, title = seeded
    plain = call("blame_location", {"target": "adr.md"})["content"][0]["text"]
    assert title not in plain
    body = json.loads(plain)
    assert body["entry_count"] >= 0
    titled = json.loads(
        call("blame_location", {"target": "adr.md"}, include_titles=True)["content"][0]["text"]
    )
    assert all("decision_title" in item for item in titled["entries"])


@pytest.mark.parametrize(
    "arguments",
    [{}, {"target": ""}, {"target": 3}, {"target": "a", "line": 0}, {"target": "a", "line": True}]
    + [{"target": "a", "extra": 1}, {"target": "x" * 301}],
)
def test_blame_location_rejects_bad_arguments(arguments):
    assert call("blame_location", arguments)["isError"] is True
