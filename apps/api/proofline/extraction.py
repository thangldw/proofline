from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .model_gateway import (
    ChatMessage,
    GenerationProvider,
    GenerationRequest,
    run_generation,
)
from .models import Chunk, Decision, Evidence, ModelRun, Source, SourceVersion


class DecisionCandidateDraft(BaseModel):
    statement: str = Field(min_length=1, max_length=4_000)
    rationale: str | None = Field(default=None, max_length=8_000)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1)


class DecisionCandidateBatch(BaseModel):
    candidates: list[DecisionCandidateDraft]


class CandidateExtractionError(RuntimeError):
    def __init__(self, run_id: str, error_code: str) -> None:
        self.run_id = run_id
        self.error_code = error_code
        super().__init__(f"candidate extraction run {run_id} failed validation")


def _mark_failed(session: Session, run: ModelRun, code: str) -> None:
    run.status = "failed"
    run.validation_status = "grounding_invalid"
    run.error_code = code
    session.commit()


def extract_decision_candidates(
    session: Session,
    source: Source,
    provider: GenerationProvider,
) -> tuple[list[Decision], ModelRun]:
    if not source.current_version_id:
        raise ValueError("source has no current version")
    version = session.get(SourceVersion, source.current_version_id)
    chunks = list(
        session.scalars(
            select(Chunk)
            .where(Chunk.source_version_id == source.current_version_id)
            .order_by(Chunk.ordinal)
        ).all()
    )
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    prompt = json.dumps(
        {
            "source_title": source.title,
            "evidence": [{"evidence_id": chunk.id, "content": chunk.content} for chunk in chunks],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    request = GenerationRequest(
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "Extract explicit engineering decisions only. Return candidates matching "
                    "the schema. Every candidate must cite supplied evidence_id values. "
                    "Do not invent rationale or mark candidates accepted."
                ),
            ),
            ChatMessage(role="user", content=prompt),
        ],
        template_version="decision-candidate-extraction-v1",
        input_hashes=[version.content_hash],
    )
    _result, batch, run = run_generation(session, provider, request, DecisionCandidateBatch)
    assert batch is not None

    for candidate in batch.candidates:
        unknown = [item for item in candidate.evidence_ids if item not in chunk_by_id]
        if unknown:
            _mark_failed(session, run, "candidate_unknown_evidence")
            raise CandidateExtractionError(run.id, "candidate_unknown_evidence")

    decisions: list[Decision] = []
    for candidate in batch.candidates:
        existing = session.scalar(
            select(Decision).where(
                Decision.source_version_id == version.id,
                Decision.statement == candidate.statement,
                Decision.extraction_method == "model",
            )
        )
        if existing:
            decisions.append(existing)
            continue
        decision = Decision(
            source_id=source.id,
            source_version_id=version.id,
            title=candidate.statement[:300],
            statement=candidate.statement,
            rationale=candidate.rationale,
            status="candidate",
            confidence=candidate.confidence,
            extraction_method="model",
            model_run_id=run.id,
        )
        session.add(decision)
        session.flush()
        for evidence_id in dict.fromkeys(candidate.evidence_ids):
            chunk = chunk_by_id[evidence_id]
            session.add(
                Evidence(
                    decision_id=decision.id,
                    source_id=source.id,
                    source_version_id=version.id,
                    quote=chunk.content,
                    quote_hash=hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                )
            )
        decisions.append(decision)
    session.commit()
    for decision in decisions:
        session.refresh(decision)
    return decisions, run
