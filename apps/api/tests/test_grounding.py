import json

import pytest
from proofline.grounding import (
    EvidenceIntegrityError,
    GroundingValidationError,
    answer_question,
)
from proofline.ingestion import ingest_source
from proofline.model_gateway import FakeGenerationProvider
from proofline.models import Chunk, ModelRun
from proofline.retrieval import lexical_search
from proofline.schemas import SourceCreate
from sqlalchemy import select


def indexed_evidence(session):
    content = (
        "# Queue decision\n\n"
        "Decision: Use NATS for the local control plane.\n"
        "Reason: It reduces operational complexity."
    )
    source, _created = ingest_source(
        session,
        SourceCreate(title="Queue ADR", uri="file:///queue.md", content=content),
    )
    hit = lexical_search(session, "operational complexity", 5)[0]
    return source, hit


def test_grounded_answer_resolves_only_server_owned_exact_citations(session):
    source, hit = indexed_evidence(session)
    provider = FakeGenerationProvider(
        json.dumps(
            {
                "statements": [
                    {
                        "text": "NATS was selected to reduce operational complexity.",
                        "kind": "direct",
                        "evidence_ids": [hit.chunk_id],
                    }
                ]
            }
        )
    )

    answer = answer_question(session, "Why was NATS selected?", provider)

    assert answer.status == "grounded"
    assert answer.citations[0].evidence_id == hit.chunk_id
    assert answer.citations[0].content == hit.content
    assert (
        source.content[answer.citations[0].start_offset : answer.citations[0].end_offset]
        == answer.citations[0].content
    )
    run = session.get(ModelRun, answer.model_run_id)
    assert run.status == "succeeded"
    assert run.validation_status == "valid"
    assert run.input_hashes == [source.versions[0].content_hash]


def test_unknown_model_citation_fails_closed_and_marks_run(session):
    indexed_evidence(session)
    provider = FakeGenerationProvider(
        json.dumps(
            {
                "statements": [
                    {
                        "text": "Unsupported claim",
                        "kind": "direct",
                        "evidence_ids": ["invented-evidence-id"],
                    }
                ]
            }
        )
    )

    with pytest.raises(GroundingValidationError) as raised:
        answer_question(session, "Why was NATS selected?", provider)

    run = session.get(ModelRun, raised.value.run_id)
    assert run.status == "failed"
    assert run.validation_status == "grounding_invalid"
    assert run.error_code == "grounding_unknown_evidence"


def test_provider_unavailable_returns_verified_evidence_without_claims(session):
    _source, hit = indexed_evidence(session)

    answer = answer_question(session, "operational complexity", None)

    assert answer.status == "provider_unavailable"
    assert answer.statements == []
    assert answer.citations[0].evidence_id == hit.chunk_id
    assert answer.model_run_id is None


def test_no_retrieval_match_returns_insufficient_evidence_without_model_call(session):
    answer = answer_question(
        session, "a topic that is absent", FakeGenerationProvider("not valid json")
    )

    assert answer.status == "insufficient_evidence"
    assert answer.citations == []
    assert session.scalar(select(ModelRun)) is None


def test_corrupted_chunk_span_is_rejected_before_generation(session):
    _source, hit = indexed_evidence(session)
    chunk = session.get(Chunk, hit.chunk_id)
    chunk.content = "tampered content"
    session.commit()

    with pytest.raises(EvidenceIntegrityError):
        answer_question(session, "operational complexity", FakeGenerationProvider("{}"))

    assert session.scalar(select(ModelRun)) is None
