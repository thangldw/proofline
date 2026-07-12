# Changelog

Notable user-visible and operator-visible changes will be recorded in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Proofline is pre-alpha, has no supported release, and does not yet promise
semantic-versioning compatibility.

## [Unreleased]

### Added

- Local Markdown and UTF-8 text ingestion with immutable source versions, exact
  source spans, observable ingestion jobs, retry handling, registered-root scans,
  and deletion impact previews with derived-data cleanup.
- A governed memory registry for decisions, assumptions, constraints, and
  alternatives. Memories retain exact evidence and support correction plus
  reversible review states.
- Lexical retrieval with optional local dense retrieval and reciprocal-rank
  fusion, grounded answers with exact citations, context-budget exclusions, and
  retrieval diagnostics.
- Safe model-run list, detail, and repair-lineage API endpoints. A dedicated
  metadata-only web screen provides filters, detail, and parent/current/child lineage without
  rendering private model payloads.
- Verified portable JSON export and SQLite backup workflows, including separate
  verification commands and documented recovery steps. Portable import remains
  unimplemented.
- A credential-free platform smoke script and a configured GitHub Actions matrix
  for Ubuntu and macOS. A versioned receipt records successful API CI and Secret
  Scan runs for revision `0dde53f`, including both platform jobs and browser E2E.
- Community health files, contribution guidance, a code of conduct, and private
  security-reporting guidance for the pre-alpha repository.
- Exact-set confirmed missing-source deletion with drift/error checks and the existing complete
  derived-data cascade.
- Source-ID and indexed-time scopes for search and grounded answers.
- Credential-free deterministic extraction and retrieval v2 regression gates. Retrieval v2 covers
  26 Unicode and current/superseded-revision queries; neither gate is real-model or pilot evidence.
- A Chromium vertical-path E2E test for provenance navigation, governed correction, deletion,
  hostile-content inertness, and non-loopback egress detection. Its hosted workflow is configured,
  not claimed as successfully run.

### Changed

- Deterministic and provider-backed extraction now use the same governed memory
  model and provenance rules.
- Runtime answers expose evidence and retrieval exclusions rather than silently
  dropping context that does not fit the answer budget.
- Docker Compose publishes the unauthenticated API to loopback by default.
- Migration coverage now includes a large legacy provenance/backfill fixture and current
  search/deletion behavior after upgrade.

### Security

- The web console now uses system fonts without external font requests, and its
  test/build pipeline rejects unapproved external URLs in shipped web assets.
- Private reporting and coordinated-disclosure guidance is documented in
  `SECURITY.md`.

### Known limitations

- Proofline remains pre-alpha with no supported release or production support.
- Portable import, scalable vector indexing, reranking, Windows verification, production support,
  a repository security-plugin scan, real-model quality qualification, and external pilot gates
  are still open.

When preparing the first tagged alpha, review these entries and link their pull
requests or issues. Every entry must describe observable behavior; planned
behavior must not appear as shipped.
