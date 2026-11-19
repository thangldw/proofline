from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .decision_reviews import DecisionReviewError, reanchor_review
from .models import Decision, DecisionReview, Evidence, SourceVersion

OPEN_STATES = ("open", "acknowledged")


@dataclass(frozen=True)
class RebindPreview:
    review_id: str
    decision_id: str
    decision_title: str
    anchor_state: str
    cited_quote: str
    candidate_text: str | None
    candidate_start_line: int | None
    candidate_end_line: int | None
    diff: list[str]
    can_apply: bool
    blocker: str | None

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


def list_pending_reviews(session: Session) -> list[DecisionReview]:
    return list(
        session.scalars(
            select(DecisionReview)
            .where(DecisionReview.state.in_(OPEN_STATES))
            .order_by(DecisionReview.opened_at, DecisionReview.id)
        ).all()
    )


def _load(session: Session, review_id: str) -> tuple[DecisionReview, Decision, Evidence]:
    review = session.get(DecisionReview, review_id)
    if review is None:
        raise DecisionReviewError("review_not_found")
    decision = session.get(Decision, review.decision_id)
    evidence = session.get(Evidence, review.evidence_id)
    if decision is None or evidence is None:
        raise DecisionReviewError("review_provenance_invalid")
    return review, decision, evidence


def preview_rebind(session: Session, review_id: str) -> RebindPreview:
    """Show what re-anchoring would replace; read-only."""

    review, decision, evidence = _load(session, review_id)
    current = session.get(SourceVersion, review.current_source_version_id)
    if current is None:
        raise DecisionReviewError("review_provenance_invalid")
    start, end = review.candidate_start_offset, review.candidate_end_offset
    candidate = current.content[start:end] if start is not None and end is not None else None
    blocker: str | None = None
    if review.state not in OPEN_STATES:
        blocker = "review_not_actionable"
    elif review.anchor_state == "ambiguous":
        blocker = "ambiguous_candidate"
    elif candidate is None:
        blocker = "no_candidate"
    diff = (
        list(
            difflib.unified_diff(
                evidence.quote.splitlines(),
                candidate.splitlines(),
                fromfile="cited",
                tofile="current",
                lineterm="",
            )
        )
        if candidate is not None
        else []
    )
    return RebindPreview(
        review_id=review.id,
        decision_id=decision.id,
        decision_title=decision.title,
        anchor_state=review.anchor_state,
        cited_quote=evidence.quote,
        candidate_text=candidate,
        candidate_start_line=review.candidate_start_line,
        candidate_end_line=review.candidate_end_line,
        diff=diff,
        can_apply=blocker is None,
        blocker=blocker,
    )


def apply_rebind(session: Session, review_id: str, *, actor: str, reason: str) -> DecisionReview:
    """Re-anchor the decision on the proposed candidate. The caller commits."""

    preview = preview_rebind(session, review_id)
    if preview.blocker is not None:
        raise DecisionReviewError(preview.blocker)
    review = session.get(DecisionReview, review_id)
    if (
        review is None
        or review.candidate_start_offset is None
        or review.candidate_end_offset is None
    ):
        raise DecisionReviewError("no_candidate")
    return reanchor_review(
        session,
        review.id,
        workspace_id=review.workspace_id,
        expected_current_source_version_id=review.current_source_version_id,
        start_offset=review.candidate_start_offset,
        end_offset=review.candidate_end_offset,
        actor=actor,
        reason=reason,
    )
