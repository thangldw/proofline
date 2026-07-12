import json

import httpx
import pytest
from proofline.model_gateway import (
    MAX_STRUCTURED_OUTPUT_BYTES,
    ChatMessage,
    EmbeddingRequest,
    EmbeddingValidationError,
    FakeEmbeddingProvider,
    FakeGenerationProvider,
    GenerationRequest,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
    StructuredOutputError,
    run_embedding,
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


def test_oversized_structured_output_fails_without_persisting_content(session):
    sentinel = "PRIVATE-OVERSIZED-OUTPUT"
    provider = FakeGenerationProvider(sentinel + ("x" * MAX_STRUCTURED_OUTPUT_BYTES))

    with pytest.raises(StructuredOutputError) as raised:
        run_generation(session, provider, request_with_secret(), DecisionOutput)

    assert raised.value.error_code == "structured_output_too_large"
    run = session.get(ModelRun, raised.value.run_id)
    assert run.error_code == "structured_output_too_large"
    assert sentinel not in " ".join(
        str(getattr(run, column.name)) for column in ModelRun.__table__.columns
    )


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


def test_invalid_embedding_dimensions_fail_and_persist_diagnostics(session):
    provider = FakeEmbeddingProvider({"one": [1.0, 0.0], "two": [1.0]})

    with pytest.raises(EmbeddingValidationError) as raised:
        run_embedding(
            session,
            provider,
            EmbeddingRequest(texts=["one", "two"], input_hashes=["1", "2"]),
        )

    run = session.get(ModelRun, raised.value.run_id)
    assert run.status == "failed"
    assert run.validation_status == "invalid"
    assert run.error_code == "embedding_output_invalid"


def test_zero_norm_embedding_fails_and_persists_diagnostics(session):
    provider = FakeEmbeddingProvider({"zero": [0.0, 0.0]})

    with pytest.raises(EmbeddingValidationError) as raised:
        run_embedding(
            session,
            provider,
            EmbeddingRequest(texts=["zero"], input_hashes=["zero-hash"]),
        )

    run = session.get(ModelRun, raised.value.run_id)
    assert run.status == "failed"
    assert run.validation_status == "invalid"
    assert run.error_code == "embedding_output_invalid"


def test_openai_compatible_embedding_adapter_preserves_input_order():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        assert json.loads(request.content)["input"] == ["first", "second"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 2},
            },
        )

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="http://localhost:11434/v1",
        model="embedding-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.embed(EmbeddingRequest(texts=["first", "second"]))

    assert result.vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert result.prompt_tokens == 2
