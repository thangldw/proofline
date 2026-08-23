from pathlib import Path

import pytest
from proofline.decision_policy import (
    DecisionPolicyError,
    load_decision_policy,
    policy_sha256,
)

ROOT = Path(__file__).resolve().parents[3]


def test_default_policy_has_stable_contract_and_hash():
    policy = load_decision_policy(None)

    assert policy.version == 1
    assert policy.fail_on == frozenset({"moved", "ambiguous", "changed", "deleted"})
    assert policy.acknowledged_is_blocking is True
    assert policy.allow_waiver is True
    assert policy.max_open_age_days == 14
    assert (
        policy_sha256(policy) == "bd56673e3c8afb637fc700d33dc09f21506d7300b32946f364863eb74c51eeab"
    )


def test_committed_policy_matches_default_contract():
    assert load_decision_policy(ROOT / "proofline.toml") == load_decision_policy(None)


@pytest.mark.parametrize(
    ("document", "code"),
    [
        (
            'version = 1\nextra = true\n[decision_health]\nfail_on = ["changed"]\n',
            "policy_schema_invalid",
        ),
        (
            'version = 1\n[decision_health]\nfail_on = ["changed"]\nextra = true\n',
            "policy_schema_invalid",
        ),
        (
            'version = 2\n[decision_health]\nfail_on = ["changed"]\n',
            "policy_version_unsupported",
        ),
        (
            'version = 1\n[decision_health]\nfail_on = ["current"]\n',
            "policy_schema_invalid",
        ),
        (
            "version = 1\n[decision_health]\nacknowledged_is_blocking = 1\n",
            "policy_schema_invalid",
        ),
        (
            "version = 1\n[decision_health]\nmax_open_age_days = 0\n",
            "policy_schema_invalid",
        ),
    ],
)
def test_invalid_policy_fails_closed_with_content_free_code(tmp_path, document, code):
    policy_path = tmp_path / "private-policy.toml"
    policy_path.write_text(document, encoding="utf-8")

    with pytest.raises(DecisionPolicyError, match=f"^{code}$") as raised:
        load_decision_policy(policy_path)

    assert "private-policy" not in str(raised.value)


def test_malformed_and_missing_policy_have_distinct_codes(tmp_path):
    malformed = tmp_path / "malformed.toml"
    malformed.write_text("version = [", encoding="utf-8")

    with pytest.raises(DecisionPolicyError, match="^policy_toml_invalid$"):
        load_decision_policy(malformed)
    with pytest.raises(DecisionPolicyError, match="^policy_file_unavailable$"):
        load_decision_policy(tmp_path / "missing.toml")
