from __future__ import annotations

import json

from .decision_policy import BLOCKING_ANCHOR_STATES

SCHEMA_ID = "https://github.com/thangldw/proofline/spec/decision-policy/v1/schema.json"


def decision_policy_schema() -> dict[str, object]:
    """JSON Schema for `proofline.toml`, generated from the same constants the loader uses."""

    states = {"type": "string", "enum": sorted(BLOCKING_ANCHOR_STATES)}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Proofline decision policy",
        "type": "object",
        "required": ["version"],
        "additionalProperties": False,
        "properties": {
            "version": {"const": 1, "description": "Policy format version."},
            "decision_health": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fail_on": {
                        "type": "array",
                        "items": states,
                        "uniqueItems": True,
                        "description": "Anchor states that make check-decisions fail.",
                    },
                    "acknowledged_is_blocking": {"type": "boolean"},
                    "allow_waiver": {"type": "boolean"},
                    "max_open_age_days": {"type": "integer", "minimum": 1, "maximum": 3650},
                    "overrides": {
                        "type": "array",
                        "description": "Per-directory fail_on; the longest matching path wins.",
                        "items": {
                            "type": "object",
                            "required": ["path", "fail_on"],
                            "additionalProperties": False,
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "pattern": r"^(?!.*(^|/)\.\.(/|$))/*[^/]+.*$",
                                },
                                "fail_on": {
                                    "type": "array",
                                    "items": states,
                                    "uniqueItems": True,
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def render_policy_schema() -> str:
    return json.dumps(decision_policy_schema(), indent=2, sort_keys=True) + "\n"
