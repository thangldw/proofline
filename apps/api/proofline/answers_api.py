from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from . import provider_runtime
from .api import resolve_workspace_id
from .config import get_settings
from .database import get_session
from .embeddings import hybrid_search
from .grounding import EvidenceIntegrityError, GroundingValidationError, answer_question
from .model_gateway import (
    EmbeddingValidationError,
    ProviderConfigurationError,
    ProviderRequestError,
    StructuredOutputError,
    build_embedding_provider,
)
from .reranking import DeterministicTokenReranker
from .schemas import (
    AnswerRequest,
    AnswerResponse,
    SearchResponse,
    normalize_retrieval_filters,
)

router: APIRouter = APIRouter()


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    max_per_source: int = Query(default=2, ge=1, le=50),
    min_semantic_score: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    ),
    hybrid: bool = True,
    rerank: bool = False,
    source_ids: list[str] | None = Query(default=None, alias="source_id"),
    ingested_from: datetime | None = Query(default=None),
    ingested_before: datetime | None = Query(default=None),
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> SearchResponse:
    try:
        source_ids, ingested_from, ingested_before = normalize_retrieval_filters(
            source_ids, ingested_from, ingested_before
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        embedding_provider = build_embedding_provider(get_settings()) if hybrid else None
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=409, detail="Embedding provider configuration is invalid"
        ) from exc
    try:
        hits = hybrid_search(
            session,
            q,
            embedding_provider,
            limit,
            max_per_source=max_per_source,
            min_semantic_score=min_semantic_score,
            source_ids=source_ids,
            ingested_from=ingested_from,
            ingested_before=ingested_before,
            reranker=DeterministicTokenReranker() if rerank else None,
            workspace_id=workspace_id,
        )
    except (ProviderRequestError, EmbeddingValidationError) as exc:
        raise HTTPException(status_code=502, detail="Embedding provider request failed") from exc
    return SearchResponse(query=q, hits=hits)


@router.post("/answers", response_model=AnswerResponse)
def create_answer(
    payload: AnswerRequest,
    response: Response,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> AnswerResponse:
    try:
        settings = get_settings()
        provider = provider_runtime.build_generation_provider(settings)
        embedding_provider = build_embedding_provider(settings)
        answer = answer_question(
            session,
            payload.question,
            provider,
            embedding_provider,
            payload.limit,
            payload.max_per_source,
            payload.min_semantic_score,
            payload.source_ids,
            payload.ingested_from,
            payload.ingested_before,
            reranker=DeterministicTokenReranker() if payload.rerank else None,
            workspace_id=workspace_id,
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=409, detail="AI provider configuration is invalid") from exc
    except (
        ProviderRequestError,
        EmbeddingValidationError,
        StructuredOutputError,
        GroundingValidationError,
    ) as exc:
        run_id = getattr(exc, "run_id", None)
        headers = {"X-Proofline-Model-Run-ID": run_id} if run_id else None
        raise HTTPException(
            status_code=502,
            detail="model output could not produce a grounded answer",
            headers=headers,
        ) from exc
    except EvidenceIntegrityError as exc:
        raise HTTPException(status_code=500, detail="evidence integrity validation failed") from exc
    if answer.model_run_id:
        response.headers["X-Proofline-Model-Run-ID"] = answer.model_run_id
    return answer
