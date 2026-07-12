# Proofline 90-Day Roadmap

**Document status:** Proposed  
**Start assumption:** Day 1 begins with the foundation repository  
**Implementation status:** The internal Phase 2 engineering gates are implemented; Phase 1 pilot
corpus evidence remains open, and Phase 3 governed extraction is in progress

The roadmap is organized around validated outcomes. Dates may move; quality gates should not be
silently weakened to preserve a date.

## Day 0 baseline

Before delivery work, record:

- the accepted product brief and architecture ADR;
- supported development platforms, Python version, Node.js version, and npm version;
- five prospective pilot teams or equivalent individual design partners;
- at least 25 real engineering-context questions, with permission to use sanitized artifacts;
- security and privacy constraints for the pilot data; and
- a named owner for product, architecture, evaluation, and release decisions.

## Phase 1 — Days 1–14: Foundation and problem corpus

### Outcomes

- A runnable Python/FastAPI + SQLAlchemy service and React/Vite evidence console with tests and
  build checks. This scaffold and the first deterministic vertical slice are implemented.
- Reproducible local setup and CI that needs no provider credentials.
- A versioned evaluation corpus derived from real questions.
- A threat sketch for local files, local API, provider egress, and model output. The baseline
  repository threat model and CI secret scan are implemented.

### Planned work

- Keep ADR-0001 aligned with implementation.
- Maintain Python formatting/linting/tests, web behavior tests, the TypeScript production build,
  migration tests, and secret scanning. These automated foundations are implemented; corpus and
  pilot evidence remain open.
- Establish contracts for source identity, source versions, spans, jobs, and model runs.
- Extend the implemented synthetic ADR retrieval corpus with CJK, revision cases, and a
  permissioned real-question dataset.
- Interview 5–10 engineers and classify questions by decision, rationale, ownership, change,
  incident, and validity intent.
- Record a manual baseline: time and sources needed to answer each usable question today.

### Exit gate

- A clean checkout can run `make setup`, then `make test` and `make check`.
- CI is green without network model access.
- At least 25 questions have source evidence and relevance judgments; 10 should exercise a
  decision changing over time.
- Offset encoding and deletion semantics are explicitly decided and tested.

## Phase 2 — Days 15–35: Trustworthy local ingestion

### Outcomes

- A local folder can be scanned into immutable source versions and exact spans.
- Every source has visible stage status and actionable failures.
- Unchanged files are not reprocessed; changed and deleted files behave deterministically.

### Planned work

- Harden Markdown/text upload and safe registered-root folder scanning. On-demand scanning,
  containment checks, deterministic ordering, immutable updates, audited unambiguous rename, and
  missing-file preview are implemented; watching and confirmed missing-file deletion remain open.
- Harden the implemented immutable source versioning and explicit SQLite migrations. Atomic crash
  rollback, v7-to-v8 backfill, startup recovery, idempotency, and stale-claim concurrency are
  tested; a larger legacy-database fixture remains open.
- Harden the implemented FTS5 lexical search and exact-span contract.
- Extend the implemented persisted ingestion job status with retries and dead-letter states.
  Bounded retry, private staged input, conditional claims, startup recovery, and UI controls are
  implemented.
- Extend the implemented source/decision inventory UI with stage diagnostics. Latest job state,
  stage, attempts, retryability, and safe failure fields are now visible per source.
- Implement deletion preview and cascade behavior for derived data. Source deletion impact and
  complete tested cascade cleanup are implemented; missing-file confirmation remains open.

### Exit gate

- Integration tests now cover create, update, unambiguous and ambiguous rename, duplicate content,
  delete, retry, stale concurrent claims, and crash recovery.
- All golden source spans pass exact hash/offset validation.
- Every discovered fixture reaches a visible `ready`, `failed`, or `dead_letter` state; retryable
  failures expose a retry control.
- Lexical search p95 is measured against the documented local scale fixture; a qualified 1,000-
  source/100-query receipt is committed under `evals/benchmarks/`. No unqualified performance
  claim is published.

## Phase 3 — Days 36–56: Model gateway and governed extraction

### Outcomes

- A provider can be configured and health-checked without changing domain code.
- Candidate decisions and assumptions are derived with exact evidence and schema validation.
- Users can accept, correct, reject, and obsolete candidates.

### Planned work

- Harden the implemented fake/OpenAI-compatible gateway across selected remote and local runtimes.
- Extend the implemented explicit remote-egress configuration and secret-safe diagnostics.
- Extend the implemented versioned decision-extraction prompt/schema to assumptions, constraints,
  and alternatives. The generalized schema, deterministic extraction, exact evidence, and
  decision-only compatibility API are implemented.
- Add validation, bounded repair retries, confidence metadata, and dead-letter inspection.
  Schema/size and evidence-ID repair is implemented as one additional call with secret-safe
  `ModelRun` lineage; model-run inspection and broader extraction evaluation remain open.
- Extend the implemented AI decision candidate queue and audit-backed review actions to other
  memory kinds. The filterable memory registry and review API now cover decisions, assumptions,
  constraints, and alternatives.
- Run extraction evaluation across at least one remote and one local/cheap model if available.

### Exit gate

- Invalid model output never creates a valid domain record.
- Every candidate records its source spans and model-run metadata.
- Provider failure leaves indexed sources searchable.
- Review actions are reversible and audited.
- Model comparison reports include dataset, configuration, cost/latency where available, and
  precision/recall estimates; they do not imply general quality from anecdotal examples.

## Phase 4 — Days 57–75: Evidence-backed answers

### Outcomes

- A user can ask a real pilot question and inspect why each source was selected.
- Answers have exact citations and visible evidence/synthesis/inference labels.
- Insufficient evidence produces a useful qualified response.

### Planned work

- Benchmark and replace the implemented bounded SQLite JSON embedding storage when scale requires.
- Extend the implemented lexical/semantic retrieval and reciprocal-rank fusion with filters and
  diversity control.
- Add optional reranking behind a capability interface.
- Extend the implemented bounded lexical evidence packs and grounded answer generation to hybrid
  retrieval and context diversity.
- Harden the implemented deterministic citation identifier and quoted-span validation.
- Extend the implemented citation navigation with a retrieval debug view.
- Add grounded-QA golden tests and evaluation harness.

### Exit gate

- 100% of emitted citations resolve and match stored source spans in automated tests.
- Citation precision is at least 90% on the pilot evaluation set, or the phase remains open.
- Unsupported statements are rejected, repaired, or clearly labeled as inference.
- The system can return `insufficient evidence` without calling that state an error.

## Phase 5 — Days 76–90: Pilot hardening and release decision

### Outcomes

- Design partners can install and use a documented alpha on approved data.
- The project has evidence for whether to continue, narrow, or stop.
- OSS contributors can understand scope, reproduce checks, and report failures safely.

### Planned work

- Complete end-to-end tests and supported-platform smoke tests.
- Add export, backup guidance, recovery exercises, and a complete deletion test.
- Run a lightweight security review of local API, path handling, dependency surface, egress,
  logging, and imported content rendering.
- Add contributor templates, code of conduct decision, security reporting process, and release
  notes.
- Pilot weekly with up to five teams; collect task completion time and structured feedback.
- Triage only defects that block the defined vertical slice; defer feature expansion.

### Go/no-go gate

Continue toward a public beta when:

- citation precision is >= 90%;
- useful-answer rate is >= 65% on real pilot questions;
- median time-to-context improves >= 50% from the recorded baseline;
- at least 3 of 5 pilot teams use the workflow weekly;
- at least 2 teams express concrete willingness to pay for a defined managed/team capability;
- no unresolved critical security or deletion-integrity defect exists; and
- the supported setup succeeds on the declared platform matrix.

If gates are missed, document which hypothesis failed. Narrow the source set, ontology, or user
segment before adding features.

## Work intentionally deferred beyond day 90

- GitHub/GitLab write integrations and broad connector coverage.
- PDF, audio, email, chat, calendar, and incident ingestion.
- Desktop packaging and mobile clients.
- Team authorization, shared workspaces, and real-time collaboration.
- Managed sync/inference, billing, enterprise controls, and deployment automation.
- Autonomous agents, plugin marketplace, editor, canvas, and graph visualization.

Deferred work requires its own evidence, owner, threat model, and acceptance criteria before
entering an active milestone.
