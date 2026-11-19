from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from . import provider_runtime
from .api import decision_to_read, get_workspace_source, resolve_workspace_id
from .config import get_settings
from .database import get_session
from .extraction import (
    CandidateExtractionError,
    extract_decision_candidates,
    extract_memory_candidates,
)
from .model_gateway import (
    ProviderConfigurationError,
    ProviderRequestError,
    StructuredOutputError,
)
from .schemas import (
    DecisionRead,
    MemoryRead,
)

router: APIRouter = APIRouter()


@router.post("/sources/{source_id}/extract-decisions", response_model=list[DecisionRead])
def extract_source_decisions(
    source_id: str,
    response: Response,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[DecisionRead]:
    source = get_workspace_source(session, source_id, workspace_id)
    try:
        provider = provider_runtime.build_generation_provider(get_settings())
        if provider is None:
            raise HTTPException(status_code=409, detail="AI provider is disabled")
        decisions, run = extract_decision_candidates(session, source, provider)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=409, detail="AI provider configuration is invalid") from exc
    except (ProviderRequestError, StructuredOutputError, CandidateExtractionError) as exc:
        run_id = getattr(exc, "run_id", None)
        headers = {"X-Proofline-Model-Run-ID": run_id} if run_id else None
        raise HTTPException(
            status_code=502,
            detail="model output could not produce grounded decision candidates",
            headers=headers,
        ) from exc
    response.headers["X-Proofline-Model-Run-ID"] = run.id
    return [decision_to_read(decision, source.title) for decision in decisions]


@router.post("/sources/{source_id}/extract-memories", response_model=list[MemoryRead])
def extract_source_memories(
    source_id: str,
    response: Response,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[MemoryRead]:
    source = get_workspace_source(session, source_id, workspace_id)
    try:
        provider = provider_runtime.build_generation_provider(get_settings())
        if provider is None:
            raise HTTPException(status_code=409, detail="AI provider is disabled")
        memories, run = extract_memory_candidates(session, source, provider)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=409, detail="AI provider configuration is invalid") from exc
    except (ProviderRequestError, StructuredOutputError, CandidateExtractionError) as exc:
        run_id = getattr(exc, "run_id", None)
        headers = {"X-Proofline-Model-Run-ID": run_id} if run_id else None
        raise HTTPException(
            status_code=502,
            detail="model output could not produce grounded memory candidates",
            headers=headers,
        ) from exc
    response.headers["X-Proofline-Model-Run-ID"] = run.id
    return [
        MemoryRead(**decision_to_read(memory, source.title).model_dump()) for memory in memories
    ]
