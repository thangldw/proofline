from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import provider_runtime
from .api import resolve_workspace_id
from .config import get_settings
from .database import get_session
from .grounding import EvidenceIntegrityError, GroundingValidationError, answer_question
from .model_gateway import (
    EmbeddingValidationError,
    ProviderConfigurationError,
    ProviderRequestError,
    StructuredOutputError,
    build_embedding_provider,
)
from .models import (
    ActionProposal,
    AuditEvent,
    ProposalCitation,
    utc_now,
)
from .reranking import DeterministicTokenReranker
from .schemas import (
    ActionProposalCreate,
    ActionProposalRead,
    ActionProposalReview,
)

router: APIRouter = APIRouter()


@router.post(
    "/action-proposals", response_model=ActionProposalRead, status_code=status.HTTP_201_CREATED
)
def create_action_proposal(
    payload: ActionProposalCreate,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> ActionProposal:
    try:
        settings = get_settings()
        answer = answer_question(
            session,
            payload.question,
            provider_runtime.build_generation_provider(settings),
            build_embedding_provider(settings),
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
        raise HTTPException(status_code=502, detail="grounded proposal generation failed") from exc
    except EvidenceIntegrityError as exc:
        raise HTTPException(status_code=500, detail="evidence integrity validation failed") from exc
    if answer.status != "grounded" or answer.model_run_id is None:
        raise HTTPException(
            status_code=422 if answer.status == "insufficient_evidence" else 409,
            detail=(
                "Insufficient evidence for an action proposal"
                if answer.status == "insufficient_evidence"
                else "A generation provider is required for action proposals"
            ),
        )
    proposal = ActionProposal(
        workspace_id=workspace_id,
        goal=payload.question,
        body=answer.answer,
        status="candidate",
        model_run_id=answer.model_run_id,
    )
    for citation in answer.citations:
        proposal.citations.append(
            ProposalCitation(
                source_id=citation.source_id,
                source_version_id=citation.source_version_id,
                chunk_id=citation.evidence_id,
                source_title=citation.source_title,
                quote=citation.content,
                quote_hash=hashlib.sha256(citation.content.encode("utf-8")).hexdigest(),
                start_offset=citation.start_offset,
                end_offset=citation.end_offset,
                start_line=citation.start_line,
                end_line=citation.end_line,
            )
        )
    session.add(proposal)
    session.flush()
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor="model",
            action="action_proposal.created",
            object_type="action_proposal",
            object_id=proposal.id,
            before_json={},
            after_json={"status": "candidate", "model_run_id": proposal.model_run_id},
        )
    )
    session.commit()
    session.refresh(proposal)
    return proposal


@router.get("/action-proposals", response_model=list[ActionProposalRead])
def list_action_proposals(
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> list[ActionProposal]:
    return list(
        session.scalars(
            select(ActionProposal)
            .where(ActionProposal.workspace_id == workspace_id)
            .options(selectinload(ActionProposal.citations))
            .order_by(ActionProposal.created_at.desc())
        ).all()
    )


@router.patch("/action-proposals/{proposal_id}", response_model=ActionProposalRead)
def review_action_proposal(
    proposal_id: str,
    payload: ActionProposalReview,
    workspace_id: str = Depends(resolve_workspace_id),
    session: Session = Depends(get_session),
) -> ActionProposal:
    proposal = session.scalar(
        select(ActionProposal)
        .where(ActionProposal.id == proposal_id, ActionProposal.workspace_id == workspace_id)
        .options(selectinload(ActionProposal.citations))
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Action proposal not found")
    if proposal.status != "candidate":
        raise HTTPException(status_code=409, detail="Action proposal was already reviewed")
    before = proposal.status
    proposal.status = payload.status
    proposal.updated_at = utc_now()
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor="local_user",
            action="action_proposal.reviewed",
            object_type="action_proposal",
            object_id=proposal.id,
            before_json={"status": before},
            after_json={"status": proposal.status},
        )
    )
    session.commit()
    session.refresh(proposal)
    return proposal
