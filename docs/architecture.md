# Proposed MVP Architecture

**Document status:** Evolving  
**Implementation status:** Foundation API/web vertical slice implemented; later stages planned  
**Decision record:** [ADR-0001](./adr/0001-scope-and-stack.md)

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
                 retrieve -> rerank -> answer
                           |
                           v
                exact citations + labels
```

A slice is complete only when a fixture source can move through this flow, a user can inspect
its processing state, and an answer citation resolves to the original source version and span.

## Planned components

### 1. Local API service — implemented foundation

`apps/api` is a Python 3.11+ FastAPI service using Pydantic, SQLAlchemy, and SQLite. It currently
owns configuration, Markdown chunking, content ingestion, source/decision/evidence persistence,
deterministic marked-decision extraction, immutable source versions, committed schema migrations,
source retrieval and deletion, FTS5 search, overview counts, and health reporting. Local
development runs through Uvicorn.

The deterministic ingestion path is synchronous and has no required model dependency. Optional
generation and embedding providers use the same immutable evidence contract.

### 2. Local web application — implemented foundation

`apps/web` is a React/Vite evidence console. It currently supports browser-side Markdown/text
upload to the API, lexical search, source inventory, decision browsing, overview counts, and an
evidence drawer plus accept/reject/obsolete decision actions. Grounded answer statements retain
their statement-level citation mapping, and an answer-provider failure does not discard lexical
results. It is a pre-alpha inspection surface, not a rich editor. The API also supports decision
corrections with a before/after audit trail. Provider configuration remains environment-based;
there is no settings UI. Evidence navigation loads the immutable referenced source version.
Desktop packaging is deferred.

### 3. Future application modules

The service will grow through internal interfaces rather than provider-specific product logic.
Planned modules are:

- workspace and source catalog;
- ingestion coordinator;
- retrieval and answer service;
- memory review service;
- provider gateway;
- job status and diagnostics; and
- deletion and export service.

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

### 5. Storage

The foundation uses SQLite plus content uploaded from the browser or API:

- Browser-selected files remain in their original location; the web client reads their text and
  sends the content to the local API.
- The API can scan explicitly registered local roots for Markdown and UTF-8 text. It resolves
  every selected path before reading, rejects traversal and symlink escape, and never accepts an
  arbitrary unregistered root. Folder watching and automatic deletion remain unimplemented.
- SQLite currently stores sources, raw Markdown/text, chunks, deterministic decisions, evidence,
  character/line spans, and FTS rows through SQLAlchemy models plus an FTS5 virtual table.
- SQLite FTS5 currently provides lexical search.
- Source versions, versioned schema migrations, resumable ingestion jobs with private staged
  input, and decision audit events are implemented; generalized derived memory remains planned.
- A metadata-only deletion-impact endpoint counts every source-owned version, chunk, embedding,
  decision, evidence link, audit event, FTS row, and ingestion job that will be detached. Confirmed
  deletion removes content-bearing derived rows and preserves only detached safe job diagnostics.
- Versioned chunk embeddings are implemented in a local SQLite table with provider/model,
  dimensions, content hash, and immutable source-version ownership. Indexing is incremental.
  Dense search currently uses bounded in-process cosine scoring; a SQLite vector extension or
  dedicated local index must replace it before claiming the 10,000-file scale envelope.

No graph database is planned for the MVP. Typed relations are represented as adjacency rows
and queried through the domain repository.

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

The response reports every processed file and any source IDs whose files are missing. Missing-file
deletion is preview-only even when `delete_missing=true`; no source is removed by a folder scan.

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

Structured results are parsed as untrusted data and validated against versioned schemas. Invalid
results persist a failed model run without creating memory. Retry and dead-letter execution remain
planned. Provider errors must not corrupt existing source or memory records.

Model-assisted decision extraction is implemented as a separate source action. Candidates must
cite known chunks from the current immutable source version, are deduplicated per version, retain
the generating `ModelRun`, and always enter the governed review flow as `candidate`. Unknown
evidence fails the run before any memory object is persisted. Assumption/constraint extraction and
repair retries remain planned.

### 7. Retrieval and answering

Lexical FTS5 retrieval, dense cosine retrieval, reciprocal-rank fusion, and the guarded answer path
are implemented. The current path builds a bounded evidence pack, requests typed statements plus
evidence IDs, rejects unknown/missing IDs, resolves citations server-side, and revalidates exact
spans against immutable source versions. When no provider is configured, it returns verified
evidence without synthesizing claims. Cross-encoder reranking, diversity control, and automated
repair retries remain planned. The target full path is:

1. normalize the question and optional filters;
2. run lexical and semantic retrieval independently;
3. fuse ranked results using reciprocal-rank fusion;
4. filter by source version, workspace, and deletion state;
5. optionally rerank through a configured capability;
6. select diverse evidence within a bounded context budget;
7. generate an answer constrained to evidence identifiers;
8. validate that every cited identifier exists and its quoted span matches stored content;
9. label statements as direct, synthesis, inference, or insufficient evidence.

If answer validation fails, the service should retry with a repair prompt within a fixed limit,
then return a qualified failure rather than ungrounded prose.

## Domain model

The names below describe the target MVP. Current SQLAlchemy models and SQLite setup in `apps/api`
remain the source of truth for implemented records. `Source`, `Chunk`, `Decision`, and `Evidence`
exist now; `SourceVersion`, `ModelRun`, `IngestionJob`, and `AuditEvent` are also implemented.
Generalized `MemoryObject` and `Relation` remain planned.

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
  input_hashes, validation_status, started_at, finished_at

Job
  id, kind, state, stage, attempts, error_code, error_detail, timestamps

AuditEvent
  id, actor, action, object_type, object_id, before_json, after_json, created_at
```

Allowed MVP memory kinds are `claim`, `decision`, `assumption`, `constraint`, and
`alternative`. Allowed statuses are `candidate`, `accepted`, `rejected`, `obsolete`, and
`deleted`. Candidate model output never becomes accepted solely because a model emitted it.

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
POST   /api/v1/folder-scans
GET    /api/v1/sources
GET    /api/v1/sources/:id
GET    /api/v1/sources/:id/deletion-impact
DELETE /api/v1/sources/:id
GET    /api/v1/jobs
GET    /api/v1/jobs/:id
POST   /api/v1/jobs/:id/retry
GET    /api/v1/decisions
GET    /api/v1/decisions/:id
GET    /api/v1/search
POST   /api/v1/answers
```

Planned MVP operations (exact contracts remain undecided):

```text
POST   /workspaces
GET    /workspaces/:id/status
POST   /workspaces/:id/sources/scan
GET    /sources/:id/versions/:versionId/spans/:spanId
GET    /workspaces/:id/memories?status=candidate
PATCH  /memories/:id
POST   /workspaces/:id/search
POST   /workspaces/:id/answers
DELETE /sources/:id
POST   /workspaces/:id/export
```

Write operations should accept an idempotency key. Errors should have stable machine-readable
codes and a safe human-readable message.

## Security and privacy boundaries

- Bind the local service to loopback by default.
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
- queue depth and dead-letter count; and
- schema and migration version.

Telemetry leaving the device is deferred and, if introduced, must be opt-in and documented.

## Quality attributes and initial budgets

These are engineering targets to validate, not current performance claims:

| Attribute | MVP target |
| --- | --- |
| Recoverability | Interrupted ingestion can resume without duplicate domain objects |
| Provenance | 100% of answer citations pass deterministic span validation |
| Portability | Workspace export uses documented, non-provider-specific records |
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
- Integration tests use a temporary workspace and real SQLite migrations.
- Golden fixtures include ADRs with CJK, emoji, CRLF, changed versions, contradictions, and
  superseding decisions.
- End-to-end tests cover import -> inspect -> review -> ask -> open citation -> delete.
- Evaluation results are versioned with dataset version, provider/model configuration, and code
  revision. Benchmark numbers without this context must not be published.
- The implemented `seed-v1` retrieval gate runs real migrations, ingestion, and FTS5 retrieval for
  15 synthetic questions. Its baseline Recall@10, nDCG@10, and MRR are `0.80`; three explicit
  lexical misses document the semantic-retrieval gap. This is regression evidence, not pilot
  evidence.

## Evolution after the vertical slice

Only after quality gates pass should the project add Git metadata/GitHub, PDF parsing, meeting
transcripts, team workspaces, or desktop packaging. Cloud sync, enterprise governance, and a
commercial control plane require separate architecture and threat-model decisions.
