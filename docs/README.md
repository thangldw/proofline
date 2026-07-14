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
| [v0.14.12 notes](./releases/v0.14.12.md) | Public experimental repository and qualification boundary | Current pre-release |
| [v0.11.0 notes](./releases/v0.11.0.md) | One-command installed app with bundled web UI | Pre-alpha |
| [Alpha support boundary](./alpha-support-boundary.md) | Current exclusions and evidence required for alpha | Current |
| [Production readiness](./production-readiness.md) | Evidence gate matrix for the first supported local desktop profile | Current |
| [Support policy](../SUPPORT.md) | Supported experiment, issue handling, recovery escalation and rollback | Current |
| [Maintainers](../MAINTAINERS.md) | Current maintainer and explicit production ownership gaps | Current |
| [v0.10.0 notes](./releases/v0.10.0.md) | Embedded runtime lifecycle and same-origin web serving | Pre-alpha |
| [Embedded lifecycle](./embedded-lifecycle.md) | Start, readiness, data directory, stop and recovery contract | Implemented locally |
| [Roadmap evidence quality report](./reports/roadmap-evidence-quality-v0.10.0.html) | Metadata fitness of checked-in benchmark/platform receipts | Current report |
| [v0.10.0 launch-flow audit](./audits/v0.10.0-launch/audit.md) | Screenshot-backed Search, Sources and Settings audit | Current audit |
| [v0.6.0 notes](./releases/v0.6.0.md) | Reranking, grounding assessment and vector index | Pre-alpha |
| [v0.7.0 notes](./releases/v0.7.0.md) | Workspace isolation and multi-worker scan leases | Pre-alpha |
| [v0.8.0 notes](./releases/v0.8.0.md) | Portable non-empty merge with deterministic remapping | Pre-alpha |
| [v0.9.0 notes](./releases/v0.9.0.md) | Workspace UI and evidence-based watcher decision | Pre-alpha |
| [Roadmap evidence audit](./roadmap-evidence-2026-07-13.md) | Implemented milestones and external blockers | Current audit |
| [ADR 0003](./adr/0003-defer-tauri-packaging.md) | Defer Tauri until platform and lifecycle gates pass | Accepted |
| [v0.5.0 notes](./releases/v0.5.0.md) | Provider settings and model reliability | Pre-alpha |
| [Provider configuration](./provider-configuration.md) | Profiles, keys, health and retry semantics | Implemented |
| [v0.4.0 notes](./releases/v0.4.0.md) | Temporal decision relations and timelines | Pre-alpha |
| [v0.3.0 notes](./releases/v0.3.0.md) | Immutable local Git repository ingestion | Pre-alpha |
| [Product brief](./product-brief.md) | Problem, audience, value proposition, scope, and success measures | Baseline |
| [MVP architecture](./architecture.md) | Current vertical slice, planned boundaries, data model, and quality attributes | Evolving |
| [ADR-0001](./adr/0001-scope-and-stack.md) | First scope and technology decision | Accepted |
| [90-day roadmap](./roadmap-90-days.md) | Validation and delivery plan with measurable gates | Proposed |
| [External pilot protocol](./pilot-protocol.md) | Consent-safe evidence collection, metric formulas, and go/no-go rules | Ready for collection |
| [Security threat model](./security-threat-model.md) | Assets, trust boundaries, attacker stories, and severity calibration | Baseline |
| [Backup and recovery](./backup-recovery.md) | Portable export, complete SQLite backup, verification, restore drill, and retention limits | Implemented |
| [v0.1.0-alpha.5 notes](./releases/v0.1.0-alpha.5.md) | Live provenance integrity verification and cited inference | Pre-alpha |
| [v0.1.0-alpha.4 notes](./releases/v0.1.0-alpha.4.md) | Safe registered-folder polling and stable-read ingestion | Pre-alpha |
| [v0.1.0-alpha.3 notes](./releases/v0.1.0-alpha.3.md) | Transactional portable import and synthetic pilot simulation | Pre-alpha |
| [v0.1.0-alpha.2 notes](./releases/v0.1.0-alpha.2.md) | Release automation hardening and immutable-tag recovery | Pre-alpha |
| [v0.1.0-alpha.1 notes](./releases/v0.1.0-alpha.1.md) | First experimental pre-release scope, assets, and limitations | Pre-alpha |
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

As of 2026-07-13:

- Implemented in `apps/api`: Python/FastAPI + SQLAlchemy local API, SQLite schema,
  deterministic Markdown chunking, upload and registered-root folder ingestion, FTS5 lexical
  search, deterministic extraction of explicitly marked English/Vietnamese decisions,
  assumptions, constraints, and alternatives, exact evidence spans, source and generalized-memory
  browsing, cascading source deletion, health/overview endpoints, and tests.
- Implemented in `apps/web`: React/Vite local evidence console for Markdown upload, lexical
  and optional hybrid search with source/indexed-time scopes, source inventory, filterable generalized-memory review and
  correction, reversible statuses, overview counts, evidence inspection, statement-level
  citation mapping, retrieval diagnostics, context-budget exclusions, and degraded search
  behavior when answer generation fails. A dedicated safe Model runs view filters metadata and
  inspects parent/current/child repair lineage without rendering private model payloads.
- Local container scaffolding and root setup/development/quality commands are present. Docker
  Compose publishes the unauthenticated API to loopback by default.
- Also implemented: immutable source-version history and versioned SQLite migrations, including a
  large legacy-database fixture that exercises migration/backfill provenance and current behavior.
- Also implemented: migration-backed retryable ingestion jobs, private staged input, atomic
  domain/job commits, startup recovery, idempotency keys, dead-letter handling, and UI retry controls.
- Also implemented: governed updates for decisions, assumptions, constraints, and alternatives,
  with append-only before/after audit events.
- Also implemented: provider-neutral generation gateway, fake/OpenAI-compatible adapters,
  explicit remote egress, structured-output validation, and persisted model-run diagnostics.
  Safe list/detail and repair-lineage inspection is available through both the API and web view.
- Also implemented: bounded lexical evidence packs, typed grounded statements, server-resolved
  exact citations, insufficient-evidence behavior, and fail-closed grounding validation.
- Also implemented: the versioned synthetic retrieval v2 corpus and repository evaluation command
  for Recall@10, Precision@10, MRR, nDCG@10, and expected-empty accuracy. V2 covers 26 Unicode and
  current/superseded-revision queries. The recorded hosted workflow ran it successfully, but
  synthetic scores are not pilot evidence. Real pilot judgments are still required.
- Also implemented: separate OpenAI-compatible embedding provider, incremental versioned vectors,
  dense cosine retrieval, and reciprocal-rank fusion with lexical results.
- Also implemented: schema-validated, evidence-grounded AI memory candidates for all four current
  memory kinds, linked to model runs and the human review/audit workflow.
- Also implemented: a credential-free deterministic extraction gate for all four memory kinds,
  exact evidence slices and hashes, English/Vietnamese markers, CJK statements after supported
  markers, and negative prose. It is not real-model extraction evidence.
- Also implemented: registered-root folder scanning with traversal/symlink containment, per-file
  results, immutable updates, audited unique-hash rename preservation, sorted missing-file preview,
  and exact-set confirmed deletion that fails closed on drift or scan errors.
- Also implemented: metadata-only source deletion impact, verified cascade cleanup including
  embeddings/FTS/audits, and source-level ingestion job diagnostics in the web inventory.
- Also implemented: web behavior tests, a repository threat model, and CI secret scanning. A
  credential-free Chromium E2E test covers import, governed review/correction, retrieval debug,
  exact evidence, and deletion; hostile Markdown remains inert and non-loopback requests fail the
  test. The recorded hosted workflow passed this job for revision `0dde53f`.
- Also implemented: deterministic local lexical benchmark reporting and a versioned environment-
  qualified observation receipt; this is not a product performance guarantee.
- Also implemented: a credential-free synthetic grounded-QA regression gate that exercises the
  runtime answer and fail-closed citation path; it is not pilot or real-model quality evidence.
- Also implemented: verified portable JSON export, empty-database transactional import, and
  complete online SQLite backup commands. Import preserves source versions and exact evidence,
  rebuilds deterministic chunks/FTS without extraction, and records a payload receipt.
- Also implemented: a credential-free platform smoke script and an Ubuntu/macOS workflow matrix
  covering installation, local evidence, export verification, backup verification, and the web
  build. The [versioned receipt](../evals/platform/github-actions-0dde53f.json) records successful
  hosted API CI and Secret Scan runs, including both platform jobs. This is not production support;
  Windows remains unverified.
- Also implemented: portable merge/remap, a local vector candidate index, optional reranking,
  workspace isolation, a benchmark-backed polling watcher decision, and an embedded start/ready/
  stop lifecycle with bundled same-origin web serving from the installed wheel.
- Not yet completed: real-model/pilot evaluation, Windows verification, production support,
  signed desktop packaging, cloud services, or telemetry.

Update this inventory whenever the repository reaches a meaningful milestone.
