import json
from pathlib import Path

import pytest
from proofline.cli import main
from proofline.model_gateway import OpenAICompatibleProvider
from proofline.real_model_evaluation import (
    RealModelComparisonPlan,
    preflight_real_model_plan,
    write_preflight_receipt,
)
from pydantic import ValidationError


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def comparison_plan(tmp_path: Path) -> Path:
    root = repository_root()
    plan = tmp_path / "comparison.json"
    plan.write_text(
        json.dumps(
            {
                "schema_version": "proofline.real-model-comparison.v1",
                "extraction_dataset": str(root / "evals/extraction/seed-v1.json"),
                "grounded_dataset": str(root / "evals/grounded-qa/seed-v1.json"),
                "providers": [
                    {
                        "name": "remote-qwen",
                        "locality": "remote",
                        "provider": "qwen",
                        "base_url": "https://example.invalid/v1",
                        "model_id": "qwen-pinned",
                        "model_revision": "revision-2026-07-13",
                        "api_key_env": "TEST_REMOTE_KEY",
                        "input_usd_per_million_tokens": 0.1,
                        "output_usd_per_million_tokens": 0.2,
                    },
                    {
                        "name": "local-qwen",
                        "locality": "local",
                        "provider": "ollama",
                        "base_url": "http://127.0.0.1:11434/v1",
                        "model_id": "qwen-local",
                        "model_revision": "sha256:local-model",
                        "input_usd_per_million_tokens": 0,
                        "output_usd_per_million_tokens": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return plan


def test_preflight_locks_datasets_models_prompts_and_pricing_without_secrets(tmp_path):
    plan = comparison_plan(tmp_path)

    receipt = preflight_real_model_plan(
        plan,
        environ={"TEST_REMOTE_KEY": "never-persist-this-secret"},
        health_check=lambda provider: True,
    )

    assert receipt.status == "ready"
    assert receipt.receipt_kind == "preflight"
    assert {dataset.kind for dataset in receipt.datasets} == {"extraction", "grounded_qa"}
    assert all(len(dataset.sha256) == 64 for dataset in receipt.datasets)
    assert {provider.locality for provider in receipt.providers} == {"local", "remote"}
    assert all(provider.model_revision for provider in receipt.providers)
    assert all(provider.prompt_versions for provider in receipt.providers)
    assert "estimated_cost_usd" in receipt.metric_definitions
    assert "never-persist-this-secret" not in receipt.model_dump_json()


def test_preflight_records_missing_remote_credential_as_an_explicit_blocker(tmp_path):
    receipt = preflight_real_model_plan(
        comparison_plan(tmp_path),
        environ={},
        health_check=lambda provider: True,
    )

    assert receipt.status == "blocked"
    remote = next(provider for provider in receipt.providers if provider.locality == "remote")
    assert remote.status == "blocked"
    assert remote.error_code == "credential_missing"


def test_plan_requires_both_local_and_remote_providers():
    provider = {
        "name": "local-only",
        "locality": "local",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "model_id": "qwen-local",
        "model_revision": "sha256:local-model",
        "input_usd_per_million_tokens": 0,
        "output_usd_per_million_tokens": 0,
    }

    with pytest.raises(ValidationError, match="at least one local and one remote"):
        RealModelComparisonPlan.model_validate(
            {
                "schema_version": "proofline.real-model-comparison.v1",
                "extraction_dataset": "extraction.json",
                "grounded_dataset": "grounded.json",
                "providers": [provider, {**provider, "name": "local-two"}],
            }
        )


def test_plan_rejects_unpinned_template_placeholders():
    with pytest.raises(ValidationError, match="must be pinned before preflight"):
        RealModelComparisonPlan.model_validate_json(
            (repository_root() / "evals/real-model/comparison-v1.example.json").read_text(
                encoding="utf-8"
            )
        )


def test_receipt_write_is_atomic_and_refuses_overwrite_without_force(tmp_path):
    receipt = preflight_real_model_plan(
        comparison_plan(tmp_path),
        environ={"TEST_REMOTE_KEY": "secret"},
        health_check=lambda provider: True,
    )
    output = tmp_path / "receipt.json"

    write_preflight_receipt(output, receipt)
    with pytest.raises(FileExistsError):
        write_preflight_receipt(output, receipt)
    write_preflight_receipt(output, receipt, force=True)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["plan_sha256"] == receipt.plan_sha256
    assert persisted["status"] == "ready"


def test_cli_writes_a_ready_receipt_without_printing_the_credential(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TEST_REMOTE_KEY", "cli-secret")
    monkeypatch.setattr(OpenAICompatibleProvider, "health", lambda self: True)
    output = tmp_path / "cli-receipt.json"

    main(
        [
            "eval-real-model-preflight",
            "--plan",
            str(comparison_plan(tmp_path)),
            "--output",
            str(output),
        ]
    )

    stdout = capsys.readouterr().out
    assert json.loads(stdout)["status"] == "ready"
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ready"
    assert "cli-secret" not in stdout
    assert "cli-secret" not in output.read_text(encoding="utf-8")
