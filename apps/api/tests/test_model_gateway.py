import json

import httpx
import pytest
from proofline.model_gateway import (
    ChatMessage,
    FakeGenerationProvider,
    GenerationRequest,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
    StructuredOutputError,
    run_generation,
)
from proofline.models import ModelRun
from pydantic import BaseModel
from sqlalchemy import select


class DecisionOutput(BaseModel):
    statement: str
    confidence: float


def request_with_secret() -> GenerationRequest:
    return GenerationRequest(
        messages=[ChatMessage(role="user", content="private source content")],
        template_version="decision-extraction-v1",
        input_hashes=["a" * 64],
    )


def test_fake_provider_validates_structured_output_and_persists_only_metadata(session):
    provider = FakeGenerationProvider(
        "```json\n" + json.dumps({"statement": "Use SQLite", "confidence": 0.98}) + "\n```"
    )

    _result, parsed, run = run_generation(session, provider, request_with_secret(), DecisionOutput)

    assert parsed == DecisionOutput(statement="Use SQLite", confidence=0.98)
    assert run.status == "succeeded"
    assert run.validation_status == "valid"
    persisted = session.scalar(select(ModelRun).where(ModelRun.id == run.id))
    stored_values = " ".join(
        str(getattr(persisted, column.name)) for column in ModelRun.__table__.columns
    )
    assert "private source content" not in stored_values
    assert persisted.input_hashes == ["a" * 64]


def test_invalid_structured_output_is_a_persisted_failure(session):
    provider = FakeGenerationProvider('{"statement": 42}')

    with pytest.raises(StructuredOutputError) as raised:
        run_generation(session, provider, request_with_secret(), DecisionOutput)

    run = session.get(ModelRun, raised.value.run_id)
    assert run.status == "failed"
    assert run.validation_status == "invalid"
    assert run.error_code == "structured_output_invalid"


def test_remote_provider_requires_explicit_egress_opt_in():
    with pytest.raises(ProviderConfigurationError, match="remote AI is disabled"):
        OpenAICompatibleProvider(base_url="https://models.example.com/v1", model="cheap-model")


def test_openai_compatible_adapter_normalizes_response_without_storing_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "qwen-compatible"
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"statement":"Use NATS","confidence":1}'}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:11434/v1",
        model="qwen-compatible",
        api_key="test-key",
        client=client,
    )
    request = request_with_secret().model_copy(
        update={"response_schema": DecisionOutput.model_json_schema()}
    )

    result = provider.generate(request)

    assert result.prompt_tokens == 4
    assert result.completion_tokens == 3
    assert "test-key" not in result.model_dump_json()
