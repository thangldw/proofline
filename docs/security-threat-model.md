# Proofline Security Threat Model

**Document status:** Baseline threat model

**Scope:** Local single-user pre-alpha runtime

**Last reviewed:** 2026-07-12

## Overview

Proofline imports engineering documents into a local FastAPI service, stores source content and
derived evidence in SQLite, exposes a browser UI, and can optionally send bounded source context
to an OpenAI-compatible generation or embedding endpoint. The most important assets are source
confidentiality, provider credentials, immutable source identity, exact evidence spans, deletion
integrity, and the distinction between untrusted model output and accepted memory.

The supported deployment is a single trusted user on one machine. The development API is not an
authenticated multi-user or internet-facing service. Team authorization, cloud sync, public
hosting, and hostile co-tenancy are outside the current runtime assumptions and require a new
threat model before implementation.

## Threat Model, Trust Boundaries, and Assumptions

### Assets and security objectives

- Imported source text, historical versions, chunks, embeddings, and derived memory remain local
  unless remote model egress is explicitly enabled.
- API keys are read from process environment and never persisted in model-run, job, or audit
  records.
- Every citation continues to resolve to the immutable source version and exact span it names.
- Model output cannot create accepted memory or invent evidence identifiers.
- Deleting a source removes content-bearing derived records and search indexes in the documented
  scope.
- Diagnostic records expose safe error categories without copying source contents or prompts.

### Trust boundaries

1. **Local filesystem to ingestion.** File names, paths, bytes, encoding, size, symlinks, and
   Markdown content are untrusted input even when selected by the local user. Folder import is
   limited to explicitly registered roots; resolved paths must remain beneath those roots.
2. **Browser to local API.** Requests are untrusted. CORS restricts browser origins, but CORS is
   not authentication and does not protect an API deliberately exposed to a network.
3. **API to SQLite/FTS.** Source text and search queries cross into persistence and FTS5. SQL must
   remain parameterized, foreign keys enabled, migrations explicit, and source deletion complete.
4. **API to model provider.** Prompts contain sensitive source spans. Non-loopback endpoints are
   disabled unless `PROOFLINE_ALLOW_REMOTE_AI=true`; credentials and full prompts must not enter
   logs or persisted diagnostics.
5. **Model output to domain state.** Provider responses are attacker-controlled structured data.
   Schemas, bounded identifiers, exact-span validation, candidate status, and human review form
   the acceptance boundary.
6. **Imported content to browser rendering.** Source text may contain HTML, scripts, misleading
   instructions, or oversized content. React text rendering must remain escaped; raw HTML or
   executable Markdown rendering is not permitted without sanitization and a separate review.
7. **Repository and CI.** Dependencies, container bases, workflow actions, and contributor changes
   are developer-controlled supply-chain inputs. CI credentials must remain least privilege and
   generated artifacts must not contain local data or secrets.

### Actors and assumptions

- The local operator controls configuration, registered import roots, and provider selection.
- Document authors may be untrusted and may attempt prompt injection, stored XSS, parser abuse, or
  misleading evidence.
- A configured remote provider can observe every span sent to it; Proofline cannot enforce the
  provider's retention policy.
- A process with read access to the SQLite database or environment already has local-user-level
  access. Database encryption and operating-system compromise are outside the current MVP.
- The application does not claim authentication, authorization, tenancy isolation, or protection
  when bound to an untrusted network interface.

## Attack Surface, Mitigations, and Attacker Stories

### Local files and paths

Relevant attacks include path traversal, symlink escape, special files, excessive file size,
encoding failures, rename/delete confusion, and content that changes between discovery and read.
Folder scanning must use resolved paths beneath a registered root, accept only regular supported
files, cap file size, report partial failures, and never silently delete a missing source. Stable
file URIs and immutable content hashes prevent a changed file from repointing historical evidence.

### Local HTTP API and browser UI

Relevant attacks include cross-origin writes, accidental network exposure, oversized requests,
FTS/query injection, unescaped imported content, and denial of service through expensive search or
model calls. Existing controls include Pydantic bounds, parameterized SQL/FTS handling, a narrow
default CORS origin, React's escaped text rendering, and loopback defaults in both the CLI and
Docker Compose host-port binding. Operators overriding that binding must supply their own network
and authentication controls. Authentication, CSRF protection, rate limiting, and hostile
multi-user isolation are not implemented.

### Persistence, provenance, and deletion

The highest-impact integrity story is a citation or approved decision silently pointing at new or
incorrect source text. Source versions, hashes, exclusive offsets, quote hashes, and server-owned
evidence IDs mitigate this. Tests must cover Unicode offsets, historical versions, FTS cleanup,
embeddings, audit records, and orphan removal. Migration failure, interrupted jobs, and incomplete
deletion remain important failure classes because the local database is the authoritative memory.

### Model providers and prompt injection

An imported document can instruct the model to ignore schemas, cite unknown chunks, or disclose
other context. Proofline treats source text and provider output as data: context is bounded,
structured output is validated, citations must name server-issued IDs, derived decisions enter as
candidates, and provider failures must leave lexical retrieval usable. These controls do not make
remote egress private; the explicit egress switch and operator review remain required.

### Secrets and diagnostics

Provider keys can leak through logs, exception strings, persisted prompts, screenshots, fixtures,
or CI configuration. Model runs persist identifiers, hashes, token counts, latency, and safe error
codes only. Ingestion jobs must not persist source content in failure details. CI should scan
tracked changes for secret-like material, and any exposed credential must be rotated even if the
commit is later removed.

### Out-of-scope attacker stories

- Internet attackers reaching an intentionally public deployment are outside the supported
  pre-alpha configuration; such exposure is unsafe rather than a low-severity supported mode.
- Cross-tenant data access is not currently applicable because workspaces and team tenancy are not
  implemented.
- A fully compromised local OS, browser profile, or user account can read the same files and
  environment as Proofline and is outside the application's protection boundary.

## Severity Calibration (Critical, High, Medium, Low)

### Critical

- Default or non-consensual remote exfiltration of imported source content or provider credentials.
- A path escape that lets a remote or cross-origin caller read arbitrary local files in a supported
  configuration.
- Systemic provenance corruption that makes fabricated evidence appear immutable and accepted.

### High

- Folder import escaping a registered root or following a symlink to sensitive files.
- Unknown model citations becoming persisted accepted memory, or source deletion leaving
  searchable content/embeddings behind.
- Stored script execution from imported content in the local browser origin.
- An unauthenticated state-changing API exposed beyond loopback by a supported default.

### Medium

- A crafted document or query causing repeatable local denial of service within documented size
  limits.
- Diagnostics leaking file paths, prompt fragments, or sensitive metadata without full source
  disclosure.
- A crash leaving jobs permanently misleading or causing deterministic updates to be skipped.

### Low

- Minor information disclosure limited to non-sensitive identifiers already visible to the local
  operator.
- UI-only provenance ambiguity that does not alter stored evidence but could mislead review.
- Developer-tool or documentation issues that require trusted repository write access and do not
  affect distributed artifacts.

Severity moves upward when a flaw crosses a trust boundary by default, affects source
confidentiality or accepted-memory integrity, survives deletion, or requires no local operator
action. It moves downward when exploitation requires an already compromised local account or an
explicitly unsupported public deployment.
