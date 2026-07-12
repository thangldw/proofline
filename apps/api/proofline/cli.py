from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .database import SessionLocal, initialize_database
from .ingestion import ingest_source
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
    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run("proofline.main:app", host=args.host, port=args.port, reload=False)
    elif args.command == "seed":
        seed_demo()


if __name__ == "__main__":
    main()
