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
  model-run web screen is not yet available.
- Verified portable JSON export and SQLite backup workflows, including separate
  verification commands and documented recovery steps. Portable import remains
  unimplemented.
- A credential-free platform smoke script and a configured GitHub Actions matrix
  for Ubuntu and macOS. This records the checked-in automation, not a claim that
  hosted CI has completed successfully.
- Community health files, contribution guidance, a code of conduct, and private
  security-reporting guidance for the pre-alpha repository.

### Changed

- Deterministic and provider-backed extraction now use the same governed memory
  model and provenance rules.
- Runtime answers expose evidence and retrieval exclusions rather than silently
  dropping context that does not fit the answer budget.

### Security

- The web console now uses system fonts without external font requests, and its
  test/build pipeline rejects unapproved external URLs in shipped web assets.
- Private reporting and coordinated-disclosure guidance is documented in
  `SECURITY.md`.

### Known limitations

- Proofline remains pre-alpha with no supported release or production support.
- Portable import, reranking, a dedicated model-run web screen, Windows platform
  verification, real-model quality qualification, and external pilot gates are
  still open.

When preparing the first tagged alpha, review these entries and link their pull
requests or issues. Every entry must describe observable behavior; planned
behavior must not appear as shipped.
