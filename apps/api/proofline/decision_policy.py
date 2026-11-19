from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

BLOCKING_ANCHOR_STATES = frozenset({"moved", "ambiguous", "changed", "deleted"})


class DecisionPolicyError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DecisionHealthPolicy:
    version: int = 1
    fail_on: frozenset[str] = BLOCKING_ANCHOR_STATES
    acknowledged_is_blocking: bool = True
    allow_waiver: bool = True
    max_open_age_days: int = 14
    overrides: tuple[tuple[str, frozenset[str]], ...] = ()

    def fail_on_for(self, source_uri: str | None) -> frozenset[str]:
        """States that block for a source: the longest matching directory override, else global."""

        if source_uri is None:
            return self.fail_on
        haystack = "/" + source_uri.replace("\\", "/").split("//", 1)[-1].lstrip("/") + "/"
        best: tuple[str, frozenset[str]] | None = None
        for path, states in self.overrides:
            if f"/{path}/" in haystack and (best is None or len(path) > len(best[0])):
                best = (path, states)
        return best[1] if best else self.fail_on


def _schema_error() -> DecisionPolicyError:
    return DecisionPolicyError("policy_schema_invalid")


def _parse_overrides(value: object) -> tuple[tuple[str, frozenset[str]], ...]:
    if not isinstance(value, list):
        raise _schema_error()
    parsed: dict[str, frozenset[str]] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "fail_on"}:
            raise _schema_error()
        path, states = item["path"], item["fail_on"]
        if (
            type(path) is not str
            or not path.strip("/")
            or ".." in path.split("/")
            or not isinstance(states, list)
            or any(
                type(state) is not str or state not in BLOCKING_ANCHOR_STATES for state in states
            )
            or len(states) != len(set(states))
        ):
            raise _schema_error()
        key = path.strip("/")
        if key in parsed:
            raise _schema_error()
        parsed[key] = frozenset(states)
    return tuple(sorted(parsed.items()))


def _parse_policy(document: object) -> DecisionHealthPolicy:
    if not isinstance(document, dict) or set(document) - {"version", "decision_health"}:
        raise _schema_error()
    version = document.get("version")
    if type(version) is not int:
        raise _schema_error()
    if version != 1:
        raise DecisionPolicyError("policy_version_unsupported")

    values = document.get("decision_health", {})
    if not isinstance(values, dict) or set(values) - {
        "fail_on",
        "acknowledged_is_blocking",
        "allow_waiver",
        "max_open_age_days",
        "overrides",
    }:
        raise _schema_error()

    fail_on = values.get("fail_on", sorted(BLOCKING_ANCHOR_STATES))
    acknowledged_is_blocking = values.get("acknowledged_is_blocking", True)
    allow_waiver = values.get("allow_waiver", True)
    max_open_age_days = values.get("max_open_age_days", 14)
    overrides = _parse_overrides(values.get("overrides", []))
    if (
        not isinstance(fail_on, list)
        or any(type(value) is not str or value not in BLOCKING_ANCHOR_STATES for value in fail_on)
        or len(fail_on) != len(set(fail_on))
        or type(acknowledged_is_blocking) is not bool
        or type(allow_waiver) is not bool
        or type(max_open_age_days) is not int
        or not 1 <= max_open_age_days <= 3650
    ):
        raise _schema_error()
    return DecisionHealthPolicy(
        fail_on=frozenset(fail_on),
        acknowledged_is_blocking=acknowledged_is_blocking,
        allow_waiver=allow_waiver,
        max_open_age_days=max_open_age_days,
        overrides=overrides,
    )


def load_decision_policy(path: Path | None) -> DecisionHealthPolicy:
    if path is None:
        return DecisionHealthPolicy()
    try:
        content = path.expanduser().resolve().read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DecisionPolicyError("policy_file_unavailable") from exc
    try:
        document = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        raise DecisionPolicyError("policy_toml_invalid") from exc
    return _parse_policy(document)


def policy_sha256(policy: DecisionHealthPolicy) -> str:
    document: dict[str, object] = {
        "acknowledged_is_blocking": policy.acknowledged_is_blocking,
        "allow_waiver": policy.allow_waiver,
        "fail_on": sorted(policy.fail_on),
        "max_open_age_days": policy.max_open_age_days,
        "version": policy.version,
    }
    if policy.overrides:
        document["overrides"] = [[path, sorted(states)] for path, states in policy.overrides]
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
