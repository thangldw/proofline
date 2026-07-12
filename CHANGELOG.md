# Changelog

Notable user-visible and operator-visible changes will be recorded in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Proofline is pre-alpha, has no stable supported release, and does not yet promise
semantic-versioning compatibility between pre-releases.

## [Unreleased]

No changes have been recorded after `v0.1.0-alpha.5`.

## [0.1.0-alpha.5] - 2026-07-13

### Added

- A read-only `proofline verify-integrity` command checks live SQLite provenance invariants and
  emits only counts or stable content-free failure codes.

### Fixed

- Inference statements now require exact evidence IDs and use the same bounded repair path as
  direct and synthesis statements.

## [0.1.0-alpha.4] - 2026-07-13

### Added

- An opt-in single-process polling watcher scans explicitly registered folders immediately and at a
  bounded interval, exposes content-free lifecycle counters, never confirms deletion, and shares a
  coordinator with manual scans so ingestion cycles cannot overlap within the API process.

### Fixed

- Registered-folder scans no longer create ingestion jobs for unchanged files.
- Files that change while being read fail explicitly and leave source versions, evidence, and jobs
  untouched so a later stable scan can retry safely.

## [0.1.0-alpha.3] - 2026-07-13

### Added

- A strict schema-v1 portable JSON import command restores exported domain records into an empty
  database in one transaction, preserves exact IDs/history/evidence, rebuilds chunks and FTS
  without re-running extraction, and records a unique payload-hash receipt.
- A versioned credential-free pilot simulation exercises seven scripted engineering-context tasks
  across five invented personas and records citation/source-inspection metrics with explicit
  simulation-only qualification.

### Security

- Portable export verification now bounds input size and validates scalar types, enums, numeric
  ranges, timezone-aware timestamps, JSON depth, model lineage, and exact provenance before import.
- Import rejects non-empty targets and rolls back on any write, index, constraint, or final
  payload-equivalence failure without exposing source content in its error contract.

## [0.1.0-alpha.2] - 2026-07-13

### Fixed

- Release builds now install into the repository-local virtual environment expected by the
  quality commands, then smoke-test the wheel in a second clean environment.
- A manually dispatched recovery path rebuilds an existing immutable tag without moving it and
  proves that the tag resolves to a commit contained in `main`.
- Tagged-source secret scanning now receives the exact tagged SHA instead of relying on an empty
  tag-push commit list.
- Artifact verification/build runs with read-only repository access, while the separate publish
  job receives the narrowly scoped release-write permission and an explicit repository target.

## [0.1.0-alpha.1] - 2026-07-13

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
  hostile-content inertness, and non-loopback egress detection. The versioned CI receipt records
  its successful hosted run at revision `0dde53f`.

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

Future releases must move reviewed entries out of `Unreleased`, describe only observable behavior,
and keep planned behavior out of shipped release notes.

[Unreleased]: https://github.com/thangldw/proofline/compare/v0.1.0-alpha.5...HEAD
[0.1.0-alpha.5]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.5
[0.1.0-alpha.4]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.4
[0.1.0-alpha.3]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.1
