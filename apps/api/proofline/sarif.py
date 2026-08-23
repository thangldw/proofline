from __future__ import annotations

from collections.abc import Iterable

from . import __version__
from .decision_health import DecisionHealthFinding
from .decision_impacts import DecisionImpactFinding
from .decision_policy import DecisionHealthPolicy, policy_sha256
from .decision_reviews import review_fingerprint

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
RULE_STATES = ("ambiguous", "changed", "deleted", "moved")


def _result(finding: DecisionHealthFinding) -> dict:
    start_line = finding.candidate_start_line or finding.start_line
    end_line = finding.candidate_end_line or finding.end_line
    fingerprint = review_fingerprint(
        decision_id=finding.decision_id,
        evidence_id=finding.evidence_id,
        cited_source_version_id=finding.cited_source_version_id,
        current_source_version_id=finding.current_source_version_id,
        anchor_state=finding.reason,
    )
    return {
        "ruleId": f"proofline/{finding.reason}",
        "level": "error" if getattr(finding, "severity", "warning") == "error" else "warning",
        "message": {"text": f"Decision evidence is {finding.reason}; review required."},
        "partialFingerprints": {"prooflineFinding/v1": fingerprint},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": finding.source_uri or f"proofline://sources/{finding.source_id}"
                    },
                    "region": {"startLine": start_line, "endLine": end_line},
                }
            }
        ],
        "properties": {
            "anchorState": finding.reason,
            "citedSourceVersionId": finding.cited_source_version_id,
            "currentSourceVersionId": finding.current_source_version_id,
            "decisionId": finding.decision_id,
            "evidenceId": finding.evidence_id,
        },
    }


def build_decision_health_sarif(
    findings: Iterable[DecisionHealthFinding],
    policy: DecisionHealthPolicy,
) -> dict:
    ordered = sorted(
        findings,
        key=lambda item: (
            item.source_uri or "",
            item.candidate_start_line or item.start_line,
            item.decision_id,
            item.evidence_id,
        ),
    )
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Proofline",
                        "semanticVersion": __version__,
                        "informationUri": "https://github.com/thangldw/proofline",
                        "rules": [
                            {
                                "id": f"proofline/{state}",
                                "shortDescription": {
                                    "text": f"Decision evidence anchor is {state}"
                                },
                                "defaultConfiguration": {"level": "warning"},
                            }
                            for state in RULE_STATES
                        ],
                    }
                },
                "properties": {"policySha256": policy_sha256(policy)},
                "results": [_result(finding) for finding in ordered],
            }
        ],
    }


def build_decision_impact_sarif(findings: Iterable[DecisionImpactFinding]) -> dict:
    ordered = sorted(
        findings,
        key=lambda item: (
            item.root_review_id,
            item.depth,
            item.relation_path,
            item.impacted_decision_id,
        ),
    )
    evaluated_at = ordered[0].evaluated_at.isoformat() if ordered else None
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Proofline",
                        "semanticVersion": __version__,
                        "informationUri": "https://github.com/thangldw/proofline",
                        "rules": [
                            {
                                "id": "proofline/transitive-impact",
                                "shortDescription": {
                                    "text": "Decision is transitively exposed to stale evidence"
                                },
                                "defaultConfiguration": {"level": "warning"},
                            }
                        ],
                    }
                },
                "properties": {"evaluatedAt": evaluated_at},
                "results": [
                    {
                        "ruleId": "proofline/transitive-impact",
                        "level": "warning",
                        "message": {
                            "text": (
                                "Explicit dependency path leads to an unresolved evidence review."
                            )
                        },
                        "partialFingerprints": {"prooflineImpact/v1": item.fingerprint},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": (
                                            f"proofline://decisions/{item.impacted_decision_id}"
                                        )
                                    }
                                }
                            }
                        ],
                        "properties": {
                            "rootReviewId": item.root_review_id,
                            "rootDecisionId": item.root_decision_id,
                            "impactedDecisionId": item.impacted_decision_id,
                            "depth": item.depth,
                            "decisionPath": list(item.decision_path),
                            "relationPath": list(item.relation_path),
                            "relationKinds": list(item.relation_kinds),
                        },
                    }
                    for item in ordered
                ],
            }
        ],
    }
