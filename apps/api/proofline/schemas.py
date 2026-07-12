from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryKind = Literal["decision", "assumption", "constraint", "alternative"]


class SourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=5_000_000)
    kind: str = Field(default="markdown", pattern="^(markdown|text)$")
    uri: str | None = None


class FolderScanRequest(BaseModel):
    root: str | None = Field(default=None, min_length=1, max_length=4_096)
    path: str | None = Field(default=None, max_length=4_096)
    delete_missing: bool = False


class FolderScanFileResult(BaseModel):
    relative_path: str
    uri: str | None = None
    previous_uri: str | None = None
    status: Literal["created", "updated", "unchanged", "renamed", "failed"]
    source_id: str | None = None
    source_version_id: str | None = None
    job_id: str | None = None
    error_code: str | None = None


class FolderScanResponse(BaseModel):
    root: str
    path: str
    delete_missing_requested: bool
    deletion_mode: Literal["preview_only"] = "preview_only"
    deleted_count: int = 0
    discovered_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    renamed_count: int
    failed_count: int
    missing_count: int
    missing_source_ids: list[str]
    files: list[FolderScanFileResult]


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
    memory_count: int = 0


class SourceDeletionImpactRead(BaseModel):
    source_id: str
    title: str
    current_version_id: str | None
    versions: int = Field(ge=0)
    chunks: int = Field(ge=0)
    embeddings: int = Field(ge=0)
    decisions: int = Field(ge=0)
    memories: int = Field(ge=0)
    evidence: int = Field(ge=0)
    ingestion_jobs_to_detach: int = Field(ge=0)
    audit_events_to_delete: int = Field(ge=0)
    fts_rows: int = Field(ge=0)


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
    kind: MemoryKind
    title: str
    statement: str
    rationale: str | None
    status: str
    confidence: float
    extraction_method: str
    model_run_id: str | None
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


class MemoryRead(DecisionRead):
    pass


class MemoryUpdate(DecisionUpdate):
    pass


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
    max_per_source: int = Field(default=2, ge=1, le=12)
    min_semantic_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )


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


class AnswerExclusion(BaseModel):
    evidence_id: str
    reason: Literal["context_budget"]


class AnswerResponse(BaseModel):
    status: Literal["grounded", "insufficient_evidence", "provider_unavailable"]
    answer: str
    statements: list[AnswerStatement]
    citations: list[AnswerCitation]
    model_run_id: str | None
    exclusions: list[AnswerExclusion] = Field(default_factory=list)


class Overview(BaseModel):
    sources: int
    chunks: int
    decisions: int
    memories: int
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
    request_hash: str | None
    max_attempts: int
    error_code: str | None
    error_detail: str | None
    retryable: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


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
    parent_run_id: str | None
    attempt_number: int
    repair_reason: str | None
    status: str
    validation_status: str | None
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
