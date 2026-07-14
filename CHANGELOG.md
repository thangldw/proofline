# Changelog

Notable user-visible and operator-visible changes will be recorded in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Proofline is pre-alpha, has no stable supported release, and does not yet promise
semantic-versioning compatibility between pre-releases.

## [Unreleased]

No changes have been recorded after `v0.14.14`.

## [0.14.14] - 2026-07-14

### Added

- Add portable export schema v2 for workspace-scoped chunks, study cards and append-only reviews,
  grounded action proposals and citations, and Evidence Studio artifacts and citations.
- Add deterministic all-ID remapping for every new portable collection and preserve exact source
  spans through empty-database restore and non-empty merge.

### Changed

- Preserve chunk identities directly instead of rebuilding them with new IDs during import.
- Upgrade verified schema-v1 exports in memory so older core snapshots remain restorable.

### Validation

- Cover full study scheduling, reviewed proposal and Studio artifact round trips, v1 upgrade,
  tamper rejection, atomic rollback and no-overwrite merge behavior.

## [0.14.13] - 2026-07-14

### Added

- Add `proofline launch` for a loopback-only dynamic-port installed-wheel experience that opens the
  bundled UI in the default browser.
- Resolve owned application state to macOS Application Support, Windows Local AppData or the Linux
  XDG data directory, with an explicit override for testing and recovery.

### Changed

- Default the launcher to OS-backed provider secrets on macOS and Windows while preserving explicit
  secret-store overrides.
- Publish and clean launcher readiness metadata inside the selected application data directory.

## [0.14.12] - 2026-07-14

### Changed

- Publish the GitHub repository as a public experimental pre-alpha project after explicit owner
  approval.
- Verify the public repository description, topics, Issues setting and `main` default branch.
- Update release and readiness documentation to distinguish public availability from production
  qualification.

## [0.14.11] - 2026-07-14

### Added

- Add a root support policy covering the supported experiment, safe issue reports, data-loss
  escalation, operator backup responsibility, upgrade/database rollback and release cadence.
- Add a maintainer document naming the current pre-alpha owner and recording unassigned production
  signing, updater, incident-response, retention, evaluation and pilot responsibilities.

### Changed

- Narrow the remaining public-repository gate to the external GitHub visibility decision.
- Distinguish complete pre-alpha operational documentation from unaccepted production support
  commitments.

## [0.14.10] - 2026-07-14

### Added

- Add `proofline restore-backup` for verified, atomic SQLite restore with a required rollback copy
  when replacing an existing database.
- Add installed-release receipt observations for restoring a backup and reversing that restore
  from the preserved rollback database.

### Changed

- Refuse restore when SQLite sidecars suggest the target has not been cleanly stopped, when paths
  overlap, or when the rollback destination already exists.
- Publish restored databases with owner-only permissions and verify the exact schema after atomic
  replacement.

### Validation

- Cover the full old-state restore and new-state rollback round trip, safe path/sidecar refusal,
  CLI targeting and installed-package smoke behavior.

## [0.14.9] - 2026-07-14

### Added

- Add opt-in operating-system keyring storage for generation and embedding API keys, backed by
  macOS Keychain and Windows Credential Locker through the installed `keyring` dependency.
- Expose the active secret-storage mode and explicit key removal controls in Settings.
- Add OS-keyring set/read/delete observations to local platform release receipts.

### Changed

- Migrate legacy file-stored keys to the OS keyring on the next successful settings save and keep
  non-secret provider configuration in the owner-only JSON file.
- Roll back file and keyring mutations together when provider validation fails.

### Validation

- Cover migration, replacement, removal, secret-free JSON persistence and transactional rollback.
- Exercise the real macOS Keychain backend during the local installed-wheel release gate.

## [0.14.8] - 2026-07-14

### Added

- Add an atomic platform-release qualification receipt that binds an installed wheel SHA-256 and
  Git revision to the observed OS, architecture, Python and Proofline versions.
- Exercise installed server lifecycle, bundled web, exact evidence, portable export/import,
  SQLite backup/restore and semantic integrity in the same receipt.

### Changed

- Upload the platform receipt as a checksummed local GitHub Release asset.

### Validation

- Cover successful receipt generation, artifact identity, qualification boundaries and safe
  refusal to overwrite an existing receipt.

## [0.14.7] - 2026-07-14

### Added

- Add an evidence-based production-readiness matrix for the first supported local desktop profile.

### Changed

- Remove contributor-machine absolute paths from Studio design QA evidence.
- Update the security support table and alpha boundary to the current pre-alpha release.
- Correct the portability documentation to cover the explicit no-overwrite merge workflow that
  has been implemented since `v0.8.0`.
- Mark all `v0.x` local GitHub releases as pre-releases so release metadata matches the documented
  support boundary.

## [0.14.6] - 2026-07-13

### Added

- Add explicit `--allow-mock` preflight and comparison CLI paths backed by an in-process scripted
  provider that never calls remote or local model transports.
- Add versioned synthetic extraction, grounded-QA and local/remote comparison fixtures for running
  the complete model-evaluation pipeline without a working provider credential.

### Changed

- Mock preflight receipts now state that they prove scripted wiring and frozen fixture identity,
  not endpoint readiness or model quality.
- Keep mock execution opt-in and preserve `mock_integration` qualification on comparison receipts.

### Validation

- Cover the explicit mock boundary, credential non-persistence, scripted provider execution and
  CLI receipt output while retaining the guard against accidental mock execution.

## [0.14.5] - 2026-07-13

### Added

- Add an evidence-first Studio with audio narration, presentation, video storyboard, mind map,
  report, flashcard, quiz, infographic and data-table artifacts.
- Persist deterministic artifacts per immutable source version through migration 21, with exact
  citation offsets, line ranges and SHA-256 quote hashes.
- Add responsive pastel Studio cards, saved-artifact browsing, interactive quiz/flashcard/slide
  previews, browser-local narration and exact-evidence inspection.

### Changed

- Source deletion preview and cascade now include Studio artifacts and their citations.
- Media-heavy outputs remain honest local previews: the release does not claim downloadable audio,
  rendered video or production presentation-file export.

### Validation

- Add backend coverage for all nine artifact kinds, idempotency, source revisions, workspace scope
  and deletion; add frontend interaction coverage and browser design QA at 746 × 860.

## [0.14.4] - 2026-07-13

### Added

- Run preflighted local/remote providers through the production memory-extraction and grounded-QA
  paths with per-provider failure isolation.
- Record extraction metrics by memory kind, exact evidence resolution, citation precision,
  abstention accuracy, transport latency, provider-reported tokens and estimated cost.
- Support explicitly mock-qualified integration comparisons through injected test transport while
  preventing mock manifests from using real transport accidentally.

### Validation

- Add a balanced mock corpus covering positive extraction, negative extraction, grounded citation
  and insufficient-evidence abstention.
- Keep mock receipts permanently distinct from real-model and external-pilot evidence.

## [0.14.3] - 2026-07-13

### Added

- Add a versioned real-model comparison preflight manifest requiring local and remote providers.
- Persist dataset hashes, declared model revisions, prompt versions, pricing and explicit readiness
  blockers without storing provider credentials.
- Add an atomic `eval-real-model-preflight` CLI receipt with non-zero exit status when any provider
  is unavailable or a remote credential is missing.

### Documentation

- Record the metric contract and explicitly distinguish preflight readiness from model-quality or
  pilot evidence.

## [0.14.2] - 2026-07-13

### Added

- Local Notes filtering by title or deterministic hashtag.
- Notes list every immutable source revision with version number and content length.
- A read-only historical revision preview loads through the workspace-scoped source/version API
  and displays a shortened immutable content hash.

### Documentation

- Study/proposal portable JSON is explicitly deferred because it requires validator, canonical
  ordering and full merge/remap graph changes rather than a safe incremental patch.

## [0.14.1] - 2026-07-13

### Added

- Notes now expose deterministic tags, resolved/unresolved wiki-links and backlinks with exact line
  and immutable source-version identity directly in the UI.
- Study review history is readable through a workspace-scoped API.

### Fixed

- Title-only note edits update metadata without creating a fake immutable content revision or
  changing the content ingestion timestamp.
- The Study navigation count and review queue now include only cards whose due time has arrived.

## [0.14.0] - 2026-07-13

### Added

- Grounded action proposals generated through the existing provider-neutral answer pipeline; only
  successfully grounded output can become a persisted candidate.
- Every proposal retains its model run plus immutable chunk/source/version citations, exact spans
  and quote hashes.
- A Third Brain review surface and append-only audit events for explicit human accept/reject.

### Changed

- Proposal acceptance is governance state only and never mutates source content or accepted memory.
- Deleting any cited source removes the complete dependent proposal and reports proposal/citation
  counts in the deletion preview, avoiding partially grounded artifacts.

## [0.13.0] - 2026-07-13

### Added

- Deterministic study-card derivation from explicit adjacent `Q:` and `A:` source lines; every
  answer records its immutable source version, exact offsets/lines and SHA-256 quote hash.
- A Learning Brain review screen with answer reveal, evidence locator and four deterministic
  review ratings.
- Persistent append-only review history, due dates and intervals through migration 19.

### Changed

- Re-deriving after a source revision supersedes prior-version cards while keeping their evidence
  and review history; superseded cards cannot receive new reviews.
- Source deletion preview now reports study cards and review events covered by cascade deletion.

## [0.12.0] - 2026-07-13

### Added

- Evidence-first Markdown quick capture with stable `note://` identities and immutable content
  revisions that reuse the existing indexing, backup and deletion contracts.
- Deterministic hashtags and `[[wiki links]]` with exact offsets and line numbers, plus current-note
  backlink resolution carrying the immutable linking source version.
- A focused Notes workspace for capture and revision without introducing a rich-text editor.

### Quality

- API coverage proves revision history, exact link spans, backlinks, search, workspace isolation and
  deletion; web coverage proves capture and revision workflows.
- ADR 0004 bounds the planned Learning Brain, Third Brain AI and Team Brain milestones.

## [0.11.0] - 2026-07-13

### Added

- Python release artifacts now contain the reviewed web UI and serve it by default, enabling a
  one-command local application without Node.js at runtime.
- `proofline serve --no-web` provides an explicit API-only mode, while `--web-dir` can still select
  a reviewed external build.
- Release smoke now starts the cleanly installed wheel, checks its UI and API, and proves graceful
  shutdown before a tag can be published.
- The pre-alpha support boundary and evidence required for a future alpha claim are documented.

### Changed

- The quality gate rejects a Python web bundle that differs from the current production Vite build.

## [0.10.0] - 2026-07-13

### Added

- The local server can bind an OS-selected port, publish atomic machine-readable readiness, use an
  owned data directory, and serve the built web archive from the API process.
- The installed `proofline` entry point applies the data directory before database and provider
  configuration are initialized.

### Changed

- `SIGTERM` and `SIGINT` now drive a graceful watcher/API shutdown and remove the readiness file.
- `/health` reports the running Proofline version.

### Quality

- Subprocess coverage proves start, migrate, ready, same-origin web/API access, graceful stop, and
  cleanup without external services.
- A screenshot-backed launch-flow audit and source-backed receipt metadata report document the
  remaining accessibility and evidence-quality follow-ups.

## [0.9.1] - 2026-07-13

### Changed

- The web app now uses a bright Sky + Mint theme with ice-blue surfaces, aqua navigation,
  accessible azure actions, mint provenance states, and navy typography.
- Theme colors are consolidated into semantic CSS variables across search, decisions, sources,
  settings, diagnostics, model runs, warnings, and failure states.
- Mobile navigation and search controls no longer cause horizontal overflow at a 390 px viewport.

### Quality

- Browser comparison covers the selected visual target, desktop and mobile empty states, primary
  navigation, console output, responsive overflow, and WCAG AA contrast for core color pairs.

## [0.9.0] - 2026-07-13

### Added

- The web app now discovers local workspaces and sends the selected workspace boundary on every
  API request, making the v0.7 backend isolation usable without custom headers.
- A reproducible 1,000-file watcher benchmark records initial, no-op and one-update latency,
  memory, storage, platform and a predeclared native-notification decision rule.

### Changed

- Polling remains the watcher default: three no-op samples measured 404, 403 and 402 ms locally,
  below the predeclared 1,000 ms threshold. Native notifications remain unnecessary complexity at
  the measured scale; Windows and network filesystems are explicitly not qualified by this receipt.

## [0.8.0] - 2026-07-13

### Added

- Portable exports can be previewed and merged into a non-empty database through deterministic
  all-ID remapping, with source identities and every provenance reference rewritten consistently.
- Merge apply requires the exact preview digest, rejects changed targets and duplicate payloads,
  never overwrites existing records, and owns a rollback savepoint for import failures.
- The CLI exposes `proofline import --preview-merge` followed by explicit `--merge
  --preview-sha256 DIGEST`; reports contain IDs and counts but no source content.

### Changed

- Release tag pushes no longer start GitHub Actions automatically. Maintainers can run the guarded
  `make release-local TAG=vX.Y.Z` path to test, build, smoke-check, tag, and publish from a local
  machine when hosted Actions quota is unavailable.

## [0.7.0] - 2026-07-13

### Added

- A local workspace API and `X-Proofline-Workspace-ID` request boundary scope sources, ingestion
  jobs, search, grounded answers, decisions, model runs, audit history, Git imports, and deletion.
- SQLite-backed expiring folder-scan leases prevent overlapping scans across API workers while
  preserving the existing in-process coordinator and explicit `scan_in_progress` failure.
- Migration 17 backfills all existing records into the immutable default local workspace;
  migration 18 adds durable worker leases without requiring an external service.

## [0.6.0] - 2026-07-14

### Added

- A provider-neutral reranker interface, optional deterministic post-RRF reranking, and an HTTP
  cross-encoder adapter with rank/score diagnostics.
- Statement support assessment reports `supported` or `uncertain` and rejects direct negation
  contradictions through the existing bounded repair contract.
- A SQLite locality-sensitive vector band index narrows semantic candidates before exact cosine
  scoring and is covered by migration backfill, integrity verification, and deletion impact.
- Versioned synthetic receipts record reranker MRR and 1,000-source vector index latency, memory,
  storage, and no-op update cost without making 10,000-file or 1-GB claims.

## [0.5.0] - 2026-07-14

### Added

- A local Settings screen configures Qwen, DeepSeek, Ollama, vLLM, and generic
  OpenAI-compatible generation/embedding profiles without returning stored API keys.
- Separate generation, embedding, and reranking capability health states plus visible degraded
  mode preserve deterministic ingestion and lexical retrieval when models are unavailable.
- Transient model transport calls use three bounded attempts; exhaustion persists a dead-letter
  run that can be explicitly retried against the same immutable input and exact provider/model.

### Security

- Provider configuration is written atomically with owner-only permissions. Remote egress remains
  opt-in and retries never fall back to a different provider.

## [0.4.0] - 2026-07-14

### Added

- Typed temporal decision relations for `supersedes`, `implements`, `contradicts`, `based_on`, and
  `considered`, with validity windows, audit history, timeline API/UI, and candidate diagnostics.
- Superseding a decision atomically closes the prior decision's validity and marks it obsolete.

### Changed

- Retrieval demotes evidence owned by expired or obsolete decisions while preserving lexical and
  semantic relevance ordering among current and neutral sources.

## [0.3.0] - 2026-07-13

### Added

- Read-only local Git repository ingestion resolves revisions to immutable commits and indexes
  tracked Markdown/text files plus commit metadata with exact commit/path/line provenance.
- Git scans are idempotent per commit, preserve historical citations across later commits, report
  per-file failures, and delete all repository-owned derived data through the existing cascade.

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

[Unreleased]: https://github.com/thangldw/proofline/compare/v0.14.4...HEAD
[0.14.4]: https://github.com/thangldw/proofline/releases/tag/v0.14.4
[0.14.3]: https://github.com/thangldw/proofline/releases/tag/v0.14.3
[0.9.0]: https://github.com/thangldw/proofline/releases/tag/v0.9.0
[0.8.0]: https://github.com/thangldw/proofline/releases/tag/v0.8.0
[0.7.0]: https://github.com/thangldw/proofline/releases/tag/v0.7.0
[0.6.0]: https://github.com/thangldw/proofline/releases/tag/v0.6.0
[0.5.0]: https://github.com/thangldw/proofline/releases/tag/v0.5.0
[0.4.0]: https://github.com/thangldw/proofline/releases/tag/v0.4.0
[0.3.0]: https://github.com/thangldw/proofline/releases/tag/v0.3.0
[0.1.0-alpha.5]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.5
[0.1.0-alpha.4]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.4
[0.1.0-alpha.3]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/thangldw/proofline/releases/tag/v0.1.0-alpha.1
