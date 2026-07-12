from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .model_gateway import (
    ChatMessage,
    GenerationProvider,
    GenerationRequest,
    run_generation,
)
from .models import ModelRun, SourceVersion
from .retrieval import lexical_search
from .schemas import AnswerCitation, AnswerResponse, AnswerStatement, SearchHit


class DraftStatement(BaseModel):
    text: str = Field(min_length=1)
    kind: Literal["direct", "synthesis", "inference"]
    evidence_ids: list[str] = Field(default_factory=list)


class GroundedDraft(BaseModel):
    statements: list[DraftStatement] = Field(min_length=1)


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


def build_generation_request(question: str, hits: list[SearchHit]) -> GenerationRequest:
    evidence = [
        {
            "evidence_id": hit.chunk_id,
            "source_title": hit.source_title,
            "lines": [hit.start_line, hit.end_line],
            "content": hit.content,
        }
        for hit in hits
    ]
    prompt = json.dumps(
        {"question": question, "evidence": evidence}, ensure_ascii=False, separators=(",", ":")
    )
    return GenerationRequest(
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "Answer only from the supplied evidence. Return JSON matching the schema. "
                    "Every direct or synthesis statement must cite one or more supplied "
                    "evidence_id values. Label any reasoning beyond direct evidence as inference."
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
    limit: int = 8,
) -> AnswerResponse:
    hits = lexical_search(session, question, limit)
    if not hits:
        return AnswerResponse(
            status="insufficient_evidence",
            answer="There is not enough indexed evidence to answer this question.",
            statements=[],
            citations=[],
            model_run_id=None,
        )
    validate_evidence_spans(session, hits)
    if provider is None:
        return AnswerResponse(
            status="provider_unavailable",
            answer="Relevant evidence was found, but no generation provider is configured.",
            statements=[],
            citations=[AnswerCitation.from_hit(hit) for hit in hits],
            model_run_id=None,
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
    _result, draft, run = run_generation(session, provider, request, GroundedDraft)
    assert draft is not None
    hit_by_id = {hit.chunk_id: hit for hit in hits}
    cited_ids: list[str] = []
    statements: list[AnswerStatement] = []
    for statement in draft.statements:
        if statement.kind in {"direct", "synthesis"} and not statement.evidence_ids:
            _fail_grounding(session, run, "grounding_missing_citation")
            raise GroundingValidationError(run.id, "grounding_missing_citation")
        unknown = [item for item in statement.evidence_ids if item not in hit_by_id]
        if unknown:
            _fail_grounding(session, run, "grounding_unknown_evidence")
            raise GroundingValidationError(run.id, "grounding_unknown_evidence")
        cited_ids.extend(statement.evidence_ids)
        statements.append(AnswerStatement(**statement.model_dump()))

    ordered_ids = list(dict.fromkeys(cited_ids))
    citations = [AnswerCitation.from_hit(hit_by_id[item]) for item in ordered_ids]
    answer = "\n\n".join(statement.text for statement in statements)
    return AnswerResponse(
        status="grounded",
        answer=answer,
        statements=statements,
        citations=citations,
        model_run_id=run.id,
    )
