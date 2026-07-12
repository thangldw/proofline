from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .embeddings import hybrid_search
from .model_gateway import (
    MAX_GENERATION_ATTEMPTS,
    REPAIRABLE_OUTPUT_CODES,
    ChatMessage,
    EmbeddingProvider,
    GenerationProvider,
    GenerationRequest,
    StructuredOutputError,
    build_repair_request,
    run_generation,
)
from .models import ModelRun, SourceVersion
from .schemas import AnswerCitation, AnswerExclusion, AnswerResponse, AnswerStatement, SearchHit

MAX_EVIDENCE_PACK_BYTES = 64 * 1024
MAX_EVIDENCE_ITEM_BYTES = 8 * 1024


class DraftStatement(BaseModel):
    text: str = Field(min_length=1)
    kind: Literal["direct", "synthesis", "inference"]
    evidence_ids: list[str] = Field(default_factory=list)


class GroundedDraft(BaseModel):
    statements: list[DraftStatement] = Field(min_length=1, max_length=32)


GroundedAnswerDraft = GroundedDraft


class EvidenceIntegrityError(RuntimeError):
    pass


class GroundingValidationError(RuntimeError):
    def __init__(self, run_id: str, reason: str) -> None:
        self.run_id = run_id
        self.reason = reason
        super().__init__(f"model run {run_id} failed grounding validation")


def validate_evidence_spans(session: Session, hits: list[SearchHit]) -> None:
    for hit in hits:
        version = session.get(SourceVersion, hit.source_version_id)
        if not version or version.source_id != hit.source_id:
            raise EvidenceIntegrityError("retrieved evidence references a missing source version")
        if version.content[hit.start_offset : hit.end_offset] != hit.content:
            raise EvidenceIntegrityError(
                "retrieved evidence does not match its immutable source span"
            )


def evidence_item(hit: SearchHit) -> dict:
    return {
        "evidence_id": hit.chunk_id,
        "source_title": hit.source_title,
        "lines": [hit.start_line, hit.end_line],
        "content": hit.content,
    }


def serialize_evidence_prompt(question: str, evidence: list[dict]) -> str:
    return json.dumps(
        {"question": question, "evidence": evidence},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def select_bounded_evidence(
    question: str, hits: list[SearchHit]
) -> tuple[list[SearchHit], list[AnswerExclusion]]:
    selected: list[SearchHit] = []
    selected_items: list[dict] = []
    exclusions: list[AnswerExclusion] = []
    for hit in hits:
        item = evidence_item(hit)
        item_size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if item_size > MAX_EVIDENCE_ITEM_BYTES:
            exclusions.append(AnswerExclusion(evidence_id=hit.chunk_id, reason="context_budget"))
            continue
        candidate_items = [*selected_items, item]
        if (
            len(serialize_evidence_prompt(question, candidate_items).encode("utf-8"))
            > MAX_EVIDENCE_PACK_BYTES
        ):
            exclusions.append(AnswerExclusion(evidence_id=hit.chunk_id, reason="context_budget"))
            continue
        selected.append(hit)
        selected_items.append(item)
    return selected, exclusions


def build_generation_request(question: str, hits: list[SearchHit]) -> GenerationRequest:
    prompt = serialize_evidence_prompt(question, [evidence_item(hit) for hit in hits])
    if len(prompt.encode("utf-8")) > MAX_EVIDENCE_PACK_BYTES:
        raise ValueError("evidence pack exceeds the hard context budget")
    return GenerationRequest(
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "Answer only from the supplied evidence. Return JSON matching the schema. "
                    "Every statement must cite one or more supplied evidence_id values. Label "
                    "any reasoning beyond direct evidence as inference."
                ),
            ),
            ChatMessage(role="user", content=prompt),
        ],
        template_version="grounded-answer-v1",
        input_hashes=[],
    )


def _fail_grounding(session: Session, run: ModelRun, reason: str) -> None:
    run.status = "failed"
    run.validation_status = "grounding_invalid"
    run.error_code = reason
    session.commit()


def answer_question(
    session: Session,
    question: str,
    provider: GenerationProvider | None,
    embedding_provider: EmbeddingProvider | None = None,
    limit: int = 8,
    max_per_source: int = 2,
    min_semantic_score: float = 0.0,
    source_ids: list[str] | None = None,
    ingested_from: datetime | None = None,
    ingested_before: datetime | None = None,
) -> AnswerResponse:
    hits = hybrid_search(
        session,
        question,
        embedding_provider,
        limit,
        max_per_source=max_per_source,
        min_semantic_score=min_semantic_score,
        source_ids=source_ids,
        ingested_from=ingested_from,
        ingested_before=ingested_before,
    )
    if not hits:
        return AnswerResponse(
            status="insufficient_evidence",
            answer="There is not enough indexed evidence to answer this question.",
            statements=[],
            citations=[],
            model_run_id=None,
        )
    validate_evidence_spans(session, hits)
    hits, exclusions = select_bounded_evidence(question, hits)
    if not hits:
        return AnswerResponse(
            status="insufficient_evidence",
            answer="Indexed evidence was excluded by the context budget.",
            statements=[],
            citations=[],
            model_run_id=None,
            exclusions=exclusions,
        )
    if provider is None:
        return AnswerResponse(
            status="provider_unavailable",
            answer="Relevant evidence was found, but no generation provider is configured.",
            statements=[],
            citations=[AnswerCitation.from_hit(hit) for hit in hits],
            model_run_id=None,
            exclusions=exclusions,
        )

    request = build_generation_request(question, hits)
    versions = {
        hit.source_version_id: session.get(SourceVersion, hit.source_version_id) for hit in hits
    }
    request = request.model_copy(
        update={
            "input_hashes": sorted(
                version.content_hash for version in versions.values() if version is not None
            )
        }
    )
    hit_by_id = {hit.chunk_id: hit for hit in hits}
    initial_request = request
    parent_run_id: str | None = None
    repair_reason: str | None = None
    for attempt_number in range(1, MAX_GENERATION_ATTEMPTS + 1):
        try:
            _result, draft, run = run_generation(
                session,
                provider,
                request,
                GroundedDraft,
                parent_run_id=parent_run_id,
                attempt_number=attempt_number,
                repair_reason=repair_reason,
            )
        except StructuredOutputError as exc:
            if (
                attempt_number >= MAX_GENERATION_ATTEMPTS
                or exc.error_code not in REPAIRABLE_OUTPUT_CODES
            ):
                raise
            parent_run_id = exc.run_id
            repair_reason = exc.error_code
            request = build_repair_request(initial_request, repair_reason)
            continue

        assert draft is not None
        cited_ids: list[str] = []
        statements: list[AnswerStatement] = []
        validation_error: str | None = None
        for statement in draft.statements:
            if not statement.evidence_ids:
                validation_error = "grounding_missing_citation"
                break
            unknown = [item for item in statement.evidence_ids if item not in hit_by_id]
            if unknown:
                validation_error = "grounding_unknown_evidence"
                break
            cited_ids.extend(statement.evidence_ids)
            statements.append(AnswerStatement(**statement.model_dump()))

        if validation_error:
            _fail_grounding(session, run, validation_error)
            if attempt_number >= MAX_GENERATION_ATTEMPTS:
                raise GroundingValidationError(run.id, validation_error)
            parent_run_id = run.id
            repair_reason = validation_error
            request = build_repair_request(initial_request, repair_reason)
            continue

        ordered_ids = list(dict.fromkeys(cited_ids))
        citations = [AnswerCitation.from_hit(hit_by_id[item]) for item in ordered_ids]
        answer = "\n\n".join(statement.text for statement in statements)
        return AnswerResponse(
            status="grounded",
            answer=answer,
            statements=statements,
            citations=citations,
            model_run_id=run.id,
            exclusions=exclusions,
        )
    raise AssertionError("bounded generation loop exited without a result")
