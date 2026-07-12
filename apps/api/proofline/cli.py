from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn

from .config import get_settings
from .database import SessionLocal, initialize_database
from .embeddings import index_current_embeddings
from .evaluation import evaluate_dataset
from .ingestion import ingest_source
from .model_gateway import ProviderConfigurationError, build_embedding_provider
from .schemas import SourceCreate


def seed_demo() -> None:
    initialize_database()
    demo = Path(__file__).resolve().parents[3] / "examples" / "architecture-decision.md"
    with SessionLocal() as session:
        source, created = ingest_source(
            session,
            SourceCreate(title=demo.name, content=demo.read_text(), uri=str(demo)),
        )
    print(f"{'Indexed' if created else 'Already indexed'}: {source.title} ({source.id})")


def main() -> None:
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
    subcommands.add_parser("embed", help="Incrementally embed current source chunks")
    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run("proofline.main:app", host=args.host, port=args.port, reload=False)
    elif args.command == "seed":
        seed_demo()
    elif args.command == "eval":
        report = evaluate_dataset(args.dataset, args.k)
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        if report.recall_at_k < args.min_recall or report.ndcg_at_k < args.min_ndcg:
            raise SystemExit(1)
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


if __name__ == "__main__":
    main()
