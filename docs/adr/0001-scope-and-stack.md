# ADR-0001: MVP Scope and Technology Stack

- **Status:** Accepted
- **Date:** 2026-07-12
- **Deciders:** Project maintainers
- **Implementation:** Foundation slice in progress

## Context

Proofline needs to prove that exact evidence and temporal engineering memory produce better
context recovery than document search alone. The largest execution risks are ingestion
reliability, citation correctness, model variability, and trying to build too broad a product.

The repository now contains the first local API increment. This ADR records the direction used
by that implementation and separates it from planned later stages.

## Decision

### Product boundary

Build one local, single-user, evidence-backed vertical slice for Markdown/ADR sources. The
slice includes source versioning, exact spans, lexical and semantic retrieval, reviewable
decision extraction, grounded answers, and pipeline diagnostics.

Do not build a rich editor, real-time collaboration, general agent platform, graph database,
mobile client, cloud sync, or enterprise features during the 90-day MVP.

### Runtime and language

Use Python 3.11+ with FastAPI, Pydantic, and SQLAlchemy for the local API in `apps/api`. Keep the
backend as a single installable package with pytest tests and root `make` entry points. Validate
API and future model boundaries with typed Pydantic schemas.

Use React, TypeScript, and Vite for the local evidence console in `apps/web`. The client consumes
the FastAPI HTTP contract and does not own ingestion or extraction rules. Desktop packaging
remains deferred until the web/API workflow is stable.

### Persistence and search

Use SQLite as the canonical MVP database, with migrations committed to source control. Use
SQLite FTS5 for lexical search and the local filesystem for source files. Store typed relations
in ordinary tables instead of introducing a graph database.

Keep vector storage behind an interface. Select a SQLite-compatible vector implementation or
a bounded in-process implementation through a benchmark spike; the choice must not leak into
the domain model.

Persist source span offsets as Python Unicode code-point indexes, with exclusive end offsets.
Store one-based inclusive line boundaries for display. Test round trips with multibyte and
mixed-newline fixtures before declaring this a stable external format.

### Models

Define provider-neutral generation and embedding interfaces. The first adapters target:

- an OpenAI-compatible HTTP API, which can represent Qwen, DeepSeek, and other providers when
  they expose compatible endpoints; and
- a local runtime endpoint such as Ollama.

No provider is mandatory for offline lexical search. Model output is untrusted and must pass
versioned schema validation before persistence. CI uses fakes and recorded fixtures by default,
not live paid endpoints.

### Delivery shape

Use a modular Python monolith with in-process jobs first. Persist job state so future work is
resumable.
Components communicate through typed application interfaces, not an event broker. Split into
services only after profiling or deployment requirements demonstrate a need.

## Rationale

- Python provides mature parsing, evaluation, AI-provider, and local-service tooling.
- FastAPI and Pydantic provide inspectable HTTP contracts and boundary validation.
- SQLAlchemy keeps the implemented persistence model explicit while retaining a path to a
  future hosted relational database.
- React/Vite provides a lightweight inspection UI without committing to a rich editor.
- SQLite and FTS5 make the local-first path portable and operationally simple.
- A modular monolith preserves boundaries without taking on distributed-system failure modes.
- A browser-served UI lets the team validate workflow before accepting desktop packaging cost.
- Provider interfaces and schema validation address cheap/local model variability without
  tying product semantics to one vendor.

## Consequences

### Positive

- A contributor can eventually run the whole MVP on one machine.
- Exact provenance can be enforced transactionally with derived memory.
- Core search and browsing remain useful when providers are offline.
- Tests can cover the complete slice without external infrastructure.
- Provider and vector implementations can be replaced behind contracts.

### Negative

- The web client introduces a second language/runtime and requires generated or manually
  synchronized API contracts.
- In-process jobs limit throughput and require careful crash recovery.
- SQLite has a bounded concurrent-write envelope and is not the intended team-cloud database.
- Deferring desktop packaging means the first UX is not yet a native local application.
- Maintaining Unicode code-point offsets requires disciplined round-trip tests at every parser
  boundary and explicit conversion for clients that use UTF-16 indexes.

## Alternatives considered

### TypeScript service and UI monorepo

Rejected for the backend foundation. Shared UI types would be convenient, but Python's parsing
and AI ecosystem better fits the core pipeline. The implemented React client uses TypeScript
behind the HTTP contract.

### Tauri desktop application from day one

Deferred. Native distribution and OS integration are valuable, but packaging and platform
support can obscure the evidence/retrieval validation goal.

### PostgreSQL, Qdrant, and a worker queue

Rejected for the local MVP because they raise installation and operations cost. They remain
candidates for a future managed/team deployment.

### Neo4j or another graph database

Rejected for the MVP. The initial ontology and traversal depth fit relational adjacency tables,
and the graph workload has not yet been measured.

### Build an editor as the primary product surface

Rejected. Proofline is designed to remember artifacts where engineers already work. An editor
would consume scope without validating the core differentiation.

## Validation conditions

The foundation currently demonstrates a FastAPI/SQLAlchemy application, SQLite/FTS5 schema,
deterministic Markdown chunks and decisions with character/line locations, a React/Vite evidence
console, API tests, and root quality commands. Remaining validation before calling the complete
MVP stack proven includes:

- Unicode span round trips across the full golden fixture set;
- a provider interface tested with a fake adapter; and
- benchmark evidence for the selected vector implementation.

Revisit the decision if a required parser cannot run safely in Python, SQLite cannot meet the
documented scale envelope, or desktop security constraints require a different process model.

## Licensing note

The repository currently contains an MIT license. This ADR does not adopt AGPL, dual licensing,
or an open-core boundary. Licensing changes require a separate legal and governance decision.
