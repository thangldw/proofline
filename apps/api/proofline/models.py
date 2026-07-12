from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="markdown")
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="indexed")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    indexed_at: Mapped[datetime] = mapped_column(default=utc_now)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    versions: Mapped[list[SourceVersion]] = relationship(
        cascade="all, delete-orphan", foreign_keys="SourceVersion.source_id"
    )
    chunks: Mapped[list[Chunk]] = relationship(cascade="all, delete-orphan")
    decisions: Mapped[list[Decision]] = relationship(cascade="all, delete-orphan")


class SourceVersion(Base):
    __tablename__ = "source_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    version_number: Mapped[int] = mapped_column(Integer)
    content_length: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="indexed")
    parser_version: Mapped[str] = mapped_column(String(30), default="deterministic-v1")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    statement: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    extraction_method: Mapped[str] = mapped_column(String(40), default="deterministic")
    model_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    valid_from: Mapped[datetime | None] = mapped_column(nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)

    evidence: Mapped[list[Evidence]] = relationship(cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), index=True
    )
    quote: Mapped[str] = mapped_column(Text)
    quote_hash: Mapped[str] = mapped_column(String(64))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default="source_ingestion")
    state: Mapped[str] = mapped_column(String(30), default="running", index=True)
    stage: Mapped[str] = mapped_column(String(30), default="accepted")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retryable: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(100), default="local_user")
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str] = mapped_column(String(50), index=True)
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    before_json: Mapped[dict] = mapped_column(JSON)
    after_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(String(100))
    model_id: Mapped[str] = mapped_column(String(200))
    operation: Mapped[str] = mapped_column(String(50))
    template_version: Mapped[str] = mapped_column(String(80))
    input_hashes: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), index=True)
    validation_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_versions.id", ondelete="CASCADE"), index=True
    )
    provider_id: Mapped[str] = mapped_column(String(100))
    model_id: Mapped[str] = mapped_column(String(200))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector_json: Mapped[list[float]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
