import json
from pathlib import Path

import proofline.cli as cli_module
import pytest
from proofline.cli import main
from proofline.model_gateway import (
    GenerationRequest,
    GenerationResult,
    ModelCapabilities,
    OpenAICompatibleProvider,
)
from proofline.real_model_evaluation import (
    RealModelComparisonPlan,
    preflight_real_model_plan,
    run_real_model_comparison,
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


class MockComparisonProvider:
    def __init__(self, provider_id: str, model: str) -> None:
        self.id = provider_id
        self.model = model

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities()

    def health(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.messages[-1].content)
        evidence = payload["evidence"]
        if request.template_version.startswith("memory-candidate-extraction"):
            content = " ".join(item["content"] for item in evidence)
            candidates = (
                []
                if "No architectural choice" in content
                else [
                    {
                        "kind": "decision",
                        "statement": "Use SQLite for local metadata.",
                        "rationale": None,
                        "confidence": 0.9,
                        "evidence_ids": [evidence[0]["evidence_id"]],
                    }
                ]
            )
            response = {"candidates": candidates}
        else:
            response = {
                "statements": [
                    {
                        "text": "SQLite is the local metadata store.",
                        "kind": "direct",
                        "evidence_ids": [evidence[0]["evidence_id"]],
                    }
                ]
            }
        return GenerationResult(content=json.dumps(response), prompt_tokens=11, completion_tokens=7)


class FailingMockComparisonProvider(MockComparisonProvider):
    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise RuntimeError("sensitive provider detail must not enter the receipt")


def mock_comparison_plan(tmp_path: Path) -> Path:
    extraction = tmp_path / "model-extraction.json"
    extraction.write_text(
        json.dumps(
            {
                "version": "model-extraction-test-v1",
                "provenance": "synthetic-mock-integration",
                "description": "Synthetic mock transport integration fixture.",
                "sources": [
                    {
                        "title": "Storage decision",
                        "uri": "mock://extraction/storage",
                        "content": "Use SQLite for local metadata.",
                        "expected_memories": [
                            {
                                "kind": "decision",
                                "statement": "Use SQLite for local metadata.",
                                "status": "active",
                                "evidence_quote": "Use SQLite for local metadata.",
                            }
                        ],
                    },
                    {
                        "title": "Negative source",
                        "uri": "mock://extraction/negative",
                        "content": "No architectural choice is recorded here.",
                        "expected_memories": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    grounded = tmp_path / "model-grounded.json"
    grounded.write_text(
        json.dumps(
            {
                "version": "model-grounded-test-v1",
                "provenance": "synthetic-mock-integration",
                "description": "Synthetic mock transport integration fixture.",
                "sources": [
                    {
                        "title": "Storage ADR",
                        "uri": "mock://grounded/storage",
                        "content": "SQLite is the local metadata store.",
                    }
                ],
                "queries": [
                    {
                        "id": "grounded-storage",
                        "question": "What is the local metadata store?",
                        "expected_status": "grounded",
                        "expected_statements": [
                            {
                                "text": "SQLite is the local metadata store.",
                                "kind": "direct",
                                "supporting_source_uris": ["mock://grounded/storage"],
                            }
                        ],
                    },
                    {
                        "id": "abstain-broker",
                        "question": "Which Kafka broker is deployed?",
                        "expected_status": "insufficient_evidence",
                        "expected_statements": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    payload = json.loads(comparison_plan(tmp_path).read_text(encoding="utf-8"))
    payload["extraction_dataset"] = str(extraction)
    payload["grounded_dataset"] = str(grounded)
    for provider in payload["providers"]:
        provider["execution_mode"] = "mock"
    plan = tmp_path / "mock-comparison.json"
    plan.write_text(json.dumps(payload), encoding="utf-8")
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


def test_mock_comparison_runs_production_paths_and_is_never_real_model_evidence(tmp_path):
    def provider_factory(spec, api_key):
        if spec.locality == "remote":
            assert api_key == "mock-api-key"
        return MockComparisonProvider(spec.provider, spec.model_id)

    receipt = run_real_model_comparison(
        mock_comparison_plan(tmp_path),
        environ={"TEST_REMOTE_KEY": "mock-api-key"},
        health_check=lambda provider: True,
        provider_factory=provider_factory,
    )

    assert receipt.status == "completed"
    assert receipt.evidence_class == "mock_integration"
    assert "not real-model" in receipt.qualification
    assert "mock-api-key" not in receipt.model_dump_json()
    assert len(receipt.providers) == 2
    for provider in receipt.providers:
        assert provider.status == "completed"
        assert provider.extraction.precision == 1
        assert provider.extraction.recall == 1
        assert provider.extraction.negative_source_accuracy == 1
        assert provider.extraction.evidence_resolution == 1
        assert provider.grounded_qa.citation_precision == 1
        assert provider.grounded_qa.expected_status_accuracy == 1
        assert provider.abstention_accuracy == 1
        assert provider.usage.call_count == 3
        assert provider.usage.prompt_tokens == 33
        assert provider.usage.completion_tokens == 21
    remote = next(provider for provider in receipt.providers if provider.locality == "remote")
    assert remote.usage.estimated_cost_usd == pytest.approx(7.5e-6)


def test_plan_rejects_mixed_mock_and_real_evidence_classes(tmp_path):
    payload = json.loads(mock_comparison_plan(tmp_path).read_text(encoding="utf-8"))
    payload["providers"][0]["execution_mode"] = "real"

    with pytest.raises(ValidationError, match="cannot mix mock and real"):
        RealModelComparisonPlan.model_validate(payload)


def test_mock_plan_cannot_call_real_transport_without_an_injected_factory(tmp_path):
    with pytest.raises(ValueError, match="requires an injected provider factory"):
        run_real_model_comparison(
            mock_comparison_plan(tmp_path),
            environ={"TEST_REMOTE_KEY": "mock-api-key"},
        )


def test_comparison_cli_writes_the_qualified_receipt(tmp_path, monkeypatch, capsys):
    receipt = run_real_model_comparison(
        mock_comparison_plan(tmp_path),
        environ={"TEST_REMOTE_KEY": "mock-api-key"},
        health_check=lambda provider: True,
        provider_factory=lambda spec, api_key: MockComparisonProvider(spec.provider, spec.model_id),
    )
    monkeypatch.setattr(cli_module, "run_real_model_comparison", lambda path: receipt)
    output = tmp_path / "comparison-receipt.json"

    main(
        [
            "eval-real-model",
            "--plan",
            str(tmp_path / "unused-by-mock.json"),
            "--output",
            str(output),
        ]
    )

    stdout = json.loads(capsys.readouterr().out)
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert stdout["evidence_class"] == "mock_integration"
    assert persisted["status"] == "completed"


def test_provider_failure_is_sanitized_and_does_not_discard_other_results(tmp_path):
    def provider_factory(spec, api_key):
        provider_type = (
            FailingMockComparisonProvider if spec.locality == "remote" else MockComparisonProvider
        )
        return provider_type(spec.provider, spec.model_id)

    receipt = run_real_model_comparison(
        mock_comparison_plan(tmp_path),
        environ={"TEST_REMOTE_KEY": "mock-api-key"},
        health_check=lambda provider: True,
        provider_factory=provider_factory,
    )

    assert receipt.status == "partial"
    remote = next(provider for provider in receipt.providers if provider.locality == "remote")
    local = next(provider for provider in receipt.providers if provider.locality == "local")
    assert remote.status == "failed"
    assert remote.error_code == "provider_evaluation_failed"
    assert remote.usage.failed_count == 1
    assert local.status == "completed"
    assert "sensitive provider detail" not in receipt.model_dump_json()
