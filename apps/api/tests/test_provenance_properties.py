import copy
import zipfile

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from proofline.evidence_packages import (
    EvidencePackageError,
    build_decision_package,
    load_and_verify_package,
    verify_decision_package,
)
from proofline.ingestion import chunk_markdown, ingest_source, line_number
from proofline.models import Decision, ModelRun
from proofline.portability import PortabilityError, verify_portable_export
from proofline.schemas import SourceCreate
from sqlalchemy import select

JSON_SCALARS = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=True, allow_infinity=True)
    | st.text(max_size=100)
)
JSON_VALUES = st.recursive(
    JSON_SCALARS,
    lambda children: (
        st.lists(children, max_size=8) | st.dictionaries(st.text(max_size=30), children, max_size=8)
    ),
    max_leaves=30,
)


@given(
    content=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        max_size=600,
    ),
    max_chars=st.integers(min_value=1, max_value=80),
)
@settings(max_examples=150)
def test_markdown_chunks_always_resolve_to_exact_monotonic_source_spans(
    content: str, max_chars: int
):
    spans = chunk_markdown(content, max_chars=max_chars)

    previous_end = 0
    for span in spans:
        assert 0 <= span.start_offset < span.end_offset <= len(content)
        assert span.start_offset >= previous_end
        assert span.text == content[span.start_offset : span.end_offset]
        assert span.start_line == line_number(content, span.start_offset)
        assert span.end_line == line_number(content, span.end_offset - 1)
        assert len(span.text) <= max_chars
        previous_end = span.end_offset


@given(value=JSON_VALUES)
@settings(max_examples=150)
def test_untrusted_package_and_portable_json_never_escape_safe_validation_errors(value):
    for verifier, error_type in (
        (verify_decision_package, EvidencePackageError),
        (verify_portable_export, PortabilityError),
    ):
        try:
            verifier(value)
        except error_type as exc:
            assert str(exc) == getattr(exc, "code", str(exc))


@given(data=st.binary(max_size=4096))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_package_loader_fuzz_fails_with_content_free_codes(tmp_path, data: bytes):
    path = tmp_path / "fuzz-package.json"
    path.write_bytes(data)

    try:
        _document, report = load_and_verify_package(path)
        assert report["valid"] is True
    except EvidencePackageError as exc:
        assert str(exc) == exc.code
        sentinel = data[:20].decode("utf-8", errors="ignore")
        if len(sentinel) >= 8:
            assert sentinel not in str(exc)


@given(
    entry_name=st.sampled_from(
        ["evidence.json", "../evidence.json", "/evidence.json", "nested/evidence.json"]
    ),
    payload=st.binary(max_size=2048),
    compressed=st.booleans(),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_archive_import_fuzz_never_bypasses_safe_verification(
    tmp_path, entry_name: str, payload: bytes, compressed: bool
):
    path = tmp_path / "fuzz-archive.zip"
    compression = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        archive.writestr(entry_name, payload)

    try:
        _document, report = load_and_verify_package(path)
        assert report["valid"] is True
    except EvidencePackageError as exc:
        assert str(exc) == exc.code


@given(delta=st.integers(min_value=-10_000, max_value=10_000).filter(lambda value: value != 0))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_any_citation_offset_drift_is_rejected(session, delta: int):
    source, _created = ingest_source(
        session,
        SourceCreate(
            title="Property ADR",
            uri="property:///citation.md",
            content="Decision: Keep exact citation spans.\nReason: provenance must fail closed.",
        ),
    )
    decision = session.scalar(
        select(Decision).where(
            Decision.source_version_id == source.current_version_id,
            Decision.kind == "decision",
        )
    )
    package = copy.deepcopy(build_decision_package(session, decision.id))
    package["payload"]["citations"][0]["start_offset"] += delta

    try:
        verify_decision_package(package)
    except EvidencePackageError as exc:
        assert exc.code in {"citation_reference_invalid", "citation_span_invalid"}
    else:
        raise AssertionError("citation offset drift was accepted")


@given(foreign_workspace_id=st.uuids().map(str))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_any_cross_workspace_model_lineage_is_rejected(session, foreign_workspace_id: str):
    source, _created = ingest_source(
        session,
        SourceCreate(
            title="Workspace property ADR",
            uri="property:///workspace.md",
            content="Decision: Reject cross-workspace provenance references.",
        ),
    )
    assume(foreign_workspace_id != source.workspace_id)
    decision = session.scalar(
        select(Decision).where(
            Decision.source_version_id == source.current_version_id,
            Decision.kind == "decision",
        )
    )
    run = ModelRun(
        workspace_id=source.workspace_id,
        provider_id="property-provider",
        model_id="property-model",
        operation="generate",
        template_version="property-v1",
        input_hashes=["a" * 64],
        status="succeeded",
        validation_status="valid",
    )
    session.add(run)
    session.flush()
    decision.extraction_method = "model"
    decision.model_run_id = run.id
    session.flush()
    package = copy.deepcopy(build_decision_package(session, decision.id))
    package["payload"]["transformation"]["model_runs"][-1]["workspace_id"] = foreign_workspace_id

    try:
        verify_decision_package(package)
    except EvidencePackageError as exc:
        assert exc.code == "model_run_lineage_invalid"
    else:
        raise AssertionError("cross-workspace model lineage was accepted")
