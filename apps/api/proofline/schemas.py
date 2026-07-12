from __future__ import annotations

from datetime import datetime

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
    evidence: list[EvidenceRead] = []


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


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


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
