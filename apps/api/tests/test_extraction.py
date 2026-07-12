import json

import pytest
from proofline.extraction import (
    CandidateExtractionError,
    extract_decision_candidates,
    extract_memory_candidates,
)
from proofline.ingestion import ingest_source
from proofline.model_gateway import FakeGenerationProvider, GenerationResult, StructuredOutputError
from proofline.models import Chunk, Decision, ModelRun
from proofline.schemas import SourceCreate
from sqlalchemy import func, select


class ScriptedGenerationProvider:
    id = "scripted"
    model = "scripted-memory-repair-test"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return GenerationResult(content=self.outcomes.pop(0))


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
                    "kind": "decision",
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


def test_model_memory_candidates_are_kind_scoped_and_candidate_only(session):
    source, chunk, _content = source_and_chunk(session)
    response = json.dumps(
        {
            "candidates": [
                {
                    "kind": "decision",
                    "statement": "SQLite remains local",
                    "rationale": None,
                    "confidence": 0.9,
                    "evidence_ids": [chunk.id],
                },
                {
                    "kind": "assumption",
                    "statement": "SQLite remains local",
                    "rationale": None,
                    "confidence": 0.8,
                    "evidence_ids": [chunk.id],
                },
            ]
        }
    )
    provider = FakeGenerationProvider(response)

    first, run = extract_memory_candidates(session, source, provider)
    second, _second_run = extract_memory_candidates(session, source, provider)

    assert {memory.kind for memory in first} == {"decision", "assumption"}
    assert all(memory.status == "candidate" for memory in first)
    assert all(memory.model_run_id == run.id for memory in first)
    assert {memory.id for memory in first} == {memory.id for memory in second}
    assert session.scalar(select(func.count()).select_from(Decision)) == 2


def test_invalid_model_memory_kind_is_rejected_before_persistence(session):
    source, chunk, _content = source_and_chunk(session)
    provider = FakeGenerationProvider(
        json.dumps(
            {
                "candidates": [
                    {
                        "kind": "incident",
                        "statement": "Unsupported kind",
                        "confidence": 0.7,
                        "evidence_ids": [chunk.id],
                    }
                ]
            }
        )
    )

    with pytest.raises(StructuredOutputError) as raised:
        extract_memory_candidates(session, source, provider)

    assert session.scalar(select(func.count()).select_from(Decision)) == 0
    run = session.get(ModelRun, raised.value.run_id)
    assert run.status == "failed"
    assert run.error_code == "structured_output_invalid"


def test_legacy_decision_extraction_rejects_mixed_kinds_before_persistence(session):
    source, chunk, _content = source_and_chunk(session)
    provider = FakeGenerationProvider(
        json.dumps(
            {
                "candidates": [
                    {
                        "kind": "decision",
                        "statement": "Use SQLite locally",
                        "confidence": 0.9,
                        "evidence_ids": [chunk.id],
                    },
                    {
                        "kind": "assumption",
                        "statement": "There is one writer",
                        "confidence": 0.8,
                        "evidence_ids": [chunk.id],
                    },
                ]
            }
        )
    )

    with pytest.raises(CandidateExtractionError) as raised:
        extract_decision_candidates(session, source, provider)

    assert raised.value.error_code == "candidate_kind_not_allowed"
    assert session.scalar(select(func.count()).select_from(Decision)) == 0
    run = session.get(ModelRun, raised.value.run_id)
    assert run.status == "failed"
    assert run.validation_status == "grounding_invalid"
    assert run.error_code == "candidate_kind_not_allowed"


def test_unknown_candidate_evidence_is_repaired_before_persistence(session):
    source, chunk, content = source_and_chunk(session)
    provider = ScriptedGenerationProvider(
        [candidate_response("invented-id"), candidate_response(chunk.id)]
    )

    memories, run = extract_memory_candidates(session, source, provider)

    assert len(provider.requests) == 2
    assert len(memories) == 1
    assert memories[0].model_run_id == run.id
    assert (
        content[memories[0].evidence[0].start_offset : memories[0].evidence[0].end_offset]
        == memories[0].evidence[0].quote
    )
    runs = list(session.scalars(select(ModelRun).order_by(ModelRun.attempt_number)).all())
    assert runs[0].status == "failed"
    assert runs[0].error_code == "candidate_unknown_evidence"
    assert runs[1].parent_run_id == runs[0].id
    assert runs[1].attempt_number == 2
    assert runs[1].repair_reason == "candidate_unknown_evidence"
    assert memories[0].status == "candidate"


def test_candidate_batch_is_bounded_to_64_items(session):
    source, chunk, _content = source_and_chunk(session)
    candidate = json.loads(candidate_response(chunk.id))["candidates"][0]
    oversized = json.dumps({"candidates": [candidate] * 65})
    provider = ScriptedGenerationProvider([oversized, oversized])

    with pytest.raises(StructuredOutputError):
        extract_memory_candidates(session, source, provider)

    assert len(provider.requests) == 2
    assert session.scalar(select(func.count()).select_from(Decision)) == 0
