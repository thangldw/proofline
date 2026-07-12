from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=5_000_000)
    kind: str = Field(default="markdown", pattern="^(markdown|text)$")
    uri: str | None = None


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    kind: str
    uri: str | None
    status: str
    created_at: datetime
    indexed_at: datetime
    current_version_id: str | None
    version_count: int = 0
    chunk_count: int = 0
    decision_count: int = 0


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    source_version_id: str
    quote: str
    quote_hash: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    source_version_id: str
    source_title: str | None = None
    title: str
    statement: str
    rationale: str | None
    status: str
    confidence: float
    extraction_method: str
    valid_from: datetime | None
    valid_to: datetime | None
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceRead] = []


class DecisionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    statement: str | None = Field(default=None, min_length=1)
    rationale: str | None = None
    status: Literal["candidate", "active", "accepted", "rejected", "obsolete"] | None = None


class SearchHit(BaseModel):
    chunk_id: str
    source_id: str
    source_version_id: str
    source_title: str
    content: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    rank: float
    retrieval_channels: list[str] = Field(default_factory=lambda: ["lexical"])
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    semantic_score: float | None = None
    fused_score: float | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class AnswerRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2_000)
    limit: int = Field(default=8, ge=1, le=12)


class AnswerStatement(BaseModel):
    text: str
    kind: Literal["direct", "synthesis", "inference"]
    evidence_ids: list[str]


class AnswerCitation(BaseModel):
    evidence_id: str
    source_id: str
    source_version_id: str
    source_title: str
    content: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int

    @classmethod
    def from_hit(cls, hit: SearchHit) -> AnswerCitation:
        return cls(
            evidence_id=hit.chunk_id,
            source_id=hit.source_id,
            source_version_id=hit.source_version_id,
            source_title=hit.source_title,
            content=hit.content,
            start_offset=hit.start_offset,
            end_offset=hit.end_offset,
            start_line=hit.start_line,
            end_line=hit.end_line,
        )


class AnswerResponse(BaseModel):
    status: Literal["grounded", "insufficient_evidence", "provider_unavailable"]
    answer: str
    statements: list[AnswerStatement]
    citations: list[AnswerCitation]
    model_run_id: str | None


class Overview(BaseModel):
    sources: int
    chunks: int
    decisions: int
    evidence: int


class SourceVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    content_hash: str
    version_number: int
    content_length: int
    status: str
    parser_version: str
    created_at: datetime


class SourceVersionContentRead(SourceVersionRead):
    content: str


class IngestionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str | None
    source_version_id: str | None
    kind: str
    state: str
    stage: str
    attempts: int
    error_code: str | None
    error_detail: str | None
    retryable: bool
    created_at: datetime
    updated_at: datetime


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor: str
    action: str
    object_type: str
    object_id: str
    before_json: dict
    after_json: dict
    created_at: datetime


class ProviderStatus(BaseModel):
    configured: bool
    provider_id: str | None = None
    model_id: str | None = None
    generation: bool = False
    structured_output: bool = False
    remote_egress_allowed: bool = False
    healthy: bool | None = None
    error_code: str | None = None


class EmbeddingIndexResponse(BaseModel):
    indexed: int
    skipped: int
    model_run_ids: list[str]


class ModelRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str
    model_id: str
    operation: str
    template_version: str
    input_hashes: list[str]
    status: str
    validation_status: str | None
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
