from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from .database import initialize_database, make_engine
from .decision_health import DecisionHealthFinding, check_decision_health
from .evidence_packages import (
    EvidencePackageError,
    atomic_write_html_report,
    atomic_write_package,
    build_decision_package,
    load_and_verify_package,
)
from .ingestion import ingest_source
from .models import Decision, Evidence, SourceVersion
from .portability import PortabilityError, atomic_write_export
from .schemas import SourceCreate

DEMO_DIRECTORY = "proofline-demo-stale-decision"
DEMO_URI = "file:///demo/requirement.md"
EVIDENCE_START_LINE = 42
EVIDENCE_END_LINE = 48
DEMO_MARKER = ".proofline-stale-decision-demo"


def _requirement_content(*, changed: bool) -> str:
    preface = [f"Context line {number:02d}." for number in range(1, EVIDENCE_START_LINE)]
    requirement = [
        "## Queue durability requirement",
        "The desktop application must operate without a network service.",
        "All writes must survive an application restart.",
        "The supported workload is one local user.",
        (
            "The local queue may lose acknowledged work during a process crash."
            if changed
            else "The local queue must not lose acknowledged work during a process crash."
        ),
        "Recovery must complete without operator intervention.",
        "This requirement is release-blocking.",
    ]
    return "\n".join([*preface, *requirement, "", "End of requirement."])


def _create_approved_decision(session, source) -> Decision:
    version = session.get(SourceVersion, source.current_version_id)
    if version is None:
        raise EvidencePackageError("demo_source_version_missing")
    lines = version.content.splitlines(keepends=True)
    start_offset = sum(len(line) for line in lines[: EVIDENCE_START_LINE - 1])
    end_offset = sum(len(line) for line in lines[:EVIDENCE_END_LINE])
    quote = version.content[start_offset:end_offset].rstrip("\n")
    end_offset = start_offset + len(quote)
    decision = Decision(
        source_id=source.id,
        source_version_id=version.id,
        kind="decision",
        title="ADR-007 · Keep the durable queue in SQLite",
        statement="Use SQLite for the desktop application's durable local queue.",
        rationale=(
            "The approved requirement rules out a network service and requires crash recovery."
        ),
        status="accepted",
        confidence=1.0,
        extraction_method="deterministic",
        created_at=datetime(2026, 7, 16, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 16, 9, 30, tzinfo=UTC),
    )
    session.add(decision)
    session.flush()
    session.add(
        Evidence(
            decision_id=decision.id,
            source_id=source.id,
            source_version_id=version.id,
            quote=quote,
            quote_hash=hashlib.sha256(quote.encode()).hexdigest(),
            start_offset=start_offset,
            end_offset=end_offset,
            start_line=EVIDENCE_START_LINE,
            end_line=EVIDENCE_END_LINE,
        )
    )
    session.commit()
    session.refresh(decision)
    return decision


def _write_health_receipt(
    output: Path,
    finding: DecisionHealthFinding,
    *,
    package_root: str,
) -> None:
    document = {
        "schema": "proofline-decision-health-receipt-v1",
        "status": "review_required",
        "package_root": package_root,
        "finding": finding.model_dump(),
    }
    try:
        atomic_write_export(output, document)
    except PortabilityError as exc:
        raise EvidencePackageError(exc.code) from exc


def _write_demo_marker(output: Path) -> None:
    try:
        atomic_write_export(
            output,
            {"schema": "proofline-stale-decision-demo-directory-v1"},
        )
    except PortabilityError as exc:
        raise EvidencePackageError(exc.code) from exc


def run_stale_decision_demo(output_dir: Path, *, force: bool = False) -> dict[str, object]:
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        if not force:
            raise EvidencePackageError("output_exists")
        if not (output_dir / DEMO_MARKER).is_file():
            raise EvidencePackageError("output_directory_not_demo")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, mode=0o700)
    _write_demo_marker(output_dir / DEMO_MARKER)

    demo_engine = make_engine("sqlite:///:memory:")
    initialize_database(demo_engine)
    factory = sessionmaker(bind=demo_engine, expire_on_commit=False)
    try:
        with factory() as session:
            source, _created = ingest_source(
                session,
                SourceCreate(
                    title="requirement.md",
                    uri=DEMO_URI,
                    content=_requirement_content(changed=False),
                ),
            )
            decision = _create_approved_decision(session, source)
            evidence_package = build_decision_package(
                session, decision.id, created_at=datetime(2026, 7, 16, 9, 30, tzinfo=UTC)
            )
            package_path = output_dir / "evidence.zip"
            atomic_write_package(package_path, evidence_package)

            ingest_source(
                session,
                SourceCreate(
                    title="requirement.md",
                    uri=DEMO_URI,
                    content=_requirement_content(changed=True),
                ),
            )
            findings = check_decision_health(session)
            finding = next(
                (item for item in findings if item.decision_id == decision.id),
                None,
            )
            if finding is None:
                raise EvidencePackageError("demo_stale_decision_not_detected")

            report_path = output_dir / "report.html"
            atomic_write_html_report(
                report_path,
                evidence_package,
                findings=[finding.model_dump()],
                force=False,
            )
            receipt_path = output_dir / "decision-health.json"
            _write_health_receipt(
                receipt_path,
                finding,
                package_root=evidence_package["manifest"]["root_hash"],
            )
            _document, verification = load_and_verify_package(package_path)
            return {
                "status": "review_required",
                "finding": finding,
                "package": package_path,
                "report": report_path,
                "health_receipt": receipt_path,
                "verification": verification,
            }
    finally:
        demo_engine.dispose()
