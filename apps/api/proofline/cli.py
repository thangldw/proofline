from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, NoReturn, cast

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError

from . import __version__
from .attestations import (
    AttestationError,
    atomic_write_attestation,
    attestation_paths_conflict,
    build_signed_attestation,
    generate_attestation_keypair,
    load_and_verify_attestation,
    load_attestation_private_key,
    load_attestation_public_key,
    load_revoked_key_ids,
    verify_signed_attestation,
)
from .backup import (
    BackupError,
    create_sqlite_backup,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from .config import get_settings
from .database import SessionLocal, engine, initialize_database
from .decision_asof import AsOfError, decisions_as_of, parse_as_of
from .decision_blame import DecisionBlameError, blame
from .decision_code_refs import CodeRefError, check_code_refs, scan_code_refs
from .decision_conflicts import find_conflict_candidates, suggest_links
from .decision_context import (
    ContextError,
    build_context,
    git_diff,
    parse_unified_diff,
)
from .decision_context import (
    render_markdown as render_context_markdown,
)
from .decision_enforce import EnforceError, check_enforcement
from .decision_expiry import check_expiry
from .decision_export import DecisionExportError, export_adrs
from .decision_graph import build_graph, render_dot, render_mermaid
from .decision_health import DecisionHealthError, check_decision_health
from .decision_impacts import compute_decision_impacts
from .decision_import import AdrImportError, import_adrs
from .decision_ledger import (
    DEFAULT_LEDGER,
    LedgerError,
    append_entry,
    compare_with_base,
    ledger_at_ref,
    read_ledger,
    render_comparison,
)
from .decision_notify import NotifyError, send_expiry_notification
from .decision_policy import (
    DecisionPolicyError,
    load_decision_policy,
    policy_sha256,
)
from .decision_rebind import apply_rebind, list_pending_reviews, preview_rebind
from .decision_report import build_report, render_report_html, render_report_markdown
from .decision_reviews import DecisionReviewError, refresh_decision_reviews
from .decision_trend import record_all_snapshots, render_markdown, trend
from .decision_watch import watch_folder
from .decision_why import DecisionWhyError, why
from .doctor import run_doctor
from .embeddings import index_current_embeddings
from .evaluation import (
    benchmark_lexical_search,
    evaluate_dataset,
    evaluate_extraction_dataset,
    evaluate_grounded_dataset,
    extraction_report_meets_thresholds,
    grounded_report_meets_thresholds,
)
from .evidence_packages import (
    EvidencePackageError,
    atomic_write_html_report,
    atomic_write_package,
    build_decision_package,
    diff_decision_packages,
    explain_decision_package,
    load_and_verify_package,
)
from .git_hook import HookError, install_hook, uninstall_hook
from .ingestion import ingest_source
from .integrity import IntegrityVerificationError, verify_live_database
from .mcp_server import serve_stdio
from .model_gateway import ProviderConfigurationError, build_embedding_provider
from .models import DecisionReview, SourceVersion, Workspace
from .policy_schema import render_policy_schema
from .portability import (
    PortabilityError,
    atomic_write_export,
    build_portable_export,
    load_and_verify_export,
)
from .portable_import import (
    import_portable_export,
    load_verified_import,
    merge_portable_export,
    preview_portable_merge,
)
from .real_model_evaluation import (
    preflight_real_model_plan,
    run_real_model_comparison,
    write_comparison_receipt,
    write_preflight_receipt,
)
from .review_receipts import (
    ReviewReceiptError,
    build_review_receipt,
    load_and_verify_review_receipt,
)
from .sarif import build_decision_health_sarif, build_decision_impact_sarif
from .schemas import SourceCreate
from .server import run_server
from .shell_completion import render_completion
from .stale_decision_demo import DEMO_DIRECTORY, run_stale_decision_demo
from .workspace_sync import WorkspaceSyncError, sync_folder


def unit_interval(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a number between 0 and 1") from exc
    if not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("expected a number between 0 and 1")
    return number


def seed_demo() -> None:
    initialize_database()
    demo_name = "architecture-decision.md"
    content = files("proofline").joinpath("data", demo_name).read_text(encoding="utf-8")
    with SessionLocal() as session:
        source, created = ingest_source(
            session,
            SourceCreate(
                title=demo_name,
                content=content,
                uri=f"proofline://examples/{demo_name}",
            ),
        )
    print(f"{'Indexed' if created else 'Already indexed'}: {source.title} ({source.id})")


def _decision_check_failed(code: str) -> NoReturn:
    print(f"decision check failed: {code}", file=sys.stderr)
    raise SystemExit(2)


def _impact_check_failed(code: str) -> NoReturn:
    print(f"impact check failed: {code}", file=sys.stderr)
    raise SystemExit(2)


def _parse_impact_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _impact_check_failed("as_of_invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _impact_check_failed("as_of_timezone_required")
    return parsed.astimezone(UTC)


def _parse_attestation_time(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AttestationError("issued_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AttestationError("issued_at_invalid")
    return parsed.astimezone(UTC)


def _reject_attestation_output_conflict(
    output: Path,
    *,
    package: Path,
    private_key: Path,
    review_receipt: Path | None,
) -> None:
    inputs = [package, private_key]
    if review_receipt is not None:
        inputs.append(review_receipt)
    if any(attestation_paths_conflict(output, path) for path in inputs):
        raise AttestationError("output_conflict")


def _cmd_serve(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.no_web:
        os.environ["PROOFLINE_DISABLE_WEB"] = "true"
    if args.web_dir is not None:
        web_dir = args.web_dir.expanduser().resolve()
        if not (web_dir / "index.html").is_file():
            parser.error("--web-dir must contain index.html")
        os.environ["PROOFLINE_WEB_DIR"] = str(web_dir)
    try:
        run_server(
            args.host,
            args.port,
            ready_file=args.ready_file,
            shutdown_file=args.shutdown_file,
            log_level=args.log_level,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"serve failed: {type(exc).__name__}") from exc


def _cmd_launch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    data_dir = Path(os.environ.get("PROOFLINE_HOME", Path.cwd() / ".proofline"))
    try:
        run_server(
            "127.0.0.1",
            args.port,
            ready_file=data_dir / "proofline-ready.json",
            log_level=args.log_level,
            open_browser=not args.no_browser,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"launch failed: {type(exc).__name__}") from exc


def _cmd_seed(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    seed_demo()


def _cmd_mcp(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    initialize_database()
    serve_stdio(
        sys.stdin,
        sys.stdout,
        include_titles=args.include_titles,
        include_excerpts=args.include_excerpts,
    )


def _cmd_sync(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        initialize_database()
        with SessionLocal() as session:
            summary = sync_folder(session, args.path, uri_root=args.uri_root)
    except WorkspaceSyncError as exc:
        raise SystemExit(f"sync failed: {exc.code}") from exc
    except (OSError, SQLAlchemyError) as exc:
        raise SystemExit("sync failed: database_unavailable") from exc
    if args.format == "json":
        print(json.dumps(summary.model_dump(), sort_keys=True))
    else:
        print(
            f"Synced: {summary.created} created, {summary.updated} updated, "
            f"{summary.unchanged} unchanged, {len(summary.failed)} failed"
        )
    if summary.failed:
        raise SystemExit(1)


def _cmd_eval(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    report = evaluate_dataset(args.dataset, args.k)
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    if (
        report.recall_at_k < args.min_recall
        or report.ndcg_at_k < args.min_ndcg
        or report.expected_empty_accuracy < args.min_expected_empty_accuracy
    ):
        raise SystemExit(1)


def _cmd_eval_grounded(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    report = evaluate_grounded_dataset(args.dataset, args.limit)
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    if not grounded_report_meets_thresholds(
        report,
        min_citation_resolution=args.min_citation_resolution,
        min_citation_precision=args.min_citation_precision,
        min_grounded_success=args.min_grounded_success,
        min_status_accuracy=args.min_status_accuracy,
    ):
        raise SystemExit(1)


def _cmd_eval_extraction(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    report = evaluate_extraction_dataset(args.dataset)
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    if not extraction_report_meets_thresholds(
        report,
        min_precision=args.min_precision,
        min_recall=args.min_recall,
        min_f1=args.min_f1,
        min_evidence_resolution=args.min_evidence_resolution,
        min_expected_evidence_accuracy=args.min_expected_evidence_accuracy,
        min_negative_source_accuracy=args.min_negative_source_accuracy,
    ):
        raise SystemExit(1)


def _cmd_eval_real_model_preflight(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    try:
        receipt = preflight_real_model_plan(args.plan, allow_mock=args.allow_mock)
        write_preflight_receipt(args.output, receipt, force=args.force)
    except (FileExistsError, OSError, ValueError) as exc:
        raise SystemExit(f"real-model preflight failed: {type(exc).__name__}") from exc
    print(receipt.model_dump_json(indent=2))
    if receipt.status != "ready":
        raise SystemExit(1)


def _cmd_eval_real_model(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        comparison = run_real_model_comparison(args.plan, allow_mock=args.allow_mock)
        write_comparison_receipt(args.output, comparison, force=args.force)
    except (FileExistsError, OSError, ValueError) as exc:
        raise SystemExit(f"real-model comparison failed: {type(exc).__name__}") from exc
    print(comparison.model_dump_json(indent=2))
    if comparison.status != "completed":
        raise SystemExit(1)


def _cmd_benchmark(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        report = benchmark_lexical_search(args.sources, args.queries, args.limit)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))


def _cmd_embed(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    initialize_database()
    try:
        provider = build_embedding_provider(get_settings())
    except ProviderConfigurationError as exc:
        raise SystemExit(str(exc)) from exc
    if provider is None:
        raise SystemExit("embedding provider is disabled")
    with SessionLocal() as session:
        report = index_current_embeddings(session, provider)
    print(
        json.dumps(
            {
                "indexed": report.indexed,
                "skipped": report.skipped,
                "model_run_ids": report.model_run_ids,
            },
            indent=2,
        )
    )


def _cmd_export(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    initialize_database()
    try:
        with SessionLocal() as session, session.begin():
            document = build_portable_export(session)
        atomic_write_export(args.output, document, force=args.force)
    except PortabilityError as exc:
        raise SystemExit(f"export failed: {exc.code}") from exc
    print(
        json.dumps(
            {
                "schema": document["manifest"]["schema"],
                "payload_sha256": document["manifest"]["payload_sha256"],
                "counts": document["manifest"]["counts"],
            },
            sort_keys=True,
        )
    )


def _cmd_verify_export(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        counts = load_and_verify_export(args.path)
    except PortabilityError as exc:
        raise SystemExit(f"export verification failed: {exc.code}") from exc
    print(json.dumps({"valid": True, "counts": counts}, sort_keys=True))


def _cmd_export_package(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    initialize_database()
    try:
        if (
            args.html_report is not None
            and args.output.expanduser().resolve() == args.html_report.expanduser().resolve()
        ):
            raise EvidencePackageError("report_output_conflicts_with_package")
        with SessionLocal() as session:
            document = build_decision_package(session, args.artifact_id)
        atomic_write_package(args.output, document, force=args.force)
        if args.html_report is not None:
            atomic_write_html_report(args.html_report, document, force=args.force)
    except EvidencePackageError as exc:
        raise SystemExit(f"package export failed: {exc.code}") from exc
    print(
        json.dumps(
            {
                "schema": document["manifest"]["schema"],
                "root_hash": document["manifest"]["root_hash"],
                "artifact_id": document["payload"]["artifact"]["id"],
            },
            sort_keys=True,
        )
    )


def _cmd_verify_package(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        _document, report = load_and_verify_package(args.path)
    except EvidencePackageError as exc:
        raise SystemExit(f"package verification failed: {exc.code}") from exc
    print(json.dumps(report, sort_keys=True))


def _cmd_export_review_receipt(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    initialize_database()
    try:
        _package, package_report = load_and_verify_package(args.package)
        with SessionLocal() as session:
            review = session.get(DecisionReview, args.review_id)
            if review is None:
                raise ReviewReceiptError("review_not_found")
            if package_report["artifact_id"] != review.decision_id:
                raise ReviewReceiptError("package_artifact_mismatch")
            cited = session.get(SourceVersion, review.cited_source_version_id)
            current = session.get(SourceVersion, review.current_source_version_id)
            if cited is None or current is None:
                raise ReviewReceiptError("source_version_not_found")
            document = build_review_receipt(
                review,
                package_report["root_hash"],
                cited_content_sha256=cited.content_hash,
                current_content_sha256=current.content_hash,
            )
        atomic_write_export(args.output, document)
    except (EvidencePackageError, PortabilityError, ReviewReceiptError) as exc:
        raise SystemExit(f"review receipt export failed: {exc.code}") from exc
    print(
        json.dumps(
            {
                "schema": document["schema"],
                "review_id": document["review_id"],
                "receipt_hash": document["receipt_hash"],
                "dep_root_hash": document["dep_root_hash"],
            },
            sort_keys=True,
        )
    )


def _cmd_verify_review_receipt(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        _document, report = load_and_verify_review_receipt(args.path)
    except ReviewReceiptError as exc:
        raise SystemExit(f"review receipt verification failed: {exc.code}") from exc
    print(json.dumps(report, sort_keys=True))


def _cmd_generate_attestation_key(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    try:
        report = generate_attestation_keypair(
            args.private_key,
            args.public_key,
            force=args.force,
        )
    except AttestationError as exc:
        raise SystemExit(f"attestation key generation failed: {exc.code}") from exc
    print(json.dumps(report, sort_keys=True))


def _cmd_attest(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        _reject_attestation_output_conflict(
            args.output,
            package=args.package,
            private_key=args.private_key,
            review_receipt=args.review_receipt,
        )
        _package, package_report = load_and_verify_package(args.package)
        review_report = None
        if args.review_receipt is not None:
            _receipt, review_report = load_and_verify_review_receipt(args.review_receipt)
        private_key = load_attestation_private_key(args.private_key)
        document = build_signed_attestation(
            package_report=package_report,
            review_report=review_report,
            private_key=private_key,
            issued_at=_parse_attestation_time(args.issued_at),
        )
        atomic_write_attestation(args.output, document, force=args.force)
        report = verify_signed_attestation(document, private_key.public_key())
    except (AttestationError, EvidencePackageError, ReviewReceiptError) as exc:
        raise SystemExit(f"attestation failed: {exc.code}") from exc
    print(json.dumps(report, sort_keys=True))


def _cmd_verify_attestation(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        _package, package_report = load_and_verify_package(args.package)
        review_report = None
        if args.review_receipt is not None:
            _receipt, review_report = load_and_verify_review_receipt(args.review_receipt)
        public_key = load_attestation_public_key(args.public_key)
        revoked = (
            load_revoked_key_ids(args.revocations) if args.revocations is not None else frozenset()
        )
        document, report = load_and_verify_attestation(
            args.path,
            public_key,
            revoked_key_ids=revoked,
            package_report=package_report,
            review_report=review_report,
        )
        if document["statement"]["review_receipt"] is not None and review_report is None:
            raise AttestationError("review_subject_required")
    except (AttestationError, EvidencePackageError, ReviewReceiptError) as exc:
        raise SystemExit(f"attestation verification failed: {exc.code}") from exc
    print(json.dumps(report, sort_keys=True))


def _cmd_explain(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    initialize_database()
    try:
        with SessionLocal() as session:
            document = build_decision_package(session, args.artifact_id)
        report = explain_decision_package(document)
    except EvidencePackageError as exc:
        raise SystemExit(f"artifact explanation failed: {exc.code}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_diff(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        before, _before_report = load_and_verify_package(args.before)
        after, _after_report = load_and_verify_package(args.after)
        report = diff_decision_packages(before, after)
    except EvidencePackageError as exc:
        raise SystemExit(f"package diff failed: {exc.code}") from exc
    print(json.dumps(report, sort_keys=True))


def _cmd_import(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    initialize_database()
    try:
        document = load_verified_import(args.path)
        with SessionLocal() as session:
            if args.preview_merge:
                report = preview_portable_merge(session, document)
            elif args.merge:
                if not args.preview_sha256:
                    raise PortabilityError("merge_preview_required")
                with session.begin():
                    report = merge_portable_export(
                        session,
                        document,
                        expected_preview_sha256=args.preview_sha256,
                    )
            else:
                with session.begin():
                    report = import_portable_export(session, document)
    except PortabilityError as exc:
        raise SystemExit(f"import failed: {exc.code}") from exc
    print(json.dumps({"valid": True, **report}, sort_keys=True))


def _cmd_backup(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if engine.dialect.name != "sqlite":
        raise SystemExit("backup failed: sqlite_required")
    initialize_database()
    try:
        report = create_sqlite_backup(engine, args.output, force=args.force)
    except BackupError as exc:
        raise SystemExit(f"backup failed: {exc.code}") from exc
    print(json.dumps({"valid": True, **report}, sort_keys=True))


def _cmd_verify_backup(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        report = verify_sqlite_backup(args.path)
    except BackupError as exc:
        raise SystemExit(f"backup verification failed: {exc.code}") from exc
    print(json.dumps({"valid": True, **report}, sort_keys=True))


def _cmd_restore_backup(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if engine.dialect.name != "sqlite" or not engine.url.database:
        raise SystemExit("backup restore failed: sqlite_file_required")
    if engine.url.database == ":memory:":
        raise SystemExit("backup restore failed: sqlite_file_required")
    engine.dispose()
    try:
        report = restore_sqlite_backup(
            args.path,
            Path(engine.url.database),
            rollback_output=args.rollback_output,
        )
    except BackupError as exc:
        raise SystemExit(f"backup restore failed: {exc.code}") from exc
    print(json.dumps({"valid": True, **report}, sort_keys=True))


def _cmd_verify_integrity(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        report = verify_live_database(engine)
    except IntegrityVerificationError as exc:
        raise SystemExit(f"integrity verification failed: {exc.code}") from exc
    print(json.dumps(report, sort_keys=True))


def _cmd_blame(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    target: str = args.target
    line: int | None = args.line
    head, sep, tail = target.rpartition(":")
    if line is None and sep and tail.isdigit() and head:
        target, line = head, int(tail)
    try:
        with SessionLocal() as session:
            entries = blame(session, target, line)
    except DecisionBlameError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        print(
            json.dumps(
                {"target": target, "line": line, "entries": [e.model_dump() for e in entries]},
                sort_keys=True,
            )
        )
        return
    if not entries:
        print("No approved decision is anchored here.")
        return
    for entry in entries:
        where = (
            f"{entry.current_start_line}-{entry.current_end_line}"
            if entry.current_start_line is not None
            else "no longer present"
        )
        print(f"[{entry.state}] {entry.decision_title} ({entry.decision_id})")
        print(f"  status {entry.decision_status}; now at lines {where}")
        print(f"  cited at lines {entry.cited_start_line}-{entry.cited_end_line}")


EXPLANATIONS = {
    "moved": "The cited text still exists but its surroundings changed.",
    "changed": "The cited text was edited; a close candidate was found.",
    "ambiguous": "The cited text now appears more than once in the source.",
    "deleted": "The cited text no longer exists in the source.",
}


def _explain_finding(finding: Any, blocking: bool) -> list[str]:
    lines = [EXPLANATIONS.get(finding.reason, finding.reason)]
    lines.append("This blocks the gate." if blocking else "Warning only under the current policy.")
    if finding.reason in {"moved", "changed"} and finding.candidate_start_line is not None:
        lines.append(
            f"Candidate now at lines {finding.candidate_start_line}-{finding.candidate_end_line}. "
            "Fix: proofline refresh-reviews, then proofline rebind <review-id> "
            '(preview the diff) and --apply --reason "...".'
        )
    elif finding.reason == "ambiguous":
        lines.append("Fix: make the cited sentence unique in the source, then re-run the check.")
    else:
        lines.append("Fix: restore the text, or supersede the decision with a new one.")
    lines.append(f'Inspect: proofline blame "{finding.source_title}"')
    return lines


def _cmd_check_decisions(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        policy = load_decision_policy(args.policy)
    except DecisionPolicyError as exc:
        _decision_check_failed(exc.code)
    try:
        with SessionLocal() as session:
            findings = check_decision_health(session)
    except DecisionHealthError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    blocking = [
        finding for finding in findings if finding.reason in policy.fail_on_for(finding.source_uri)
    ]
    if args.format == "sarif":
        document = build_decision_health_sarif(findings, policy)
    elif args.format == "json":
        document = {
            "valid": not blocking,
            "finding_count": len(findings),
            "blocking_count": len(blocking),
            "policy_sha256": policy_sha256(policy),
            "findings": [finding.content_free_model_dump() for finding in findings],
        }
    else:
        document = None
    if args.output is not None:
        if document is None:
            _decision_check_failed("output_format_invalid")
        try:
            atomic_write_export(args.output, document)
        except PortabilityError as exc:
            _decision_check_failed(exc.code)
    elif document is not None:
        print(json.dumps(document, sort_keys=True))
    elif findings:
        for finding in findings:
            print("Decision requires review")
            print(f"{finding.locator} changed after this decision was approved.")
            if args.explain:
                for line in _explain_finding(finding, finding in blocking):
                    print(f"  {line}")
    else:
        print("All approved decision citations resolve in current sources.")
    if blocking:
        raise SystemExit(1)


def _cmd_check_impacts(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    evaluated_at = _parse_impact_as_of(args.as_of)
    try:
        with SessionLocal() as session:
            verify_live_database(cast(Engine, session.get_bind()))
            workspace_ids = session.scalars(select(Workspace.id).order_by(Workspace.id)).all()
            findings = [
                finding
                for workspace_id in workspace_ids
                for finding in compute_decision_impacts(
                    session,
                    workspace_id=workspace_id,
                    as_of=evaluated_at,
                )
            ]
    except IntegrityVerificationError as exc:
        _impact_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _impact_check_failed("database_unavailable")
    if args.format == "sarif":
        document = build_decision_impact_sarif(findings, evaluated_at=evaluated_at)
    elif args.format == "json":
        document = {
            "valid": not findings,
            "finding_count": len(findings),
            "root_review_count": len({item.root_review_id for item in findings}),
            "impacted_decision_count": len({item.impacted_decision_id for item in findings}),
            "evaluated_at": evaluated_at.isoformat(),
            "findings": [item.model_dump() for item in findings],
        }
    else:
        document = None
    if args.output is not None:
        if document is None:
            _impact_check_failed("output_format_invalid")
        try:
            atomic_write_export(args.output, document)
        except PortabilityError as exc:
            _impact_check_failed(exc.code)
    elif document is not None:
        print(json.dumps(document, sort_keys=True))
    else:
        print(f"Evaluated at {evaluated_at.isoformat()}")
        if findings:
            for finding in findings:
                print("Decision transitively impacted")
                print(f"Depth: {finding.depth}")
                print(f"Decision path: {' -> '.join(finding.decision_path)}")
                print(
                    "Relation path: "
                    + " -> ".join(
                        f"{kind}:{relation_id}"
                        for kind, relation_id in zip(
                            finding.relation_kinds,
                            finding.relation_path,
                            strict=True,
                        )
                    )
                )
        else:
            print("No decisions are transitively impacted.")
    if findings:
        raise SystemExit(1)


def _cmd_refresh_reviews(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        policy = load_decision_policy(args.policy)
    except DecisionPolicyError as exc:
        _decision_check_failed(exc.code)
    try:
        initialize_database(engine)
        totals = {key: 0 for key in ("opened", "superseded", "resolved", "updated", "unchanged")}
        with SessionLocal() as session:
            workspace_ids = session.scalars(select(Workspace.id).order_by(Workspace.id)).all()
            for workspace_id in workspace_ids:
                summary = refresh_decision_reviews(
                    session,
                    workspace_id=workspace_id,
                    policy=policy,
                )
                for key, value in summary.model_dump().items():
                    totals[key] += value
            session.commit()
    except DecisionReviewError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    print(
        json.dumps(
            {"valid": True, "policy_sha256": policy_sha256(policy), **totals},
            sort_keys=True,
        )
    )


def _cmd_rebind(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            if args.review_id is None:
                pending = list_pending_reviews(session)
                if args.format == "json":
                    print(json.dumps({"pending": [_review_row(item) for item in pending]}))
                    return
                if not pending:
                    print("No pending reviews. Run `proofline refresh-reviews` to scan.")
                for item in pending:
                    row = _review_row(item)
                    print(f"{row['id']}  {row['anchor_state']}  decision {row['decision_id']}")
                return
            preview = preview_rebind(session, args.review_id)
            if not args.apply:
                if args.format == "json":
                    print(json.dumps(preview.model_dump(), sort_keys=True))
                else:
                    print(f"[{preview.anchor_state}] {preview.decision_title}")
                    print("\n".join(preview.diff) or "(no textual difference to show)")
                    print(
                        'Re-run with --apply --reason "..." to accept the current text.'
                        if preview.can_apply
                        else f"Cannot re-anchor automatically: {preview.blocker}"
                    )
                return
            if not args.reason:
                _decision_check_failed("reason_required")
            review = apply_rebind(session, args.review_id, actor="local_cli", reason=args.reason)
            session.commit()
            print(json.dumps({"review_id": review.id, "state": review.state}, sort_keys=True))
    except DecisionReviewError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")


def _review_row(review: Any) -> dict[str, Any]:
    return {
        "id": review.id,
        "decision_id": review.decision_id,
        "anchor_state": review.anchor_state,
        "state": review.state,
    }


def _cmd_check_expiry(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(UTC).date()
    except ValueError:
        _decision_check_failed("as_of_invalid")
    try:
        with SessionLocal() as session:
            findings = check_expiry(session, as_of=as_of, warn_within_days=args.warn_within)
    except ValueError as exc:
        _decision_check_failed(str(exc))
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    overdue = [item for item in findings if item.state == "overdue"]
    if args.format == "json":
        print(
            json.dumps(
                {
                    "valid": not overdue,
                    "as_of": as_of.isoformat(),
                    "findings": [item.content_free_model_dump() for item in findings],
                },
                sort_keys=True,
            )
        )
    elif not findings:
        print("No approved decision is past its review date.")
    for item in findings if args.format == "text" else []:
        suffix = (
            f"{item.days_overdue} days overdue"
            if item.state == "overdue"
            else f"due in {-item.days_overdue} days"
        )
        print(
            f"[{item.state}] {item.decision_title} ({item.decision_id}): "
            f"review by {item.review_by}, {suffix}"
        )
    if overdue:
        raise SystemExit(1)


def _cmd_why(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            answers = why(session, args.question, limit=args.limit)
    except DecisionWhyError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        print(json.dumps({"answers": [item.model_dump() for item in answers]}, sort_keys=True))
        return
    if not answers:
        print("No approved decision matches that question.")
    for item in answers:
        warning = "" if item.health == "current" else f"  WARNING: citation {item.health}"
        print(f"{item.decision_title} ({item.decision_id}) [{item.status}]{warning}")
        print(f"  cited at {item.source_title}:{item.start_line}-{item.end_line}")
        if item.rationale:
            print(f"  because: {item.rationale}")


def _cmd_export_adr(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            exported = export_adrs(session, args.output_dir, force=args.force)
    except (DecisionExportError, DecisionHealthError) as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    print(json.dumps({"exported": len(exported), "output_dir": str(args.output_dir)}))


def _cmd_import_adr(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        result = import_adrs(args.adr_dir, args.output_dir, force=args.force)
    except AdrImportError as exc:
        _decision_check_failed(exc.code)
    except OSError:
        _decision_check_failed("output_unavailable")
    document = {
        "imported": [
            {"source": item.source.name, "output": str(item.output), "status": item.status}
            for item in result.imported
        ],
        "skipped": [{"source": item.source.name, "reason": item.reason} for item in result.skipped],
        "next_step": f"proofline sync {args.output_dir}",
    }
    print(json.dumps(document, sort_keys=True))


def _cmd_hook(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.hook_action == "install":
            result = install_hook(args.repo, with_decisions=args.with_decisions, force=args.force)
        else:
            result = uninstall_hook(args.repo)
    except HookError as exc:
        _decision_check_failed(exc.code)
    except OSError:
        _decision_check_failed("hook_unwritable")
    print(json.dumps({"action": result.action, "path": str(result.path)}))


def _cmd_check_code_refs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        refs = scan_code_refs(args.paths)
        with SessionLocal() as session:
            findings = check_code_refs(session, refs)
    except (CodeRefError, DecisionHealthError) as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        document = {
            "valid": not findings,
            "reference_count": len(refs),
            "findings": [item.model_dump() for item in findings],
        }
        print(json.dumps(document, sort_keys=True))
    elif not findings:
        print(f"{len(refs)} decision reference(s) in code are current.")
    for item in findings if args.format == "text" else []:
        print(f"{item.path}:{item.line}: {item.reference} -> {item.problem}")
    if findings:
        raise SystemExit(1)


def _cmd_find_conflicts(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            candidates = find_conflict_candidates(session, min_similarity=args.min_similarity)
    except ValueError as exc:
        _decision_check_failed(str(exc))
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        print(json.dumps({"candidates": [c.model_dump() for c in candidates]}, sort_keys=True))
        return
    if not candidates:
        print("No conflict candidates.")
    for item in candidates:
        shared = ", ".join(item.shared_terms)
        print(f"{item.first_id} <-> {item.second_id}  ({item.similarity}; shared: {shared})")
    if candidates:
        print("Candidates only: a person decides whether they truly conflict.")


def _cmd_snapshot_health(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        initialize_database(engine)
        with SessionLocal() as session:
            snapshots = record_all_snapshots(session)
            session.commit()
            summary = [
                {"workspace_id": item.workspace_id, "approved": item.approved_count}
                | {"findings": item.finding_count}
                for item in snapshots
            ]
    except DecisionHealthError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    print(json.dumps({"snapshots": summary}, sort_keys=True))


def _cmd_health_trend(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            points = trend(session, limit=args.limit)
    except ValueError as exc:
        _decision_check_failed(str(exc))
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        print(json.dumps({"points": [p.model_dump() for p in points]}, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(points), end="")
    elif not points:
        print("No snapshots yet. Run `proofline snapshot-health` on a schedule.")
    else:
        for point in points:
            bar = "#" * min(40, round(point.stale_percent / 2.5))
            ratio = f"{point.findings:>4}/{point.approved:<4}"
            print(f"{point.taken_at[:10]}  {ratio} {point.stale_percent:>5}%  {bar}")


def _cmd_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(UTC).date()
    except ValueError:
        _decision_check_failed("as_of_invalid")
    try:
        with SessionLocal() as session:
            report = build_report(session, as_of=as_of, include_titles=not args.no_titles)
    except ValueError as exc:
        _decision_check_failed(str(exc))
    except (DecisionHealthError, OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    text = render_report_html(report) if args.format == "html" else render_report_markdown(report)
    if args.output is None:
        print(text, end="")
        return
    try:
        args.output.write_text(text, encoding="utf-8")
    except OSError:
        _decision_check_failed("output_unavailable")
    print(json.dumps({"output": str(args.output), "format": args.format}))


def _cmd_completion(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    print(render_completion(parser, args.shell), end="")


def _cmd_graph(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            graph = build_graph(
                session,
                include_titles=not args.no_titles,
                include_conflicts=not args.no_conflicts,
                include_isolated=args.include_isolated,
            )
    except (DecisionHealthError, OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    print(render_dot(graph) if args.format == "dot" else render_mermaid(graph), end="")


def _cmd_policy_schema(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    print(render_policy_schema(), end="")


def _cmd_notify(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(UTC).date()
    except ValueError:
        _decision_check_failed("as_of_invalid")
    try:
        with SessionLocal() as session:
            findings = check_expiry(session, as_of=as_of, warn_within_days=args.warn_within)
        result = send_expiry_notification(
            args.webhook,
            findings,
            as_of=as_of.isoformat(),
            style=args.style,
            always=args.always,
        )
    except NotifyError as exc:
        _decision_check_failed(exc.code)
    except ValueError as exc:
        _decision_check_failed(str(exc))
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    print(
        json.dumps(
            {
                "sent": result.sent,
                "overdue": result.overdue,
                "due_soon": result.due_soon,
                "status": result.status,
            },
            sort_keys=True,
        )
    )


def _cmd_watch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.interval <= 0:
        _decision_check_failed("interval_invalid")
    try:
        initialize_database()
        print(f"watching {args.path} every {args.interval:g}s; Ctrl-C to stop", flush=True)
        watch_folder(
            SessionLocal,
            args.path,
            uri_root=args.uri_root,
            interval=args.interval,
            max_cycles=args.max_cycles,
            emit=lambda line: print(line, flush=True),
        )
    except KeyboardInterrupt:
        print("stopped")
    except WorkspaceSyncError as exc:
        raise SystemExit(f"watch failed: {exc.code}") from exc
    except (OSError, SQLAlchemyError) as exc:
        raise SystemExit("watch failed: database_unavailable") from exc


def _cmd_check_enforcement(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            findings = check_enforcement(session, args.root)
    except EnforceError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        document = {
            "valid": not findings,
            "findings": [item.content_free_model_dump() for item in findings],
        }
        print(json.dumps(document, sort_keys=True))
    else:
        for item in findings:
            where = item.path if item.line is None else f"{item.path}:{item.line}"
            print(
                f"decision {item.decision_id[:8]} rule {item.rule_index} {item.problem}: ", end=""
            )
            print(f"{item.rule}" + (f" (at {where})" if where else ""))
        if not findings:
            print("All enforced decisions hold.")
    if findings:
        raise SystemExit(1)


def _cmd_asof(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        moment = parse_as_of(args.moment)
        with SessionLocal() as session:
            answers = decisions_as_of(session, moment, question=args.question)
    except AsOfError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        key = "content_free_model_dump" if args.no_titles else "model_dump"
        print(
            json.dumps(
                {"as_of": moment.isoformat(), "decisions": [getattr(a, key)() for a in answers]},
                sort_keys=True,
            )
        )
        return
    print(f"Decisions in force at {moment.isoformat(timespec='seconds')} UTC:")
    if not answers:
        print("  none")
    for item in answers:
        label = item.decision_id[:8] if args.no_titles else item.decision_title
        flag = "" if item.health == "current" else f"  WARNING: citation {item.health}"
        versions = f"v{item.cited_version_number}->v{item.version_in_force}"
        print(f"  {label} [{item.status}] {versions}{flag}")


def _cmd_code_context(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.diff_file is not None:
            diff = (
                sys.stdin.read()
                if str(args.diff_file) == "-"
                else args.diff_file.read_text(encoding="utf-8")
            )
        elif args.base:
            diff = git_diff(args.root, args.base)
        else:
            _decision_check_failed("diff_source_required")
        with SessionLocal() as session:
            items = build_context(session, args.root, parse_unified_diff(diff), radius=args.radius)
    except ContextError as exc:
        _decision_check_failed(exc.code)
    except (OSError, UnicodeError, SQLAlchemyError):
        _decision_check_failed("context_unavailable")
    attention = [item for item in items if item.needs_attention]
    if args.format == "json":
        key = "model_dump" if args.include_titles else "content_free_model_dump"
        print(
            json.dumps(
                {"items": [getattr(i, key)() for i in items], "attention": len(attention)},
                sort_keys=True,
            )
        )
    else:
        print(render_context_markdown(items, include_titles=args.include_titles), end="")
    if args.fail_on_attention and attention:
        raise SystemExit(1)


def _cmd_ledger(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        if args.ledger_action == "verify":
            entries = read_ledger(args.file)
            print(json.dumps({"valid": True, "entries": len(entries)}))
            return
        with SessionLocal() as session:
            if args.ledger_action == "append":
                entry = append_entry(session, args.file)
                print(json.dumps(entry.model_dump(), sort_keys=True))
                return
            base = ledger_at_ref(args.root, args.base, args.file)
            result = compare_with_base(session, base)
    except LedgerError as exc:
        _decision_check_failed(exc.code)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        print(json.dumps(result.model_dump(), sort_keys=True))
    else:
        print(render_comparison(result), end="")


def _cmd_doctor(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            checks = run_doctor(engine, session, policy_path=args.policy)
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    failed = [item for item in checks if item.status == "fail"]
    if args.format == "json":
        print(
            json.dumps(
                {"ok": not failed, "checks": [item.model_dump() for item in checks]},
                sort_keys=True,
            )
        )
    else:
        for item in checks:
            print(f"[{item.status:<4}] {item.name}: {item.detail}")
    if failed:
        raise SystemExit(1)


def _cmd_suggest_links(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        with SessionLocal() as session:
            suggestions = suggest_links(
                session, args.decision_id, limit=args.limit, min_similarity=args.min_similarity
            )
    except ValueError as exc:
        _decision_check_failed(str(exc))
    except (OSError, SQLAlchemyError):
        _decision_check_failed("database_unavailable")
    if args.format == "json":
        print(json.dumps({"suggestions": [s.model_dump() for s in suggestions]}, sort_keys=True))
        return
    if not suggestions:
        print("No related decisions found.")
        return
    for item in suggestions:
        age = "older" if item.other_is_older else "newer"
        print(
            f"{item.other_id}  {item.similarity}  ({age}; shared: {', '.join(item.shared_terms)})"
        )
    print("Suggestions only. Create a relation in Studio or POST /decision-relations.")


def _cmd_demo(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        result = run_stale_decision_demo(args.output_dir, force=args.force)
    except EvidencePackageError as exc:
        raise SystemExit(f"demo failed: {exc.code}") from exc
    finding = cast(Any, result["finding"])
    verification = cast(dict[str, Any], result["verification"])
    print("1. ADR-007 approved with exact requirement evidence.")
    print("2. requirement.md updated to a new immutable version.")
    print("3. Proofline compared the approved citation with the current source.")
    print()
    print("Decision requires review")
    print(f"{finding.locator} changed after this decision was approved.")
    print("Accepted · review required")
    print()
    print(f"Offline package: {result['package']}")
    print(f"Readable report: {result['report']}")
    print(f"Review receipt: {result['review_receipt']}")
    print(f"Verification: valid · root {verification['root_hash']}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="proofline")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="Run the local API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    serve.add_argument(
        "--data-dir",
        type=Path,
        help="Store the database and local configuration in this directory",
    )
    serve.add_argument(
        "--ready-file",
        type=Path,
        help="Atomically publish readiness metadata and remove it on shutdown",
    )
    serve.add_argument(
        "--shutdown-file",
        type=Path,
        help="Gracefully stop when this private lifecycle file is created",
    )
    web_mode = serve.add_mutually_exclusive_group()
    web_mode.add_argument(
        "--web-dir",
        type=Path,
        help="Serve this built web archive instead of the bundled UI",
    )
    web_mode.add_argument("--no-web", action="store_true", help="Run the API without the web UI")
    serve.add_argument(
        "--log-level", choices=("critical", "error", "warning", "info"), default="info"
    )
    launch = subcommands.add_parser(
        "launch", help="Launch the experimental local app with platform-owned state"
    )
    launch.add_argument("--port", default=0, type=int)
    launch.add_argument(
        "--data-dir",
        type=Path,
        help="Override the operating-system application data directory",
    )
    launch.add_argument(
        "--no-browser",
        action="store_true",
        help="Start without opening the local UI in the default browser",
    )
    launch.add_argument(
        "--log-level", choices=("critical", "error", "warning", "info"), default="warning"
    )
    subcommands.add_parser("seed", help="Index the bundled example decision")
    mcp = subcommands.add_parser(
        "mcp",
        help="Serve read-only decision checks to a local MCP client over stdio",
    )
    mcp.add_argument(
        "--include-titles",
        action="store_true",
        help="Include decision titles in tool results (they reach the client's model)",
    )
    mcp.add_argument(
        "--include-excerpts",
        action="store_true",
        help="Include short evidence excerpts in search results (they reach the client's model)",
    )
    sync = subcommands.add_parser(
        "sync",
        help="Index a document folder headlessly (for CI) under a stable file URI root",
    )
    sync.add_argument("path", type=Path)
    sync.add_argument(
        "--uri-root",
        help="file:// URI the folder had when decisions were approved; defaults to its real path",
    )
    sync.add_argument("--format", choices=("text", "json"), default="text")
    watch = subcommands.add_parser(
        "watch", help="Re-sync a folder when documents change and report newly stale decisions"
    )
    watch.add_argument("path", type=Path)
    watch.add_argument("--uri-root")
    watch.add_argument("--interval", type=float, default=2.0, metavar="SECONDS")
    watch.add_argument("--max-cycles", type=int, help=argparse.SUPPRESS)
    evaluate = subcommands.add_parser("eval", help="Run a versioned retrieval evaluation")
    evaluate.add_argument("--dataset", type=Path, required=True)
    evaluate.add_argument("--k", type=int, default=10)
    evaluate.add_argument("--min-recall", type=unit_interval, default=0)
    evaluate.add_argument("--min-ndcg", type=unit_interval, default=0)
    evaluate.add_argument("--min-expected-empty-accuracy", type=unit_interval, default=0)
    grounded = subcommands.add_parser(
        "eval-grounded", help="Run a versioned credential-free grounded-QA evaluation"
    )
    grounded.add_argument("--dataset", type=Path, required=True)
    grounded.add_argument("--limit", type=int, choices=range(1, 13), default=8)
    grounded.add_argument("--min-citation-resolution", type=unit_interval, default=0)
    grounded.add_argument("--min-citation-precision", type=unit_interval, default=0)
    grounded.add_argument("--min-grounded-success", type=unit_interval, default=0)
    grounded.add_argument("--min-status-accuracy", type=unit_interval, default=0)
    extraction = subcommands.add_parser(
        "eval-extraction", help="Run a versioned deterministic extraction evaluation"
    )
    extraction.add_argument("--dataset", type=Path, required=True)
    extraction.add_argument("--min-precision", type=unit_interval, default=0)
    extraction.add_argument("--min-recall", type=unit_interval, default=0)
    extraction.add_argument("--min-f1", type=unit_interval, default=0)
    extraction.add_argument("--min-evidence-resolution", type=unit_interval, default=0)
    extraction.add_argument("--min-expected-evidence-accuracy", type=unit_interval, default=0)
    extraction.add_argument("--min-negative-source-accuracy", type=unit_interval, default=0)
    real_model_preflight = subcommands.add_parser(
        "eval-real-model-preflight",
        help="Validate a versioned local/remote real-model comparison plan",
    )
    real_model_preflight.add_argument("--plan", type=Path, required=True)
    real_model_preflight.add_argument("--output", type=Path, required=True)
    real_model_preflight.add_argument("--force", action="store_true")
    real_model_preflight.add_argument(
        "--allow-mock",
        action="store_true",
        help="Explicitly allow scripted mock preflight; never real-model evidence",
    )
    real_model = subcommands.add_parser(
        "eval-real-model",
        help="Run a preflighted local/remote model comparison through production paths",
    )
    real_model.add_argument("--plan", type=Path, required=True)
    real_model.add_argument("--output", type=Path, required=True)
    real_model.add_argument("--force", action="store_true")
    real_model.add_argument(
        "--allow-mock",
        action="store_true",
        help="Explicitly allow scripted mock integration; never real-model evidence",
    )
    benchmark = subcommands.add_parser(
        "benchmark", help="Measure local SQLite FTS5 lexical search latency"
    )
    benchmark.add_argument("--sources", type=int, default=1_000)
    benchmark.add_argument("--queries", type=int, default=100)
    benchmark.add_argument("--limit", type=int, default=10)
    subcommands.add_parser("embed", help="Incrementally embed current source chunks")
    export = subcommands.add_parser("export", help="Write a verified portable JSON snapshot")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--force", action="store_true")
    verify_export = subcommands.add_parser("verify-export", help="Verify a portable JSON snapshot")
    verify_export.add_argument("path", type=Path)
    package = subcommands.add_parser(
        "export-package", help="Write a verifiable evidence package for one memory artifact"
    )
    package.add_argument("artifact_id")
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--force", action="store_true")
    package.add_argument(
        "--html-report",
        type=Path,
        help="Also write a self-contained, human-readable HTML projection",
    )
    verify_package = subcommands.add_parser(
        "verify-package", help="Verify a Decision Evidence Package without database access"
    )
    verify_package.add_argument("path", type=Path)
    review_receipt = subcommands.add_parser(
        "export-review-receipt",
        help="Bind one decision review to a verified evidence package",
    )
    review_receipt.add_argument("review_id")
    review_receipt.add_argument("--package", type=Path, required=True)
    review_receipt.add_argument("--output", type=Path, required=True)
    verify_review_receipt = subcommands.add_parser(
        "verify-review-receipt",
        help="Verify a decision review receipt without database access",
    )
    verify_review_receipt.add_argument("path", type=Path)
    generate_attestation_key = subcommands.add_parser(
        "generate-attestation-key",
        help="Generate a local Ed25519 keypair for signed evidence attestations",
    )
    generate_attestation_key.add_argument("--private-key", type=Path, required=True)
    generate_attestation_key.add_argument("--public-key", type=Path, required=True)
    generate_attestation_key.add_argument("--force", action="store_true")
    attest = subcommands.add_parser(
        "attest",
        help="Sign a verified evidence package and optional review receipt",
    )
    attest.add_argument("--package", type=Path, required=True)
    attest.add_argument("--review-receipt", type=Path)
    attest.add_argument("--private-key", type=Path, required=True)
    attest.add_argument("--issued-at")
    attest.add_argument("--output", type=Path, required=True)
    attest.add_argument("--force", action="store_true")
    verify_attestation = subcommands.add_parser(
        "verify-attestation",
        help="Verify a signed attestation against trusted public key and exact subjects",
    )
    verify_attestation.add_argument("path", type=Path)
    verify_attestation.add_argument("--public-key", type=Path, required=True)
    verify_attestation.add_argument("--package", type=Path, required=True)
    verify_attestation.add_argument("--review-receipt", type=Path)
    verify_attestation.add_argument(
        "--revocations",
        type=Path,
        help="JSON list of revoked key ids (proofline-key-revocations-v1) you trust",
    )
    explain = subcommands.add_parser(
        "explain", help="Explain one memory artifact and its exact provenance"
    )
    explain.add_argument("artifact_id")
    diff = subcommands.add_parser("diff", help="Compare two verified Decision Evidence Packages")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    import_export = subcommands.add_parser(
        "import", help="Restore or explicitly merge a verified portable JSON snapshot"
    )
    import_export.add_argument("path", type=Path)
    import_export.add_argument("--preview-merge", action="store_true")
    import_export.add_argument("--merge", action="store_true")
    import_export.add_argument("--preview-sha256")
    backup = subcommands.add_parser("backup", help="Create a complete local SQLite backup")
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--force", action="store_true")
    verify_backup = subcommands.add_parser("verify-backup", help="Verify a SQLite backup")
    verify_backup.add_argument("path", type=Path)
    restore_backup = subcommands.add_parser(
        "restore-backup",
        help="Atomically restore a verified SQLite backup while preserving rollback data",
    )
    restore_backup.add_argument("path", type=Path)
    restore_backup.add_argument("--rollback-output", type=Path)
    subcommands.add_parser(
        "verify-integrity", help="Verify live SQLite provenance without changing it"
    )
    blame_parser = subcommands.add_parser(
        "blame", help="Show the approved decisions anchored at a file or file:line"
    )
    blame_parser.add_argument("target", help="Source path, URI or title, optionally with :LINE")
    blame_parser.add_argument("--line", type=int)
    blame_parser.add_argument("--format", choices=("text", "json"), default="text")
    rebind = subcommands.add_parser(
        "rebind", help="Preview or apply re-anchoring of a stale decision to its candidate text"
    )
    rebind.add_argument("review_id", nargs="?", help="Omit to list pending reviews")
    rebind.add_argument("--apply", action="store_true")
    rebind.add_argument("--reason")
    rebind.add_argument("--format", choices=("text", "json"), default="text")
    expiry = subcommands.add_parser(
        "check-expiry", help="Fail when an approved decision is past its Review by date"
    )
    expiry.add_argument("--as-of", help="YYYY-MM-DD, default today (UTC)")
    expiry.add_argument("--warn-within", type=int, default=0, help="Also list decisions due soon")
    expiry.add_argument("--format", choices=("text", "json"), default="text")
    why_parser = subcommands.add_parser(
        "why", help="Find the approved decisions that answer a question, with citations"
    )
    why_parser.add_argument("question")
    why_parser.add_argument("--limit", type=int, default=5)
    why_parser.add_argument("--format", choices=("text", "json"), default="text")
    export_adr = subcommands.add_parser(
        "export-adr", help="Write one Markdown ADR per approved decision"
    )
    export_adr.add_argument("--output-dir", type=Path, required=True)
    export_adr.add_argument("--force", action="store_true")
    import_adr = subcommands.add_parser(
        "import-adr",
        help="Convert existing Markdown ADRs into files Proofline can index (then run sync)",
    )
    import_adr.add_argument("adr_dir", type=Path)
    import_adr.add_argument("--output-dir", type=Path, required=True)
    import_adr.add_argument("--force", action="store_true")
    hook = subcommands.add_parser(
        "hook", help="Install or remove a git pre-commit hook that runs the decision checks"
    )
    hook_actions = hook.add_subparsers(dest="hook_action", required=True)
    hook_install = hook_actions.add_parser("install", help="Write .git/hooks/pre-commit")
    hook_install.add_argument("--repo", type=Path, default=Path("."))
    hook_install.add_argument(
        "--with-decisions",
        action="store_true",
        help="Also run `sync` and `check-decisions` (slower; indexes the working tree)",
    )
    hook_install.add_argument("--force", action="store_true")
    hook_uninstall = hook_actions.add_parser("uninstall", help="Remove a hook Proofline wrote")
    hook_uninstall.add_argument("--repo", type=Path, default=Path("."))
    report = subcommands.add_parser(
        "report", help="Write a shareable health report (trend, stale, reviews due, conflicts)"
    )
    report.add_argument("--format", choices=("html", "markdown"), default="html")
    report.add_argument("--output", type=Path)
    report.add_argument("--as-of")
    report.add_argument(
        "--no-titles", action="store_true", help="Withhold decision titles and source names"
    )
    completion = subcommands.add_parser(
        "completion", help="Print a shell completion script (eval it or save it)"
    )
    completion.add_argument("shell", choices=("bash", "zsh", "fish"))
    graph = subcommands.add_parser(
        "graph", help="Print the decision relation graph as Mermaid or Graphviz DOT"
    )
    graph.add_argument("--format", choices=("mermaid", "dot"), default="mermaid")
    graph.add_argument("--no-titles", action="store_true", help="Label nodes with short ids")
    graph.add_argument("--no-conflicts", action="store_true", help="Omit possible-conflict edges")
    graph.add_argument("--include-isolated", action="store_true", help="Also draw unlinked nodes")
    subcommands.add_parser(
        "policy-schema", help="Print the JSON Schema for proofline.toml (editor validation)"
    )
    notify = subcommands.add_parser(
        "notify", help="POST a content-free review-expiry alert to a webhook (id and counts only)"
    )
    notify.add_argument("--webhook", required=True, help="https URL (http only for loopback)")
    notify.add_argument("--style", choices=("generic", "slack"), default="generic")
    notify.add_argument("--as-of")
    notify.add_argument("--warn-within", type=int, default=7, metavar="DAYS")
    notify.add_argument("--always", action="store_true", help="Send even when nothing is due")
    enforcement = subcommands.add_parser(
        "check-enforcement",
        help="Fail when code violates an `Enforce:` rule of an approved decision",
    )
    enforcement.add_argument("--root", type=Path, default=Path("."))
    enforcement.add_argument("--format", choices=("text", "json"), default="text")
    asof = subcommands.add_parser(
        "asof", help="Show which approved decisions were in force at a past date or time (UTC)"
    )
    asof.add_argument("moment", help="YYYY-MM-DD (end of that day) or an ISO datetime")
    asof.add_argument("question", nargs="?", help="Only decisions matching these words")
    asof.add_argument("--format", choices=("text", "json"), default="text")
    asof.add_argument("--no-titles", action="store_true")
    context = subcommands.add_parser(
        "code-context",
        help="List approved decisions touched by a code change (code refs, edited docs, rules)",
    )
    context.add_argument("--base", help="Git ref to diff against (uses `<base>...HEAD`)")
    context.add_argument("--diff-file", type=Path, help="Unified diff (-U0) file, or - for stdin")
    context.add_argument("--root", type=Path, default=Path("."))
    context.add_argument("--radius", type=int, default=10, help="Lines around a change to scan")
    context.add_argument("--format", choices=("markdown", "json"), default="markdown")
    context.add_argument("--include-titles", action="store_true")
    context.add_argument(
        "--fail-on-attention",
        action="store_true",
        help="Exit 1 when a touched decision is stale or a rule is violated",
    )
    ledger = subcommands.add_parser(
        "ledger", help="Keep a hash-chained, content-free health history in the repository"
    )
    ledger_actions = ledger.add_subparsers(dest="ledger_action", required=True)
    for name, text in (
        ("append", "Append the current health to the ledger file"),
        ("verify", "Verify the ledger's hash chain"),
        ("compare", "Compare current health with the ledger committed at a git ref"),
    ):
        action = ledger_actions.add_parser(name, help=text)
        action.add_argument("--file", type=Path, default=DEFAULT_LEDGER)
        if name == "compare":
            action.add_argument("--base", required=True, help="Git ref, e.g. origin/main")
            action.add_argument("--root", type=Path, default=Path("."))
            action.add_argument("--format", choices=("markdown", "json"), default="markdown")
    code_refs = subcommands.add_parser(
        "check-code-refs",
        help="Fail when code marked `proofline-decision: <id>` points at a stale decision",
    )
    code_refs.add_argument("paths", nargs="+", type=Path)
    code_refs.add_argument("--format", choices=("text", "json"), default="text")
    conflicts = subcommands.add_parser(
        "find-conflicts", help="List approved decisions that may contradict each other"
    )
    conflicts.add_argument("--min-similarity", type=float, default=0.5)
    conflicts.add_argument("--format", choices=("text", "json"), default="text")
    subcommands.add_parser(
        "snapshot-health", help="Record counts of stale decisions now (run on a schedule)"
    )
    health_trend = subcommands.add_parser(
        "health-trend", help="Show how the share of stale decisions changed over time"
    )
    health_trend.add_argument("--limit", type=int, default=30)
    health_trend.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    doctor = subcommands.add_parser(
        "doctor", help="Read-only overview: migrations, integrity, policy, reviews, snapshots"
    )
    doctor.add_argument("--policy", type=Path)
    doctor.add_argument("--format", choices=("text", "json"), default="text")
    suggest = subcommands.add_parser(
        "suggest-links", help="List approved decisions a decision probably relates to"
    )
    suggest.add_argument("decision_id", help="Decision id or an 8+ character prefix")
    suggest.add_argument("--limit", type=int, default=5)
    suggest.add_argument("--min-similarity", type=float, default=0.2)
    suggest.add_argument("--format", choices=("text", "json"), default="text")
    check_decisions = subcommands.add_parser(
        "check-decisions",
        help="Read-only CI check that approved citations still resolve in current sources",
    )
    check_decisions.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    check_decisions.add_argument("--policy", type=Path)
    check_decisions.add_argument(
        "--explain", action="store_true", help="Print the fix command for each finding"
    )
    check_decisions.add_argument("--output", type=Path)
    refresh_reviews = subcommands.add_parser(
        "refresh-reviews",
        help="Persist the current deterministic decision review ledger",
    )
    refresh_reviews.add_argument("--policy", type=Path)
    check_impacts = subcommands.add_parser(
        "check-impacts",
        help="Read-only CI check for transitive impact through explicit dependencies",
    )
    check_impacts.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    check_impacts.add_argument("--as-of")
    check_impacts.add_argument("--output", type=Path)
    demo = subcommands.add_parser("demo", help="Run a self-contained product story")
    demo_commands = demo.add_subparsers(dest="demo_name", required=True)
    stale_demo = demo_commands.add_parser(
        "stale-decision", help="Show an ADR becoming stale after its requirement changes"
    )
    stale_demo.add_argument("--output-dir", type=Path, default=Path(DEMO_DIRECTORY))
    stale_demo.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    handlers = {
        "serve": _cmd_serve,
        "launch": _cmd_launch,
        "seed": _cmd_seed,
        "mcp": _cmd_mcp,
        "sync": _cmd_sync,
        "watch": _cmd_watch,
        "eval": _cmd_eval,
        "eval-grounded": _cmd_eval_grounded,
        "eval-extraction": _cmd_eval_extraction,
        "eval-real-model-preflight": _cmd_eval_real_model_preflight,
        "eval-real-model": _cmd_eval_real_model,
        "benchmark": _cmd_benchmark,
        "embed": _cmd_embed,
        "export": _cmd_export,
        "verify-export": _cmd_verify_export,
        "export-package": _cmd_export_package,
        "verify-package": _cmd_verify_package,
        "export-review-receipt": _cmd_export_review_receipt,
        "verify-review-receipt": _cmd_verify_review_receipt,
        "generate-attestation-key": _cmd_generate_attestation_key,
        "attest": _cmd_attest,
        "verify-attestation": _cmd_verify_attestation,
        "explain": _cmd_explain,
        "diff": _cmd_diff,
        "import": _cmd_import,
        "backup": _cmd_backup,
        "verify-backup": _cmd_verify_backup,
        "restore-backup": _cmd_restore_backup,
        "verify-integrity": _cmd_verify_integrity,
        "blame": _cmd_blame,
        "suggest-links": _cmd_suggest_links,
        "doctor": _cmd_doctor,
        "snapshot-health": _cmd_snapshot_health,
        "health-trend": _cmd_health_trend,
        "export-adr": _cmd_export_adr,
        "import-adr": _cmd_import_adr,
        "hook": _cmd_hook,
        "report": _cmd_report,
        "completion": _cmd_completion,
        "graph": _cmd_graph,
        "policy-schema": _cmd_policy_schema,
        "notify": _cmd_notify,
        "check-enforcement": _cmd_check_enforcement,
        "asof": _cmd_asof,
        "code-context": _cmd_code_context,
        "ledger": _cmd_ledger,
        "check-code-refs": _cmd_check_code_refs,
        "find-conflicts": _cmd_find_conflicts,
        "why": _cmd_why,
        "check-expiry": _cmd_check_expiry,
        "rebind": _cmd_rebind,
        "check-decisions": _cmd_check_decisions,
        "check-impacts": _cmd_check_impacts,
        "refresh-reviews": _cmd_refresh_reviews,
    }
    handler = handlers.get(args.command)
    if handler is not None:
        handler(args, parser)
    elif args.command == "demo" and args.demo_name == "stale-decision":
        _cmd_demo(args, parser)


if __name__ == "__main__":
    main()
