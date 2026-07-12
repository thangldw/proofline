# Proofline Documentation

Proofline is at the **foundation / pre-alpha stage**. A runnable vertical slice is implemented
under `apps/api` and `apps/web`; it is not production-ready. Unless a document explicitly says
otherwise, capabilities described here are planned, not implemented.

Proofline's intended product is an evidence-first Engineering Decision Memory: a local-first,
model-agnostic system that helps engineering teams recover why software was built a certain
way and trace every answer back to exact source evidence.

## Start here

| Document | Purpose | Status |
| --- | --- | --- |
| [Product brief](./product-brief.md) | Problem, audience, value proposition, scope, and success measures | Baseline |
| [MVP architecture](./architecture.md) | Current vertical slice, planned boundaries, data model, and quality attributes | Evolving |
| [ADR-0001](./adr/0001-scope-and-stack.md) | First scope and technology decision | Accepted |
| [90-day roadmap](./roadmap-90-days.md) | Validation and delivery plan with measurable gates | Proposed |
| [Contributing workflow](./contributing.md) | Human contribution and review rules | Baseline |
| [Agent implementation spec](./agent-spec.md) | Operating contract for Codex, Claude, and other coding agents | Baseline |

## Documentation conventions

- **Implemented** means code exists in this repository and has been verified.
- **Planned** means accepted product intent but not necessarily scheduled.
- **Proposed** means a decision remains open to review.
- **Deferred** means intentionally outside the current delivery window.
- Requirements use `MUST`, `SHOULD`, and `MAY` in the RFC 2119 sense.
- Product claims should be backed by tests, measurements, or linked research. Aspirations
  must not be written as shipped behavior.

## Current implementation inventory

As of 2026-07-12:

- Implemented in `apps/api`: Python/FastAPI + SQLAlchemy local API, SQLite schema,
  deterministic Markdown chunking, content ingestion, FTS5 lexical search, deterministic
  extraction of explicitly marked English/Vietnamese decisions, exact evidence spans, source
  and decision browsing, cascading source deletion, health/overview endpoints, and tests.
- Implemented in `apps/web`: React/Vite local evidence console for Markdown upload, lexical
  search, source/decision browsing, overview counts, and evidence inspection.
- Local container scaffolding and root setup/development/quality commands are present.
- Also implemented: immutable source-version history and versioned SQLite migrations.
- Also implemented: persisted terminal status for synchronous ingestion jobs.
- Also implemented: governed decision updates and append-only before/after audit events.
- Also implemented: provider-neutral generation gateway, fake/OpenAI-compatible adapters,
  explicit remote egress, structured-output validation, and persisted model-run diagnostics.
- Also implemented: bounded lexical evidence packs, typed grounded statements, server-resolved
  exact citations, insufficient-evidence behavior, and fail-closed grounding validation.
- Also implemented: a versioned synthetic retrieval corpus and CI gate for Recall@10,
  Precision@10, MRR, and nDCG@10. Real pilot judgments are still required.
- Also implemented: separate OpenAI-compatible embedding provider, incremental versioned vectors,
  dense cosine retrieval, and reciprocal-rank fusion with lexical results.
- Also implemented: schema-validated, evidence-grounded AI decision candidates linked to model
  runs and the existing human review/audit workflow.
- Not yet implemented: resumable/retryable job execution, scalable vector index, reranker,
  assumption/constraint extraction, repair retries, desktop packaging, cloud services, or
  telemetry.

Update this inventory whenever the repository reaches a meaningful milestone.
