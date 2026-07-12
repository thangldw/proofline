import json

import pytest
from proofline.grounding import (
    EvidenceIntegrityError,
    GroundingValidationError,
    answer_question,
)
from proofline.ingestion import ingest_source
from proofline.model_gateway import (
    FakeGenerationProvider,
    GenerationResult,
    ProviderRequestError,
    StructuredOutputError,
)
from proofline.models import Chunk, ModelRun
from proofline.retrieval import lexical_search
from proofline.schemas import SourceCreate
from sqlalchemy import select


class ScriptedGenerationProvider:
    id = "scripted"
    model = "scripted-repair-test"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return GenerationResult(content=outcome, prompt_tokens=2, completion_tokens=3)


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
    provider = ScriptedGenerationProvider(
        [
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
        ]
    )

    answer = answer_question(session, "Why was NATS selected?", provider)

    assert len(provider.requests) == 1
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
    assert run.parent_run_id is None
    assert run.attempt_number == 1
    assert run.repair_reason is None


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


def test_structured_output_is_repaired_once_with_private_lineage(session):
    source, hit = indexed_evidence(session)
    invalid_output = "PRIVATE INVALID MODEL OUTPUT"
    valid_output = json.dumps(
        {
            "statements": [
                {
                    "text": "NATS reduces operational complexity.",
                    "kind": "direct",
                    "evidence_ids": [hit.chunk_id],
                }
            ]
        }
    )
    provider = ScriptedGenerationProvider([invalid_output, valid_output])

    answer = answer_question(session, "Why NATS?", provider)

    assert answer.status == "grounded"
    assert len(provider.requests) == 2
    runs = list(session.scalars(select(ModelRun).order_by(ModelRun.attempt_number)).all())
    assert len(runs) == 2
    assert runs[0].status == "failed"
    assert runs[0].error_code == "structured_output_invalid"
    assert runs[0].parent_run_id is None
    assert runs[0].attempt_number == 1
    assert runs[1].status == "succeeded"
    assert runs[1].parent_run_id == runs[0].id
    assert runs[1].attempt_number == 2
    assert runs[1].repair_reason == "structured_output_invalid"
    assert runs[1].input_hashes == runs[0].input_hashes == [source.versions[0].content_hash]
    assert answer.model_run_id == runs[1].id
    repair_prompt = " ".join(message.content for message in provider.requests[1].messages)
    assert invalid_output not in repair_prompt
    persisted = " ".join(
        str(getattr(run, column.name)) for run in runs for column in ModelRun.__table__.columns
    )
    assert invalid_output not in persisted


def test_unknown_citation_is_repaired_with_the_same_evidence_pack(session):
    _source, hit = indexed_evidence(session)
    invalid = json.dumps(
        {"statements": [{"text": "Unsupported", "kind": "direct", "evidence_ids": ["invented"]}]}
    )
    valid = json.dumps(
        {
            "statements": [
                {
                    "text": "NATS reduces complexity.",
                    "kind": "direct",
                    "evidence_ids": [hit.chunk_id],
                }
            ]
        }
    )
    provider = ScriptedGenerationProvider([invalid, valid])

    answer = answer_question(session, "Why NATS?", provider)

    runs = list(session.scalars(select(ModelRun).order_by(ModelRun.attempt_number)).all())
    assert answer.citations[0].evidence_id == hit.chunk_id
    assert runs[0].error_code == "grounding_unknown_evidence"
    assert runs[1].parent_run_id == runs[0].id
    assert runs[1].repair_reason == "grounding_unknown_evidence"


def test_missing_direct_citation_is_repaired_once(session):
    _source, hit = indexed_evidence(session)
    missing = json.dumps(
        {"statements": [{"text": "NATS reduces complexity.", "kind": "direct", "evidence_ids": []}]}
    )
    valid = json.dumps(
        {
            "statements": [
                {
                    "text": "NATS reduces complexity.",
                    "kind": "direct",
                    "evidence_ids": [hit.chunk_id],
                }
            ]
        }
    )
    provider = ScriptedGenerationProvider([missing, valid])

    answer = answer_question(session, "Why NATS?", provider)

    runs = list(session.scalars(select(ModelRun).order_by(ModelRun.attempt_number)).all())
    assert answer.citations[0].evidence_id == hit.chunk_id
    assert len(provider.requests) == 2
    assert runs[0].error_code == "grounding_missing_citation"
    assert runs[1].parent_run_id == runs[0].id
    assert runs[1].repair_reason == "grounding_missing_citation"


def test_two_invalid_outputs_stop_at_the_bounded_limit(session):
    indexed_evidence(session)
    provider = ScriptedGenerationProvider(["not json one", "not json two"])

    with pytest.raises(StructuredOutputError) as raised:
        answer_question(session, "Why NATS?", provider)

    runs = list(session.scalars(select(ModelRun).order_by(ModelRun.attempt_number)).all())
    assert len(provider.requests) == 2
    assert len(runs) == 2
    assert raised.value.run_id == runs[1].id
    assert runs[1].parent_run_id == runs[0].id
    assert runs[1].status == "failed"


def test_provider_failure_is_not_repaired_and_carries_run_id(session):
    indexed_evidence(session)
    provider = ScriptedGenerationProvider([ProviderRequestError("safe provider failure")])

    with pytest.raises(ProviderRequestError) as raised:
        answer_question(session, "Why NATS?", provider)

    run = session.scalar(select(ModelRun))
    assert len(provider.requests) == 1
    assert raised.value.run_id == run.id
    assert run.status == "failed"
    assert run.error_code == "provider_request_failed"


def test_provider_failure_during_repair_propagates_the_repair_run_id(session):
    indexed_evidence(session)
    provider = ScriptedGenerationProvider(
        ["not json", ProviderRequestError("safe repair provider failure")]
    )

    with pytest.raises(ProviderRequestError) as raised:
        answer_question(session, "Why NATS?", provider)

    runs = list(session.scalars(select(ModelRun).order_by(ModelRun.attempt_number)).all())
    assert len(provider.requests) == 2
    assert len(runs) == 2
    assert raised.value.run_id == runs[1].id
    assert runs[1].parent_run_id == runs[0].id
    assert runs[1].repair_reason == "structured_output_invalid"
    assert runs[1].error_code == "provider_request_failed"
