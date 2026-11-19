import json
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from proofline.cli import main
from proofline.decision_policy import DecisionPolicyError, _parse_policy
from proofline.policy_schema import decision_policy_schema, render_policy_schema

ROOT = Path(__file__).resolve().parents[3]

CASES = [
    "version = 1",
    'version = 1\n[decision_health]\nfail_on = ["moved", "changed"]\nmax_open_age_days = 30',
    'version = 1\n[decision_health]\noverrides = [{path = "docs/adr", fail_on = ["moved"]}]',
    "version = 2",
    'version = 1\n[decision_health]\nfail_on = ["moved", "moved"]',
    'version = 1\n[decision_health]\nfail_on = ["nonsense"]',
    "version = 1\n[decision_health]\nmax_open_age_days = 0",
    "version = 1\n[decision_health]\nmax_open_age_days = 4000",
    'version = 1\n[decision_health]\nallow_waiver = "yes"',
    "version = 1\n[decision_health]\nunknown = 1",
    "version = 1\nextra = 1",
    'version = 1\n[decision_health]\noverrides = [{path = "../x", fail_on = []}]',
    'version = 1\n[decision_health]\noverrides = [{path = "a", fail_on = [], more = 1}]',
    'version = 1\n[decision_health]\noverrides = [{path = "a"}]',
    "[decision_health]\nfail_on = []",
]


@pytest.mark.parametrize("source", CASES)
def test_schema_agrees_with_the_loader(source):
    document = tomllib.loads(source)
    schema_valid = Draft202012Validator(decision_policy_schema()).is_valid(document)
    try:
        _parse_policy(document)
        loader_valid = True
    except DecisionPolicyError:
        loader_valid = False
    assert schema_valid == loader_valid, source


def test_committed_schema_matches_generated_and_is_a_valid_schema():
    committed = (ROOT / "spec/decision-policy/v1/schema.json").read_text()
    assert committed == render_policy_schema()
    Draft202012Validator.check_schema(json.loads(committed))


def test_repository_policy_file_validates():
    document = tomllib.loads((ROOT / "proofline.toml").read_text())
    assert Draft202012Validator(decision_policy_schema()).is_valid(document)


def test_cli_prints_schema(capsys):
    main(["policy-schema"])
    assert json.loads(capsys.readouterr().out)["title"] == "Proofline decision policy"
