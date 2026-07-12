# Proofline

**Evidence-backed engineering memory.**

Proofline is an open-source system that helps engineering teams recover why
software was built the way it was. It connects source material such as ADRs,
design notes, issues, pull requests, commits, and meeting transcripts to
searchable evidence. The long-term product models decisions, assumptions,
alternatives, and supersession explicitly instead of treating a knowledge base
as an unstructured collection of vector chunks.

> Project status: pre-alpha. The first runnable vertical slice is implemented,
> but it is not ready for production data.

## Product principles

- **Evidence first:** derived information must remain traceable to an exact
  source span.
- **Local first:** a useful single-user deployment must run on one machine.
- **Inspectable memory:** users can see, correct, reject, and delete derived
  knowledge.
- **Model agnostic:** AI providers are replaceable; source data is not tied to
  a model vendor.
- **Engineering native:** ingest existing engineering artifacts instead of
  requiring a new editor.
- **Reliable before magical:** indexing state, failures, and retrieval choices
  must be observable.

## First vertical slice

The initial executable slice deliberately excludes LLM generation:

1. ingest a Markdown source;
2. preserve its content hash and source locations;
3. preserve immutable versions when the same source URI changes;
4. split it into deterministic, addressable evidence chunks;
5. extract explicitly marked English/Vietnamese decisions without an AI model;
6. index the current version locally with SQLite FTS5;
7. search, browse decisions, and inspect exact historical evidence in the web UI.

This establishes the evidence contract that decision extraction, hybrid
retrieval, and grounded answers will build on.

Every ingestion request also creates an inspectable job record. Terminal failures retain a safe
error code and stage without copying source content into diagnostic fields.

Decisions can be accepted, rejected, corrected, or marked obsolete. Every change records a
before/after audit event while retaining the original source evidence; complete source deletion
also removes content-bearing audit records.

The answer endpoint builds a bounded lexical evidence pack and lets the model reference only
server-issued evidence IDs. Proofline resolves citations itself and verifies every quoted span
against the immutable source version; unknown, missing, or corrupted evidence fails closed.

## Repository layout

```text
proofline/
├── apps/api/           # FastAPI, SQLite persistence, ingestion, retrieval
├── apps/web/           # React/Vite evidence console
├── docs/               # Product, architecture, ADRs, and roadmap
├── deploy/             # Local container deployment
└── .github/workflows/  # Automated quality gates
```

## Development

Prerequisites: Python 3.11+, Node.js 20 LTS or 22+, and npm. Then run:

```bash
make setup
make seed
make dev-api
# In a second terminal:
make dev-web
```

Open http://localhost:5173. The local API docs are at
http://localhost:8000/docs. Common quality commands are:

```bash
make test
make check
make eval
```

AI is disabled by default. A local OpenAI-compatible endpoint can be configured with
`PROOFLINE_AI_PROVIDER=openai_compatible`, `PROOFLINE_AI_BASE_URL`, and
`PROOFLINE_AI_MODEL`. Sending content to a non-loopback endpoint additionally requires the
explicit `PROOFLINE_ALLOW_REMOTE_AI=true` setting. API keys are read from
`PROOFLINE_AI_API_KEY` and are never persisted in model-run records.

Embeddings use a separate model configuration: `PROOFLINE_EMBEDDING_PROVIDER`,
`PROOFLINE_EMBEDDING_BASE_URL`, `PROOFLINE_EMBEDDING_MODEL`, and optionally
`PROOFLINE_EMBEDDING_API_KEY`. After configuration, build the incremental index with
`make embed` or `POST /api/v1/model/embeddings/index`. Search and grounded answers then fuse FTS5 and dense ranks
with reciprocal-rank fusion; without an embedding provider or index they remain lexical-only.

Run the local container stack with:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## Scope

Proofline is not building a rich-text editor, canvas, generic agent builder,
custom model runtime, or graph database in the MVP. See
[`docs/`](docs/) for the product brief, architecture, decisions, and roadmap.

## License

This repository is currently licensed under the [MIT License](LICENSE).
Licensing boundaries for a future open-core distribution must be decided and
documented before accepting substantial external contributions.
