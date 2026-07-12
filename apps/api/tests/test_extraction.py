import json

import pytest
from proofline.extraction import CandidateExtractionError, extract_decision_candidates
from proofline.ingestion import ingest_source
from proofline.model_gateway import FakeGenerationProvider
from proofline.models import Chunk, Decision, ModelRun
from proofline.schemas import SourceCreate
from sqlalchemy import func, select


def source_and_chunk(session):
    content = (
        "# Architecture\n\nThe team selected SQLite for local metadata to avoid another service."
    )
    source, _ = ingest_source(
        session,
        SourceCreate(title="Architecture note", uri="file:///architecture.md", content=content),
    )
    chunk = session.scalar(
        select(Chunk).where(Chunk.source_version_id == source.current_version_id)
    )
    return source, chunk, content


def candidate_response(evidence_id: str) -> str:
    return json.dumps(
        {
            "candidates": [
                {
                    "statement": "Use SQLite for local metadata",
                    "rationale": "Avoid operating another service",
                    "confidence": 0.91,
                    "evidence_ids": [evidence_id],
                }
            ]
        }
    )


def test_model_candidates_are_unaccepted_and_exactly_grounded(session):
    source, chunk, content = source_and_chunk(session)
    provider = FakeGenerationProvider(candidate_response(chunk.id))

    decisions, run = extract_decision_candidates(session, source, provider)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == "candidate"
    assert decision.extraction_method == "model"
    assert decision.model_run_id == run.id
    assert decision.evidence[0].source_version_id == source.current_version_id
    assert (
        content[decision.evidence[0].start_offset : decision.evidence[0].end_offset]
        == decision.evidence[0].quote
    )
    persisted_run = session.get(ModelRun, run.id)
    assert persisted_run.input_hashes == [source.versions[0].content_hash]


def test_unknown_candidate_evidence_fails_before_persisting_memory(session):
    source, _chunk, _content = source_and_chunk(session)
    provider = FakeGenerationProvider(candidate_response("invented-id"))

    with pytest.raises(CandidateExtractionError) as raised:
        extract_decision_candidates(session, source, provider)

    assert session.scalar(select(func.count()).select_from(Decision)) == 0
    run = session.get(ModelRun, raised.value.run_id)
    assert run.status == "failed"
    assert run.error_code == "candidate_unknown_evidence"


def test_repeated_candidate_extraction_is_idempotent_per_source_version(session):
    source, chunk, _content = source_and_chunk(session)
    provider = FakeGenerationProvider(candidate_response(chunk.id))

    first, _ = extract_decision_candidates(session, source, provider)
    second, _ = extract_decision_candidates(session, source, provider)

    assert first[0].id == second[0].id
    assert session.scalar(select(func.count()).select_from(Decision)) == 1
