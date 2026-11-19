import importlib.util
import json
from pathlib import Path

import pytest

root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "pr_gate_comment", root / "scripts/pr_gate_comment.py"
)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_clean_report_says_evidence_unchanged():
    body = gate.build_comment({"valid": True, "findings": [], "blocking_count": 0}, None)
    assert gate.MARKER in body
    assert "still cite unchanged evidence" in body


def test_findings_are_content_free_and_capped():
    findings = [
        {
            "decision_id": f"decision-{i:04d}-abcdef",
            "start_line": 3,
            "end_line": 5,
            "reason": "moved",
        }
        for i in range(25)
    ]
    body = gate.build_comment(
        {"valid": False, "findings": findings, "blocking_count": 25},
        {"findings": [1], "impacted_decision_count": 2, "root_review_count": 1},
    )
    assert "**25** decision(s)" in body
    assert body.count("| `decision-000") + body.count("| `decision-001") == 20
    assert "5 more in the SARIF report" in body
    assert "Downstream impact: **2**" in body
    assert "title" not in body.lower().replace("titles and quotes", "")


def test_missing_report_is_reported():
    assert "No decision report" in gate.build_comment(None, None)


def test_upsert_updates_existing_marker_comment_else_creates():
    calls = []

    def request(method, path, payload):
        calls.append((method, path))
        if method == "GET":
            return existing
        return {}

    existing = [{"id": 1, "body": "other"}, {"id": 9, "body": f"{gate.MARKER} old"}]
    assert gate.upsert_comment(request, "o/r", 7, "new") == "updated"
    assert calls[-1] == ("PATCH", "/repos/o/r/issues/comments/9")
    existing = [{"id": 1, "body": "other"}]
    assert gate.upsert_comment(request, "o/r", 7, "new") == "created"
    assert calls[-1] == ("POST", "/repos/o/r/issues/7/comments")


def test_api_url_must_be_https():
    with pytest.raises(ValueError, match="github_api_url_must_be_https"):
        gate.github_request("http://example.test", "t")


def test_main_skips_without_pull_request_event(tmp_path, monkeypatch, capsys):
    report = tmp_path / "d.json"
    report.write_text(json.dumps({"valid": True, "findings": []}))
    event = tmp_path / "event.json"
    event.write_text("{}")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert gate.main(["--decisions", str(report)]) == 0
    assert "not a pull_request event" in capsys.readouterr().err


def test_action_exposes_opt_in_comment_step():
    import yaml

    action = yaml.safe_load((root / "action.yml").read_text(encoding="utf-8"))
    assert action["inputs"]["comment"]["default"] == "false"
    step = next(
        s for s in action["runs"]["steps"] if s.get("name") == "Comment on the pull request"
    )
    assert step["if"] == "always() && inputs.comment == 'true'"
    assert "pr_gate_comment.py" in step["run"]
