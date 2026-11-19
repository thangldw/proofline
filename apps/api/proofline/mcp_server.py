"""Read-only local MCP server over stdio.

Speaks newline-delimited JSON-RPC 2.0 (the MCP stdio transport) and exposes deterministic decision
checks to a local MCP client. It never writes, never opens a network socket, and omits decision
titles unless the operator starts it with ``--include-titles``: titles reach whatever model the
client uses, so disclosure is an explicit choice.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from . import __version__
from .database import SessionLocal, engine
from .decision_blame import DecisionBlameError, blame
from .decision_health import DecisionHealthError, check_decision_health
from .decision_impacts import compute_decision_impacts
from .integrity import IntegrityVerificationError, verify_live_database
from .models import Decision, Workspace, utc_now
from .retrieval import lexical_search

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_LINE_BYTES = 1_000_000
MAX_LIST_LIMIT = 100
MAX_QUERY_CHARS = 500
MAX_EXCERPT_CHARS = 400
MAX_TARGET_CHARS = 300
TITLE_KEYS = ("root_decision_title", "impacted_decision_title")

TOOLS: list[dict[str, Any]] = [
    {
        "name": "blame_location",
        "description": (
            "List approved decisions anchored at a source path (optionally one line of its current "
            "version), with their anchor state and current line span. Titles only if enabled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "minLength": 1, "maxLength": MAX_TARGET_CHARS},
                "line": {"type": "integer", "minimum": 1},
            },
            "required": ["target"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_evidence",
        "description": (
            "Lexical search over current source versions. Returns chunk identifiers and line "
            "spans; excerpts and source titles are included only if the operator enabled them."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_decisions",
        "description": (
            "List approved decisions whose cited evidence no longer resolves unchanged in the "
            "current source. Deterministic and read-only; returns identifiers, spans and reasons."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "check_impacts",
        "description": (
            "List decisions transitively impacted, through based_on/implements relations, by a "
            "decision that is awaiting review."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_decisions",
        "description": "List decision identifiers and statuses, optionally filtered by status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "maxLength": 40},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIST_LIMIT},
            },
            "additionalProperties": False,
        },
    },
]


@dataclass(frozen=True)
class Disclosure:
    """What the operator allowed to leave this process toward the client's model."""

    titles: bool = False
    excerpts: bool = False


class ToolError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _text(document: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(document, sort_keys=True)}]}


def _tool_check_decisions(arguments: dict[str, Any], disclosure: Disclosure) -> Any:
    with SessionLocal() as session:
        findings = check_decision_health(session)
    dump = (
        (lambda item: item.model_dump())
        if disclosure.titles
        else (lambda item: item.content_free_model_dump())
    )
    return {"finding_count": len(findings), "findings": [dump(item) for item in findings]}


def _tool_check_impacts(arguments: dict[str, Any], disclosure: Disclosure) -> Any:
    evaluated_at = utc_now()
    with SessionLocal() as session:
        verify_live_database(engine)
        workspace_ids = session.scalars(select(Workspace.id).order_by(Workspace.id)).all()
        findings = [
            finding
            for workspace_id in workspace_ids
            for finding in compute_decision_impacts(
                session, workspace_id=workspace_id, as_of=evaluated_at
            )
        ]
    documents = [item.model_dump() for item in findings]
    if not disclosure.titles:
        for document in documents:
            for key in TITLE_KEYS:
                document.pop(key, None)
    return {"finding_count": len(documents), "findings": documents}


def _tool_list_decisions(arguments: dict[str, Any], disclosure: Disclosure) -> Any:
    unknown = set(arguments) - {"status", "limit"}
    status = arguments.get("status")
    limit = arguments.get("limit", 50)
    if unknown or (status is not None and not isinstance(status, str)):
        raise ToolError("arguments_invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIST_LIMIT:
        raise ToolError("arguments_invalid")
    statement = select(Decision).order_by(Decision.id).limit(limit)
    if status:
        statement = statement.where(Decision.status == status)
    with SessionLocal() as session:
        rows = session.scalars(statement).all()
        decisions = []
        for row in rows:
            item: dict[str, Any] = {"id": row.id, "kind": row.kind, "status": row.status}
            if disclosure.titles:
                item["title"] = row.title
            decisions.append(item)
    return {"decisions": decisions}


def _tool_search_evidence(arguments: dict[str, Any], disclosure: Disclosure) -> Any:
    query = arguments.get("query")
    limit = arguments.get("limit", 5)
    if set(arguments) - {"query", "limit"} or not isinstance(query, str):
        raise ToolError("arguments_invalid")
    if not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise ToolError("arguments_invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ToolError("arguments_invalid")
    with SessionLocal() as session:
        hits = lexical_search(session, query, limit=limit)
    results = []
    for hit in hits:
        item: dict[str, Any] = {
            "chunk_id": hit.chunk_id,
            "source_id": hit.source_id,
            "source_version_id": hit.source_version_id,
            "start_line": hit.start_line,
            "end_line": hit.end_line,
        }
        if disclosure.titles:
            item["source_title"] = hit.source_title
        if disclosure.excerpts:
            item["excerpt"] = hit.content[:MAX_EXCERPT_CHARS]
        results.append(item)
    return {"result_count": len(results), "results": results}


def _tool_blame_location(arguments: dict[str, Any], disclosure: Disclosure) -> Any:
    target = arguments.get("target")
    line = arguments.get("line")
    if set(arguments) - {"target", "line"} or not isinstance(target, str):
        raise ToolError("arguments_invalid")
    if not target.strip() or len(target) > MAX_TARGET_CHARS:
        raise ToolError("arguments_invalid")
    if line is not None and (isinstance(line, bool) or not isinstance(line, int) or line < 1):
        raise ToolError("arguments_invalid")
    try:
        with SessionLocal() as session:
            entries = blame(session, target, line)
    except DecisionBlameError as exc:
        raise ToolError(exc.code) from exc
    dump = (
        (lambda item: item.model_dump())
        if disclosure.titles
        else (lambda item: item.content_free_model_dump())
    )
    return {"entry_count": len(entries), "entries": [dump(item) for item in entries]}


HANDLERS: dict[str, Callable[[dict[str, Any], Disclosure], Any]] = {
    "blame_location": _tool_blame_location,
    "check_decisions": _tool_check_decisions,
    "check_impacts": _tool_check_impacts,
    "list_decisions": _tool_list_decisions,
    "search_evidence": _tool_search_evidence,
}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _call_tool(params: Any, disclosure: Disclosure) -> dict[str, Any]:
    if not isinstance(params, dict) or not isinstance(params.get("name"), str):
        raise ToolError("params_invalid")
    handler = HANDLERS.get(params["name"])
    if handler is None:
        raise ToolError("tool_unknown")
    arguments = params.get("arguments", {})
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolError("arguments_invalid")
    try:
        return _text(handler(arguments, disclosure))
    except ToolError:
        raise
    except (DecisionHealthError, IntegrityVerificationError) as exc:
        raise ToolError(exc.code) from exc
    except (OSError, SQLAlchemyError) as exc:
        raise ToolError("database_unavailable") from exc


def handle_message(
    message: Any, *, include_titles: bool = False, include_excerpts: bool = False
) -> dict[str, Any] | None:
    """Return the JSON-RPC response for one message, or ``None`` for notifications."""

    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "invalid_request")
    method = message.get("method")
    request_id = message.get("id")
    is_notification = "id" not in message
    if not isinstance(method, str):
        return _error(request_id, -32600, "invalid_request")
    if is_notification:
        return None  # notifications/initialized, notifications/cancelled, ... need no reply
    params = message.get("params")
    result: dict[str, Any]
    if method == "initialize":
        requested = params.get("protocolVersion") if isinstance(params, dict) else None
        version = requested if requested in SUPPORTED_PROTOCOLS else PROTOCOL_VERSION
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "proofline", "version": __version__},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            result = _call_tool(params, Disclosure(include_titles, include_excerpts))
        except ToolError as exc:
            result = {
                "isError": True,
                "content": [{"type": "text", "text": json.dumps({"error": exc.code})}],
            }
    else:
        return _error(request_id, -32601, "method_not_found")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve_stdio(
    stdin: IO[str],
    stdout: IO[str],
    *,
    include_titles: bool = False,
    include_excerpts: bool = False,
) -> None:
    for line in stdin:
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            response: dict[str, Any] | None = _error(None, -32600, "request_too_large")
        else:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response = _error(None, -32700, "parse_error")
            else:
                response = handle_message(
                    message, include_titles=include_titles, include_excerpts=include_excerpts
                )
        if response is not None:
            stdout.write(json.dumps(response, sort_keys=True) + "\n")
            stdout.flush()
