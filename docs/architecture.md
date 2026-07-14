# Proposed MVP Architecture

**Document status:** Evolving  
**Implementation status:** Pre-alpha local vertical slice implemented through governed generalized
memory and evidence-backed answers; external pilot gates and later product stages remain open
**Decision records:** [ADR-0001](./adr/0001-scope-and-stack.md),
[ADR-0002](./adr/0002-git-source-identity-and-provenance.md)

## Architecture goal

Deliver one testable vertical slice from local engineering source to evidence-backed answer,
while keeping storage local, model providers replaceable, and every derived fact traceable.

The architecture deliberately avoids a rich editor, graph database, distributed workers, and
cloud control plane in the MVP.

## Vertical slice

```text
Local Markdown folder
        |
        v
Discover -> parse -> version -> chunk -> index -> extract candidates
        |                                      |
        v                                      v
  source + spans                         review queue
        |                                      |
        +------------------+-------------------+
                           v
                 retrieve -> answer
                      \-> optional rerank (planned)
                           |
                           v
                exact citations + labels
```

A slice is complete only when a fixture source can move through this flow, a user can inspect
its processing state, and an answer citation resolves to the original source version and span.

## Components and implementation status

### 1. Local API service — implemented foundation

`apps/api` is a Python 3.11+ FastAPI service using Pydantic, SQLAlchemy, and SQLite. It currently
owns configuration, Markdown chunking, content ingestion, source/memory/evidence persistence,
deterministic marked-memory extraction, immutable source versions, committed schema migrations,
source retrieval and deletion, FTS5 search, overview counts, and health reporting. Local
development runs through Uvicorn.

The deterministic ingestion path is synchronous and has no required model dependency. Optional
generation and embedding providers use the same immutable evidence contract.

### 2. Local web application — implemented foundation

`apps/web` is a React/Vite evidence console. It currently supports browser-side Markdown/text
upload to the API, lexical and configured hybrid search, source/job inventory, filterable review
and correction for decisions, assumptions, constraints, and alternatives, reversible statuses,
overview counts, source-deletion impact confirmation, and exact evidence navigation. Grounded
answer statements retain their statement-level citation mapping; retrieval ranking and context-
budget exclusions plus source/indexed-time scopes are inspectable; and an answer-provider failure
does not discard lexical results. It is a pre-alpha inspection surface, not a rich editor. Provider
configuration remains environment-based and has no settings UI. A dedicated safe Model runs view
filters run metadata and inspects parent/current/child repair lineage without rendering source
text, prompts, model output, credentials, or input hashes. Desktop packaging is deferred.

### 3. Application boundaries and remaining modules

The service will grow through internal interfaces rather than provider-specific product logic.
Current and target boundaries are:

- workspace abstraction — implemented as local API workspaces selected by the
  `X-Proofline-Workspace-ID` header, with a backward-compatible default workspace;
- source catalog and ingestion coordinator — implemented for upload and registered roots;
- read-only local Git ingestion — implemented for immutable commit metadata and tracked
  Markdown/text objects;
- retrieval and answer service — implemented with optional post-RRF reranking, deterministic
  statement-support assessment, and indexed semantic candidate selection;
- governed memory review service — implemented for four memory kinds;
- temporal decision relation service — implemented for typed, audited transitions, validity
  windows, timelines, and non-mutating contradiction/staleness candidates;
- provider gateway plus safe model-run API and web diagnostics — implemented, with provider settings UI planned;
- job status, retry, and source diagnostics — implemented; and
- deletion impact/cascade plus portable export/import and SQLite backup services — implemented
  locally; portable import is intentionally limited to an empty target; and
- read-only semantic integrity verification — implemented for SQLite source/version, exact-span,
  embedding-ownership, and FTS invariants.

### 4. Ingestion pipeline

The implemented foundation ingests synchronously. A URI identifies a stable source, SHA-256
identifies an immutable version, unchanged content is a no-op, and changed content creates a new
version while preserving historical evidence. URI-less repeated content remains idempotent.
Every synchronous ingestion attempt persists a job with stage, terminal state, safe error
code/detail, attempt count, and source/version references. The request payload is staged in a
private table that has no read API. Source/version/chunk/FTS writes, terminal success, and staged
input deletion commit atomically. Startup recovery converts interrupted jobs to retryable failures;
conditional retry claims prevent a stale second claimant from incrementing attempts. A source
progresses through independently visible stages:

```text
discovered -> parsed -> indexed -> extracted -> ready
                 |          |           |
                 +----------+-----------+-> failed(stage, reason, retryable)
                                                |
                                                +-> dead_letter(attempts exhausted)
```

`ready` means all enabled stages succeeded. A source that is parsed and searchable but has a
failed extraction remains usable and visibly degraded.

Each source version is keyed by a stable source identity and content hash. Unchanged content
must not be parsed, embedded, or extracted again. A changed file creates a new source version;
old evidence remains resolvable until retention or deletion removes it.

For Git repositories, the API resolves a requested revision to a full commit SHA before reading
objects. A `git_file` identity combines repository root, commit SHA, and repository-relative path;
a `git_commit` identity uses the same root and SHA with a reserved commit locator. Re-scanning the
same commit is idempotent, a later commit creates new immutable sources, and citations additionally
expose commit SHA and path alongside exact offsets and lines. Git reads use tracked objects rather
than mutable working-tree content.

### 5. Storage

The foundation uses SQLite plus content uploaded from the browser or API:

- Browser-selected files remain in their original location; the web client reads their text and
  sends the content to the local API.
- The API can scan explicitly registered local roots for Markdown and UTF-8 text. It resolves
  every selected path before reading, rejects traversal and symlink escape, and never accepts an
  arbitrary unregistered root. Folder watching and implicit deletion remain unimplemented;
  exact-set confirmed missing-source deletion is implemented as a separate fail-closed scan.
- SQLite currently stores sources, raw Markdown/text, chunks, generalized governed memories, evidence,
  character/line spans, and FTS rows through SQLAlchemy models plus an FTS5 virtual table.
- SQLite FTS5 currently provides lexical search.
- Source versions, versioned schema migrations, resumable ingestion jobs with private staged
  input, generalized memory kinds, and memory audit events are implemented.
- A metadata-only deletion-impact endpoint counts every source-owned version, chunk, embedding,
  governed memory (including the decision subset), evidence link, audit event, FTS row, and
  ingestion job that will be detached. Confirmed
  deletion removes content-bearing derived rows and preserves only detached safe job diagnostics.
- Versioned chunk embeddings are implemented in a local SQLite table with provider/model,
  dimensions, content hash, and immutable source-version ownership. Indexing is incremental.
  Dense search uses a SQLite locality-sensitive sign-vector band index to select candidates before
  exact in-process cosine scoring. The checked-in 1,000-source synthetic receipt measures latency,
  memory, storage, and update cost; it does not qualify the 10,000-file/1-GB envelope.

No graph database is planned for the MVP. Typed relations are represented as adjacency rows
and queried through the domain repository.

`decision_relations` stores directed `supersedes`, `implements`, `contradicts`, `based_on`, and
`considered` edges. `source_decision_id` is the newer/acting decision for `supersedes`; creating
that edge closes the target's validity and marks it obsolete in the same transaction. Ingestion
time remains separate from decision validity. Retrieval demotes obsolete/ended decisions, while
timeline reads keep historical evidence inspectable. Candidate diagnostics never mutate memory.

### Registered-root folder scanning

Folder access is disabled by default. Register one or more roots with the operating-system path
separator (`:` on Unix-like systems, `;` on Windows):

```bash
export PROOFLINE_IMPORT_ROOTS="/absolute/team-docs:/absolute/project-adrs"
```

`POST /api/v1/folder-scans` accepts an optional registered `root`, an optional relative `path`,
and `delete_missing` (default `false`). When exactly one root is registered, `root` may be omitted.
The scanner recursively processes `.md`, `.markdown`, and `.txt` files in deterministic path
order, rejects files larger than 5 MB, and feeds valid UTF-8 content through the same observable
ingestion jobs as uploads. Unchanged files retain their current immutable version; changed files
create a new version under the stable resolved `file://` URI.

When one new file and one missing source have the same current content hash, the scanner treats the
change as a rename: it preserves the source/version/evidence identity and records a metadata-only
`source.renamed` audit event. Multiple old or new matches are ambiguous and never auto-linked.

The response reports every processed file and a sorted `missing_source_ids` set. Scans remain
preview-only unless a subsequent request sends `delete_missing=true` and the exact previewed set as
`confirmed_missing_source_ids`. Deletion fails closed if the current missing set changed, any ID is
outside the selected registered-root scan, or any file/ingestion result failed. Confirmed deletion
uses the same complete source cascade as the source deletion endpoint; it is never implicit.

Set `PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS` to an integer from 1 through 3600 to opt into the
single-process polling watcher (`0`, the default, disables it). It starts one immediate cycle and
then scans each registered root sequentially at the configured interval, using a fresh database
session per root. Watcher and manual scans share one process-local coordinator, never overlap, and
watcher scans always submit `delete_missing=false`; missing sources are therefore only reported for
later human-confirmed deletion. `GET /api/v1/folder-watch` exposes only ephemeral counters,
timestamps, and stable error codes—not root paths, source contents, or exception messages. This
pre-alpha implementation is not a multi-worker coordinator or native filesystem notification
service; operators must enable it in at most one API process. Shutdown waits for an active scan to
finish instead of abandoning its database transaction, so slow filesystems can delay termination.

The shipped Compose file intentionally has no host-vault mount. Container deployments must add an
explicit read-only bind mount and register its container path; setting a host path in the environment
alone does not grant filesystem access.

### 6. Model gateway — implemented foundation

The provider-neutral generation interface, deterministic fake provider, OpenAI-compatible
adapter, structured-output validation, explicit remote-egress gate, provider status API, and
persisted secret-safe model-run diagnostics are implemented. OpenAI-compatible endpoints cover
Qwen, DeepSeek, Ollama, vLLM, and similar providers when their selected model implements the
required chat and structured-output behavior. All model calls pass through capability-based
interfaces:

```python
class GenerationProvider(Protocol):
    @property
    def id(self) -> str: ...
    def capabilities(self) -> ModelCapabilities: ...
    def generate(self, request: GenerateRequest) -> GenerateResult: ...

class EmbeddingProvider(Protocol):
    @property
    def id(self) -> str: ...
    def dimensions(self, model: str) -> int: ...
    def embed(self, request: EmbedRequest) -> EmbeddingResult: ...
```

Provider adapters normalize OpenAI-compatible remote endpoints and local runtime endpoints.
Domain code requests a capability, not a vendor. Persisted model runs record provider, model,
prompt/template version, input content hashes, latency, token counts when available, and
validation outcome. Secrets must never be written to logs or model-run records.

The Settings surface persists explicit Qwen, DeepSeek, Ollama, vLLM, or generic compatible
profiles in a local owner-readable file; environment variables override that file. Generation,
embedding, and reranking report independent capability health. Transient transport failures use at
most three attempts before the run becomes `dead_letter`. Manual extraction retry is allowed only
for the same immutable input hash and exact provider/model, records parent lineage, and never falls
back from local to remote inference.

Structured results are parsed as untrusted data and validated against versioned schemas. Invalid
results persist a failed model run without creating memory. Structured output is capped at 128 KiB;
memory batches are capped at 64 candidates. Repairable schema, size, kind, and evidence-ID failures
receive at most one repair call with the same provider, model, evidence pack, input hashes, and
temperature zero. Initial and repair calls remain separate `ModelRun` records linked by
`parent_run_id`; invalid output and validation details are neither persisted nor copied into the
repair prompt. Transport retries and model-run dead-letter handling remain planned. Provider errors
must not corrupt existing source or memory records. Safe list/detail endpoints expose run status,
operation, provider, validation metadata, and parent/child repair lineage; they never expose source
content, prompt messages, model output, or credentials. The web Model runs view consumes these safe
endpoints, applies status/operation/provider/parent filters, and displays detail plus repair lineage
without rendering input hashes or private payloads.

Model-assisted governed memory extraction is implemented as a separate source action for decisions,
assumptions, constraints, and alternatives. Candidates must cite known chunks from the current
immutable source version, are deduplicated per version and kind, retain the generating `ModelRun`,
and always enter the governed review flow as `candidate`. Unknown evidence fails or repairs before
any memory object is persisted. The legacy decision endpoint is decision-only before persistence.

### 7. Retrieval and answering

Lexical FTS5 retrieval, dense cosine retrieval, reciprocal-rank fusion, and the guarded answer path
are implemented. Search and answer accept optional source-ID and indexed-time filters; the latter
is explicitly ingestion time, not event time inside a document. The current path builds a bounded
evidence pack, requests typed statements plus evidence IDs, rejects unknown/missing IDs, resolves
citations server-side, and revalidates exact spans against immutable source versions. When no
provider is configured, it returns verified evidence without synthesizing claims. RRF ordering is deterministic and applies a soft two-hit
per-source diversity cap before ranked backfill. New paragraphs are split into at most 1,600 code
points with exact offsets; the answer runtime additionally caps serialized UTF-8 evidence at 64 KiB
total and 8 KiB per item for legacy safety. Budget exclusions expose only evidence ID plus reason,
and an all-excluded pack returns insufficient evidence without model execution. Cross-encoder
reranking and semantic entailment checks remain planned. Semantic cosine defaults to a mathematical
floor of zero: invalid/non-finite/zero-norm vectors and negative similarity are excluded before
ranking, while lexical matches remain independent. The `0..1` floor is caller-configurable but is
not considered relevance-calibrated without model-specific evaluation. Grounded drafts are capped at 32 statements
and receive at most one repair for invalid structured output or missing/unknown citations. The target
full path is:

1. normalize the question and optional filters;
2. run lexical and semantic retrieval independently;
3. fuse ranked results using reciprocal-rank fusion;
4. filter by source version, workspace, and deletion state;
5. optionally rerank through a configured capability;
6. select diverse evidence within a bounded context budget;
7. generate an answer constrained to evidence identifiers;
8. validate that every cited identifier exists and its quoted span matches stored content;
9. label statements as direct, synthesis, inference, or insufficient evidence.

If repairable answer validation fails, the service retries once with a replacement-only repair
prompt, then returns a qualified failure rather than ungrounded prose.

## Domain model

The names below describe the target MVP. Current SQLAlchemy models and SQLite setup in `apps/api`
remain the source of truth for implemented records. `Source`, `Chunk`, `Evidence`, `SourceVersion`,
`ModelRun`, `IngestionJob`, and `AuditEvent` are implemented. Governed memories currently use the
compatibility `decisions` table plus a required kind; a renamed `MemoryObject` table and `Relation`
remain planned.

```text
Workspace
  id, name, created_at

Source
  id, workspace_id, kind, canonical_uri, display_name, deleted_at

SourceVersion
  id, source_id, content_hash, observed_at, parser_version, status

SourceSpan
  id, source_version_id, start_offset, end_offset, line_start, line_end,
  content_hash, quoted_text

MemoryObject
  id, workspace_id, kind, status, title, body, valid_from, valid_to,
  created_by, model_run_id, created_at, updated_at

EvidenceLink
  id, memory_object_id, source_span_id, stance, confidence

Relation
  id, source_memory_id, target_memory_id, kind, created_by, evidence_link_id

ModelRun
  id, provider_id, model_id, operation, template_version,
  input_hashes, parent_run_id, attempt_number, repair_reason,
  validation_status, created_at, finished_at

Job
  id, kind, state, stage, attempts, error_code, error_detail, timestamps

AuditEvent
  id, actor, action, object_type, object_id, before_json, after_json, created_at
```

Implemented memory kinds are `decision`, `assumption`, `constraint`, and `alternative`.
Reviewable statuses are `candidate`, `active`, `accepted`, `rejected`, and `obsolete`.
Candidate model output never becomes accepted solely because a model emitted it.

Important relation kinds are `supports`, `contradicts`, `depends_on`, `considered`,
`implemented_by`, and `supersedes`. Temporal validity belongs to the memory object, while the
history of edits belongs to audit events.

## Source-span invariants

Provenance is a system invariant, not presentation metadata:

- `0 <= start_offset < end_offset <= source_version_length`.
- Stored quoted text must hash to the same value as the referenced content slice.
- A citation references an immutable source version, never only a mutable file path.
- A derived memory without evidence must be explicitly marked as user-authored or inferred.
- Re-indexing must not silently repoint historical citations to a new version.
- Citation navigation should prefer line/column information for text display while offsets
  remain the canonical boundary.

Implemented offsets use Python string indexes (Unicode code points), with an exclusive end
offset. Lines are one-based and inclusive. CJK, emoji, CRLF, and combining-character behavior
must remain covered by fixtures before this representation is treated as a stable public
contract.

## Local API surface

Implemented foundation operations:

```text
GET    /health
GET    /api/v1/overview
POST   /api/v1/sources
POST   /api/v1/git-repositories
GET    /api/v1/git-repositories
DELETE /api/v1/git-repositories/:id
POST   /api/v1/folder-scans
GET    /api/v1/sources
GET    /api/v1/sources/:id
GET    /api/v1/sources/:id/deletion-impact
GET    /api/v1/sources/:id/versions
GET    /api/v1/sources/:id/versions/:versionId
POST   /api/v1/sources/:id/extract-memories
DELETE /api/v1/sources/:id
GET    /api/v1/jobs
GET    /api/v1/jobs/:id
POST   /api/v1/jobs/:id/retry
GET    /api/v1/memories
GET    /api/v1/memories/:id
PATCH  /api/v1/memories/:id
GET    /api/v1/decisions
GET    /api/v1/decisions/:id
GET    /api/v1/model/provider
GET    /api/v1/model/embedding-provider
GET    /api/v1/model/runs
GET    /api/v1/model/runs/:id
POST   /api/v1/model/embeddings/index
GET    /api/v1/search
POST   /api/v1/answers
```

Portable JSON export/verification, strict empty-database import, previewed non-empty merge/remap,
complete SQLite
backup/verification, and live semantic integrity verification are implemented as local CLI
operations. Import preserves exported domain
identity in one transaction, rebuilds chunks/FTS without extraction, and records the payload hash;
merge remaps every imported identity deterministically after an exact preview digest. Destructive
overwrite is not implemented.

The installed server also has an embedded lifecycle contract: an operator or the experimental
Tauri v2 wrapper can
select an owned data directory, bind port `0`, atomically observe readiness after migrations and
recovery, serve the built web archive from the same origin, and request graceful shutdown. This is
locally verified packaging infrastructure. The wrapper bundles a PyInstaller sidecar and uses a
private shutdown marker, but its unsigned/unqualified installers are not production support.

### Evidence-first notes

Personal notes are not stored in a parallel editor database. They are `Source` rows with kind
`note`, a generated stable `note://` URI, and the same immutable `SourceVersion`, chunk, FTS and
deletion behavior as imported Markdown. Hashtags and `[[wiki links]]` are derived deterministically
from the current version. Each backlink returns the linking source ID, immutable version ID, quote,
offsets and line range. Historical versions remain addressable through the existing source-version
API; no graph database or autonomous mutation is involved.

### Evidence-first learning

Migration 19 adds `study_cards` and append-only `study_reviews`. Card extraction is deterministic:
only an adjacent single-line `Q:`/`A:` pair is accepted, and the answer stores its source identity,
immutable version, exact offsets/lines and quote hash. Re-extraction is idempotent for one version.
A newer source version marks older cards superseded without rewriting them. Review ratings update a
bounded deterministic interval while preserving each before/after interval in a review event.
Deleting the source cascades through both tables and exposes their counts in the deletion preview.

### Human-governed action proposals

Migration 20 adds `action_proposals` and `proposal_citations`. Creation reuses the grounded-answer
pipeline, including provider isolation, bounded repair, server-owned evidence IDs and semantic
support validation. Insufficient evidence or a missing provider never creates a partial proposal.
Each candidate records its model run and copies immutable citation identity, quote hash and exact
span. Human accept/reject changes only proposal governance state and appends an audit event; it has
no write path to sources or governed memories. Deleting any cited source deletes the complete
proposal so a partially evidenced action cannot survive.

### Evidence-first Studio

Migration 21 adds `studio_artifacts` and `studio_citations`. A Studio artifact is keyed by one
immutable source version and artifact kind, making deterministic generation idempotent without
rewriting historical outputs after a source revision. Structured content JSON stores presentation
and interaction state; each item points to an ordinal citation row containing source identity,
immutable version, exact offsets/lines, quote and SHA-256 quote hash.

Nine deterministic renderers are available: audio narration, presentation, video storyboard, mind
map, report, flashcards, quiz, infographic and data table. The web client may speak narration using
the browser's local speech engine, but the API does not claim a rendered audio/video file. Deleting
a source cascades through both Studio tables, and the metadata-only deletion preview reports both
counts. Portable JSON does not yet include these regenerable derived artifacts.

Planned MVP operations (exact contracts remain undecided):

```text
POST   /workspaces
GET    /workspaces/:id/status
POST   /workspaces/:id/sources/scan
GET    /sources/:id/versions/:versionId/spans/:spanId
POST   /workspaces/:id/search
POST   /workspaces/:id/answers
POST   /workspaces/:id/import
```

Write operations should accept an idempotency key. Errors should have stable machine-readable
codes and a safe human-readable message.

## Security and privacy boundaries

- Bind the local service to loopback by default. The checked-in Docker Compose port publishes to
  `127.0.0.1` unless an operator explicitly overrides the bind address and supplies external
  authentication/network controls.
- Treat imported files, Markdown, provider output, and model-generated citations as untrusted.
- Prevent path traversal by resolving all imported paths under registered roots.
- Do not render imported HTML without sanitization.
- Keep provider credentials in OS-backed secret storage where available; define a safe
  development fallback without committing secrets.
- Redact secrets and source content from logs by default.
- Require an explicit setting before any remote model receives content.
- Define deletion transaction boundaries and test cascading derived-data removal.
- Do not add arbitrary tool execution or shell access to model workflows in the MVP.

## Observability

The local product needs useful diagnostics without exporting sensitive content:

- counts and durations by ingestion stage;
- terminal status for every discovered source version;
- stable error codes and retryability;
- provider health and capability checks;
- retrieval channel scores and fusion rank in a debug view;
- citation validation failures;
- local provenance-integrity failures reported as stable content-free codes;
- queue depth and dead-letter count; and
- schema and migration version.

Telemetry leaving the device is deferred and, if introduced, must be opt-in and documented.

## Quality attributes and initial budgets

These are engineering targets to validate, not current performance claims:

| Attribute | MVP target |
| --- | --- |
| Recoverability | Interrupted ingestion can resume without duplicate domain objects |
| Provenance | 100% of answer citations pass deterministic span validation |
| Portability | Verified JSON export plus transactional empty-database import and receipts are implemented; merge import remains open |
| Offline behavior | Search and reviewed-memory browsing work without a network |
| Provider failure | Existing indexed sources remain usable when a model is unavailable |
| Scale envelope | 10,000 Markdown files / 1 GB text on a developer laptop; benchmark required |
| Search latency | p95 under 500 ms for lexical search within the scale envelope |
| Answer diagnostics | Provider, model, retrieved spans, and validation result are inspectable |

## Repository boundaries

```text
apps/
  api/                  implemented FastAPI/SQLAlchemy service and tests
  web/                  implemented React/Vite evidence console
packages/               optional future extraction when boundaries justify it
evals/
  retrieval/            labeled queries and relevance judgments
  grounded-qa/          answers, claims, and source-span judgments
docs/
```

As the backend grows, domain logic should be extracted into provider- and transport-free Python
modules. FastAPI route handlers compose application services; provider SDKs and SQLAlchemy/
SQLite details must not leak into domain rules. The web client consumes the versioned HTTP
contract and must not reproduce backend extraction rules.

## Verification strategy

- Unit tests for offsets, hashes, schemas, status transitions, fusion, and citation validation.
- Contract tests run against each model adapter using recorded or explicitly enabled live
  endpoints; default CI must not require paid credentials.
- A repository security-plugin scan remains open; the threat model, secret scan, E2E hostile-input
  check, and egress assertions are complementary regression evidence, not that external review.
- Integration tests use a temporary workspace and real SQLite migrations.
- Migration tests include a large legacy fixture with provenance-bearing rows, backfill checks,
  idempotent re-open, current reads, search, deletion impact, and cascade deletion.
- Golden fixtures include ADRs with CJK, emoji, CRLF, changed versions, contradictions, and
  superseding decisions.
- API integration and web component tests cover constituent behavior. A credential-free Chromium
  E2E test covers import -> review/correct -> search/debug -> open exact citation -> delete while
  verifying hostile Markdown remains inert and no non-loopback request occurs. Its workflow is
  configured; a hosted CI receipt, Windows run, and production qualification remain open.
- Evaluation results are versioned with dataset version, provider/model configuration, and code
  revision. Benchmark numbers without this context must not be published.
- The current `seed-v2` retrieval gate runs real migrations, ingestion, and FTS5 retrieval for 26
  synthetic Unicode and version-aware queries. Initial/current revision pairs include positive
  current-term and expected-empty superseded-term cases; expected-empty accuracy is reported
  separately from positive-query ranking metrics.
- The deterministic extraction gate covers all four memory kinds, exact evidence/hash resolution,
  supported English/Vietnamese markers, CJK statements after markers, and negative prose. Neither
  synthetic gate is real-model or pilot evidence.

## Evolution after the vertical slice

Only after quality gates pass should the project add Git metadata/GitHub, PDF parsing, meeting
transcripts, team workspaces, or desktop packaging. Cloud sync, enterprise governance, and a
commercial control plane require separate architecture and threat-model decisions.
