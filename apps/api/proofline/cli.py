from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn

from .config import get_settings
from .database import SessionLocal, initialize_database
from .embeddings import index_current_embeddings
from .evaluation import (
    benchmark_lexical_search,
    evaluate_dataset,
    evaluate_grounded_dataset,
    grounded_report_meets_thresholds,
)
from .ingestion import ingest_source
from .model_gateway import ProviderConfigurationError, build_embedding_provider
from .portability import (
    PortabilityError,
    atomic_write_export,
    build_portable_export,
    load_and_verify_export,
)
from .schemas import SourceCreate


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
    demo = Path(__file__).resolve().parents[3] / "examples" / "architecture-decision.md"
    with SessionLocal() as session:
        source, created = ingest_source(
            session,
            SourceCreate(title=demo.name, content=demo.read_text(), uri=str(demo)),
        )
    print(f"{'Indexed' if created else 'Already indexed'}: {source.title} ({source.id})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="proofline")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="Run the local API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    subcommands.add_parser("seed", help="Index the bundled example decision")
    evaluate = subcommands.add_parser("eval", help="Run a versioned retrieval evaluation")
    evaluate.add_argument("--dataset", type=Path, required=True)
    evaluate.add_argument("--k", type=int, default=10)
    evaluate.add_argument("--min-recall", type=float, default=0)
    evaluate.add_argument("--min-ndcg", type=float, default=0)
    grounded = subcommands.add_parser(
        "eval-grounded", help="Run a versioned credential-free grounded-QA evaluation"
    )
    grounded.add_argument("--dataset", type=Path, required=True)
    grounded.add_argument("--limit", type=int, choices=range(1, 13), default=8)
    grounded.add_argument("--min-citation-resolution", type=unit_interval, default=0)
    grounded.add_argument("--min-citation-precision", type=unit_interval, default=0)
    grounded.add_argument("--min-grounded-success", type=unit_interval, default=0)
    grounded.add_argument("--min-status-accuracy", type=unit_interval, default=0)
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
    args = parser.parse_args(argv)
    if args.command == "serve":
        uvicorn.run("proofline.main:app", host=args.host, port=args.port, reload=False)
    elif args.command == "seed":
        seed_demo()
    elif args.command == "eval":
        report = evaluate_dataset(args.dataset, args.k)
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        if report.recall_at_k < args.min_recall or report.ndcg_at_k < args.min_ndcg:
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


if __name__ == "__main__":
    main()
