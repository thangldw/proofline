from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from .config import Settings
from .models import ModelRun, utc_now


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


class GenerationRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    template_version: str = Field(min_length=1, max_length=80)
    input_hashes: list[str] = Field(default_factory=list)
    response_schema: dict[str, Any] | None = None
    temperature: float = Field(default=0, ge=0, le=2)


class GenerationResult(BaseModel):
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    generation: bool = True
    structured_output: bool = True


class GenerationProvider(Protocol):
    id: str
    model: str

    def capabilities(self) -> ModelCapabilities: ...

    def health(self) -> bool: ...

    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class ProviderConfigurationError(ValueError):
    pass


class ProviderRequestError(RuntimeError):
    pass


class StructuredOutputError(RuntimeError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"model run {run_id} returned invalid structured output")


class FakeGenerationProvider:
    id = "fake"

    def __init__(self, content: str = "{}", model: str = "fake-deterministic") -> None:
        self.content = content
        self.model = model

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities()

    def health(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(content=self.content, prompt_tokens=1, completion_tokens=1)


def is_loopback_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


class OpenAICompatibleProvider:
    id = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        allow_remote: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        if not is_loopback_url(base_url) and not allow_remote:
            raise ProviderConfigurationError(
                "remote AI is disabled; set PROOFLINE_ALLOW_REMOTE_AI=true explicitly"
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=60)

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> bool:
        try:
            response = self.client.get(f"{self.base_url}/models", headers=self._headers())
            return response.is_success
        except httpx.HTTPError:
            return False

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
        }
        if request.response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "proofline_output", "schema": request.response_schema},
            }
        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            return GenerationResult(
                content=content,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderRequestError("model provider request failed") from exc


def build_generation_provider(settings: Settings) -> GenerationProvider | None:
    if settings.ai_provider == "disabled":
        return None
    if settings.ai_provider == "fake":
        return FakeGenerationProvider(model=settings.ai_model or "fake-deterministic")
    if settings.ai_provider == "openai_compatible":
        if not settings.ai_base_url or not settings.ai_model:
            raise ProviderConfigurationError(
                "PROOFLINE_AI_BASE_URL and PROOFLINE_AI_MODEL are required"
            )
        return OpenAICompatibleProvider(
            base_url=settings.ai_base_url,
            model=settings.ai_model,
            api_key=settings.ai_api_key,
            allow_remote=settings.allow_remote_ai,
        )
    raise ProviderConfigurationError(f"unsupported AI provider: {settings.ai_provider}")


OutputT = TypeVar("OutputT", bound=BaseModel)


def parse_structured_content(content: str) -> Any:
    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate[3:-3].strip()
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].lstrip()
    return json.loads(candidate)


def run_generation(
    session: Session,
    provider: GenerationProvider,
    request: GenerationRequest,
    output_type: type[OutputT] | None = None,
) -> tuple[GenerationResult, OutputT | None, ModelRun]:
    """Execute a model call while persisting metadata but never prompt content or secrets."""
    if output_type and request.response_schema is None:
        request = request.model_copy(update={"response_schema": output_type.model_json_schema()})
    run = ModelRun(
        provider_id=provider.id,
        model_id=provider.model,
        operation="generate",
        template_version=request.template_version,
        input_hashes=request.input_hashes,
        status="running",
    )
    session.add(run)
    session.commit()
    started = time.monotonic()
    try:
        result = provider.generate(request)
    except Exception as exc:
        session.rollback()
        failed = session.get(ModelRun, run.id)
        failed.status = "failed"
        failed.error_code = (
            "provider_request_failed"
            if isinstance(exc, ProviderRequestError)
            else "provider_internal_error"
        )
        failed.latency_ms = round((time.monotonic() - started) * 1000)
        failed.finished_at = utc_now()
        session.commit()
        raise

    parsed: OutputT | None = None
    validation_status = "not_requested"
    if output_type:
        try:
            parsed = output_type.model_validate(parse_structured_content(result.content))
            validation_status = "valid"
        except (json.JSONDecodeError, ValidationError, TypeError):
            invalid = session.get(ModelRun, run.id)
            invalid.status = "failed"
            invalid.validation_status = "invalid"
            invalid.error_code = "structured_output_invalid"
            invalid.latency_ms = round((time.monotonic() - started) * 1000)
            invalid.prompt_tokens = result.prompt_tokens
            invalid.completion_tokens = result.completion_tokens
            invalid.finished_at = utc_now()
            session.commit()
            raise StructuredOutputError(run.id) from None

    completed = session.get(ModelRun, run.id)
    completed.status = "succeeded"
    completed.validation_status = validation_status
    completed.latency_ms = round((time.monotonic() - started) * 1000)
    completed.prompt_tokens = result.prompt_tokens
    completed.completion_tokens = result.completion_tokens
    completed.finished_at = utc_now()
    session.commit()
    return result, parsed, completed
