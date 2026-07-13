from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MemoryKind = Literal["decision", "assumption", "constraint", "alternative"]
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


class WorkspaceCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=200)


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    title: str
    created_at: datetime


def normalize_retrieval_filters(
    source_ids: list[str] | None,
    ingested_from: datetime | None,
    ingested_before: datetime | None,
) -> tuple[list[str] | None, datetime | None, datetime | None]:
    normalized_ids = list(dict.fromkeys(source_ids)) if source_ids is not None else None
    if normalized_ids is not None and len(normalized_ids) > 100:
        raise ValueError("source_ids must contain at most 100 unique values")
    for name, value in (
        ("ingested_from", ingested_from),
        ("ingested_before", ingested_before),
    ):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError(f"{name} must include a timezone offset")
    normalized_from = ingested_from.astimezone(UTC) if ingested_from is not None else None
    normalized_before = ingested_before.astimezone(UTC) if ingested_before is not None else None
    if (
        normalized_from is not None
        and normalized_before is not None
        and normalized_from >= normalized_before
    ):
        raise ValueError("ingested_from must be earlier than ingested_before")
    return normalized_ids, normalized_from, normalized_before


class SourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=5_000_000)
    kind: str = Field(default="markdown", pattern="^(markdown|text|note)$")
    uri: str | None = Field(default=None, max_length=4_096)
    workspace_id: str = Field(default=DEFAULT_WORKSPACE_ID, min_length=36, max_length=36)


class FolderScanRequest(BaseModel):
    root: str | None = Field(default=None, min_length=1, max_length=4_096)
    path: str | None = Field(default=None, max_length=4_096)
    delete_missing: bool = False
    confirmed_missing_source_ids: list[str] | None = Field(default=None, max_length=10_000)
    workspace_id: str = Field(default=DEFAULT_WORKSPACE_ID, min_length=36, max_length=36)


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
    deletion_mode: Literal["preview_only", "confirmed_delete"] = "preview_only"
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


class FolderWatchStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    running: bool
    scan_in_progress: bool
    interval_seconds: int = Field(ge=0, le=3600)
    registered_root_count: int = Field(ge=0)
    completed_cycles: int = Field(ge=0)
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_error_code: str | None
    last_root_error_count: int = Field(ge=0)
    last_discovered_count: int = Field(ge=0)
    last_created_count: int = Field(ge=0)
    last_updated_count: int = Field(ge=0)
    last_unchanged_count: int = Field(ge=0)
    last_renamed_count: int = Field(ge=0)
    last_failed_count: int = Field(ge=0)
    last_missing_count: int = Field(ge=0)


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
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
    git_repository_id: str | None = None
    git_commit_sha: str | None = None
    git_path: str | None = None


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=5_000_000)


class NoteUpdate(NoteCreate):
    pass


class NoteTagRead(BaseModel):
    name: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int


class NoteLinkRead(BaseModel):
    target_title: str
    quote: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    resolved_source_id: str | None = None


class NoteRead(BaseModel):
    id: str
    workspace_id: str
    title: str
    content: str
    uri: str
    current_version_id: str
    version_count: int
    created_at: datetime
    indexed_at: datetime
    tags: list[NoteTagRead]
    links: list[NoteLinkRead]


class NoteBacklinkRead(NoteLinkRead):
    source_id: str
    source_version_id: str
    source_title: str


class GitRepositoryCreate(BaseModel):
    path: str = Field(min_length=1, max_length=4_096)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    revision: str = Field(default="HEAD", min_length=1, max_length=200)
    workspace_id: str = Field(default=DEFAULT_WORKSPACE_ID, min_length=36, max_length=36)


class GitRepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    title: str
    path: str
    current_commit_sha: str | None
    status: str
    created_at: datetime
    indexed_at: datetime
    source_count: int = 0
    file_count: int = 0
    commit_count: int = 0


class GitRepositoryImportResponse(BaseModel):
    repository: GitRepositoryRead
    commit_sha: str
    created_count: int
    unchanged_count: int
    failed_count: int
    failures: list[dict[str, str]] = []


class SourceDeletionImpactRead(BaseModel):
    source_id: str
    title: str
    current_version_id: str | None
    versions: int = Field(ge=0)
    chunks: int = Field(ge=0)
    embeddings: int = Field(ge=0)
    vector_index_rows: int = Field(ge=0)
    decisions: int = Field(ge=0)
    memories: int = Field(ge=0)
    evidence: int = Field(ge=0)
    decision_relations: int = Field(ge=0)
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
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def validate_validity(self) -> DecisionUpdate:
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be earlier than valid_to")
        return self


class MemoryRead(DecisionRead):
    pass


class MemoryUpdate(DecisionUpdate):
    pass


DecisionRelationKind = Literal["supersedes", "implements", "contradicts", "based_on", "considered"]


class DecisionRelationCreate(BaseModel):
    source_decision_id: str
    target_decision_id: str
    kind: DecisionRelationKind
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def validate_relation(self) -> DecisionRelationCreate:
        if self.source_decision_id == self.target_decision_id:
            raise ValueError("a decision cannot relate to itself")
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be earlier than valid_to")
        return self


class DecisionRelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_decision_id: str
    target_decision_id: str
    kind: DecisionRelationKind
    valid_from: datetime | None
    valid_to: datetime | None
    created_by: str
    created_at: datetime


class DecisionTimelineRead(BaseModel):
    decision: DecisionRead
    incoming: list[DecisionRelationRead]
    outgoing: list[DecisionRelationRead]


class DecisionRelationCandidateRead(BaseModel):
    kind: Literal["contradiction", "stale"]
    decision_ids: list[str]
    relation_id: str | None = None
    reason: str


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
    source_kind: str | None = None
    git_commit_sha: str | None = None
    git_path: str | None = None
    temporal_priority: Literal["current_decision", "neutral"] = "neutral"
    rerank_rank: int | None = None
    rerank_score: float | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class AnswerRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2_000)
    limit: int = Field(default=8, ge=1, le=12)
    max_per_source: int = Field(default=2, ge=1, le=12)
    source_ids: list[str] | None = Field(default=None, max_length=100)
    ingested_from: datetime | None = None
    ingested_before: datetime | None = None
    min_semantic_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    rerank: bool = False

    @model_validator(mode="after")
    def normalize_filters(self) -> AnswerRequest:
        self.source_ids, self.ingested_from, self.ingested_before = normalize_retrieval_filters(
            self.source_ids,
            self.ingested_from,
            self.ingested_before,
        )
        return self


class AnswerStatement(BaseModel):
    text: str
    kind: Literal["direct", "synthesis", "inference"]
    evidence_ids: list[str]
    support_status: Literal["supported", "uncertain", "contradicted"] = "supported"


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
    source_kind: str | None = None
    git_commit_sha: str | None = None
    git_path: str | None = None

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
            source_kind=hit.source_kind,
            git_commit_sha=hit.git_commit_sha,
            git_path=hit.git_path,
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
    workspace_id: str
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
    workspace_id: str
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
    embedding: bool = False
    reranking: bool = False
    remote_egress_allowed: bool = False
    healthy: bool | None = None
    error_code: str | None = None
    mode: Literal["ready", "degraded", "disabled", "unchecked"] = "unchecked"


class ProviderConfigurationUpdate(BaseModel):
    ai_provider: Literal["disabled", "qwen", "deepseek", "ollama", "vllm", "openai_compatible"]
    ai_base_url: str | None = Field(default=None, max_length=2_000)
    ai_model: str | None = Field(default=None, max_length=300)
    ai_api_key: str | None = Field(default=None, max_length=2_000)
    embedding_provider: Literal["disabled", "ollama", "vllm", "openai_compatible"]
    embedding_base_url: str | None = Field(default=None, max_length=2_000)
    embedding_model: str | None = Field(default=None, max_length=300)
    embedding_api_key: str | None = Field(default=None, max_length=2_000)
    allow_remote_ai: bool = False


class ProviderConfigurationRead(BaseModel):
    ai_provider: str
    ai_base_url: str | None
    ai_model: str | None
    ai_api_key_configured: bool
    embedding_provider: str
    embedding_base_url: str | None
    embedding_model: str | None
    embedding_api_key_configured: bool
    allow_remote_ai: bool


class EmbeddingIndexResponse(BaseModel):
    indexed: int
    skipped: int
    model_run_ids: list[str]


class ModelRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
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


class ModelRunRetryRequest(BaseModel):
    source_id: str
    operation: Literal["extract_memories"] = "extract_memories"


class ModelRunRetryResponse(BaseModel):
    parent_run_id: str
    model_run_id: str
    status: str
    memory_count: int
