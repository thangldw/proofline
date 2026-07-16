from __future__ import annotations

import argparse
import json
import os
from importlib.resources import files
from pathlib import Path

from . import __version__
from .backup import (
    BackupError,
    create_sqlite_backup,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from .config import get_settings
from .database import SessionLocal, engine, initialize_database
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
    atomic_write_package,
    build_decision_package,
    diff_decision_packages,
    explain_decision_package,
    load_and_verify_package,
)
from .ingestion import ingest_source
from .integrity import IntegrityVerificationError, verify_live_database
from .model_gateway import ProviderConfigurationError, build_embedding_provider
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
from .schemas import SourceCreate
from .server import run_server


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
    verify_package = subcommands.add_parser(
        "verify-package", help="Verify a Decision Evidence Package without database access"
    )
    verify_package.add_argument("path", type=Path)
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
    args = parser.parse_args(argv)
    if args.command == "serve":
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
    elif args.command == "launch":
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
    elif args.command == "seed":
        seed_demo()
    elif args.command == "eval":
        report = evaluate_dataset(args.dataset, args.k)
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        if (
            report.recall_at_k < args.min_recall
            or report.ndcg_at_k < args.min_ndcg
            or report.expected_empty_accuracy < args.min_expected_empty_accuracy
        ):
            raise SystemExit(1)
    elif args.command == "eval-grounded":
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
    elif args.command == "eval-extraction":
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
    elif args.command == "eval-real-model-preflight":
        try:
            receipt = preflight_real_model_plan(args.plan, allow_mock=args.allow_mock)
            write_preflight_receipt(args.output, receipt, force=args.force)
        except (FileExistsError, OSError, ValueError) as exc:
            raise SystemExit(f"real-model preflight failed: {type(exc).__name__}") from exc
        print(receipt.model_dump_json(indent=2))
        if receipt.status != "ready":
            raise SystemExit(1)
    elif args.command == "eval-real-model":
        try:
            receipt = run_real_model_comparison(args.plan, allow_mock=args.allow_mock)
            write_comparison_receipt(args.output, receipt, force=args.force)
        except (FileExistsError, OSError, ValueError) as exc:
            raise SystemExit(f"real-model comparison failed: {type(exc).__name__}") from exc
        print(receipt.model_dump_json(indent=2))
        if receipt.status != "completed":
            raise SystemExit(1)
    elif args.command == "benchmark":
        try:
            report = benchmark_lexical_search(args.sources, args.queries, args.limit)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    elif args.command == "embed":
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
    elif args.command == "export":
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
    elif args.command == "verify-export":
        try:
            counts = load_and_verify_export(args.path)
        except PortabilityError as exc:
            raise SystemExit(f"export verification failed: {exc.code}") from exc
        print(json.dumps({"valid": True, "counts": counts}, sort_keys=True))
    elif args.command == "export-package":
        initialize_database()
        try:
            with SessionLocal() as session:
                document = build_decision_package(session, args.artifact_id)
            atomic_write_package(args.output, document, force=args.force)
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
    elif args.command == "verify-package":
        try:
            _document, report = load_and_verify_package(args.path)
        except EvidencePackageError as exc:
            raise SystemExit(f"package verification failed: {exc.code}") from exc
        print(json.dumps(report, sort_keys=True))
    elif args.command == "explain":
        initialize_database()
        try:
            with SessionLocal() as session:
                document = build_decision_package(session, args.artifact_id)
            report = explain_decision_package(document)
        except EvidencePackageError as exc:
            raise SystemExit(f"artifact explanation failed: {exc.code}") from exc
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.command == "diff":
        try:
            before, _before_report = load_and_verify_package(args.before)
            after, _after_report = load_and_verify_package(args.after)
            report = diff_decision_packages(before, after)
        except EvidencePackageError as exc:
            raise SystemExit(f"package diff failed: {exc.code}") from exc
        print(json.dumps(report, sort_keys=True))
    elif args.command == "import":
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
    elif args.command == "backup":
        if engine.dialect.name != "sqlite":
            raise SystemExit("backup failed: sqlite_required")
        initialize_database()
        try:
            report = create_sqlite_backup(engine, args.output, force=args.force)
        except BackupError as exc:
            raise SystemExit(f"backup failed: {exc.code}") from exc
        print(json.dumps({"valid": True, **report}, sort_keys=True))
    elif args.command == "verify-backup":
        try:
            report = verify_sqlite_backup(args.path)
        except BackupError as exc:
            raise SystemExit(f"backup verification failed: {exc.code}") from exc
        print(json.dumps({"valid": True, **report}, sort_keys=True))
    elif args.command == "restore-backup":
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
    elif args.command == "verify-integrity":
        try:
            report = verify_live_database(engine)
        except IntegrityVerificationError as exc:
            raise SystemExit(f"integrity verification failed: {exc.code}") from exc
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
