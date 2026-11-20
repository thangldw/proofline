# Proofline changelog

## Unreleased

- Fixed re-syncing a document that was reverted to content it had before: it failed with `ingestion_error` (a unique constraint on source version content). The source now points back at its existing version, so a citation that was stale recovers.

- Added `proofline import-adr`, which converts existing Markdown ADRs into files the indexer extracts decisions from. No schema migration.
- Added `proofline hook install|uninstall`, a git pre-commit hook that runs `check-code-refs` on staged files (and optionally `sync` plus `check-decisions`).
- Added `proofline report`, a shareable HTML or Markdown health report (trend, stale citations, reviews due, possible conflicts) with an optional `--no-titles` mode.
- Added `proofline completion bash|zsh|fish`, generated from the command tree.
- Added `proofline graph`, the decision relation graph as Mermaid or Graphviz DOT with stale and possible-conflict markers.
- Added `proofline policy-schema` and `spec/decision-policy/v1/schema.json`, a JSON Schema for `proofline.toml` that a test keeps in agreement with the loader.
- Added `proofline notify --webhook URL`, a content-free review-expiry alert (generic JSON or Slack text) with https-only delivery, no redirects and a timeout.
- Added `proofline watch <folder>`, which re-syncs when documents change and reports decisions that became stale or recovered.
- Added the read-only `decision_graph` MCP tool (ids, stale flags and edge kinds; titles only with `--include-titles`).
- Added executable decisions: `Enforce: forbid|require "text" in <glob>` and `Enforce: require file <glob>` lines, checked by `proofline check-enforcement`. Literal patterns only; rule lines are part of the cited text. No schema migration.
- Added `proofline agent-hook pre|post`, Claude Code hook handlers that put the approved decisions attached to a file into the agent's context before an edit and block the edit's result when it violates an `Enforce:` rule.
- Added `proofline ledger append|verify|compare`, a hash-chained content-free health history committed in the repository, and a comparison of the current state with the ledger at a base ref (newly stale and recovered decisions, stale rate change).
- Added `proofline code-context`, the reverse of `blame`: the approved decisions touched by a code change (nearby `proofline-decision:` markers, edited cited text, applicable `Enforce:` rules). The action gains `enforce` and `code-context` inputs (default off; they need this release or newer).
- Added `proofline asof <date|datetime> [question]`, which reconstructs which approved decisions were in force at a past moment and the health of their citations then. Reverting a source to earlier content now records a `source.version_restored` audit event so the timeline stays correct.

## [2.9.0] - 2026-11-19

- Added `Review every: N days|weeks|months|years` (repeats from the date the cited version was recorded; `rebind` restarts the cycle), `proofline suggest-links`, and a weekly operating routine in `docs/operations.md`. No schema migration.

## [2.8.0] - 2026-11-19

- Added `proofline doctor`, the read-only `check_expiry` and `find_conflicts` MCP tools, and the action inputs `check-expiry` and `code-refs`. No schema migration.

## [2.7.0] - 2026-11-19

- Added `proofline snapshot-health` and `proofline health-trend` (counts-only history of how many approved decisions are stale). Migration 24 adds the `decision_health_snapshots` table; existing tables and export formats are unchanged. Measured WAL mode for faster first sync and recorded the trade-off in the roadmap instead of applying it.

## [2.6.0] - 2026-11-19

- Added `check-decisions --explain`, per-directory `overrides` in the decision policy, `export-adr`, `check-code-refs` (`proofline-decision: <id>` markers in code), `find-conflicts`, and property tests for anchor resolution. No schema migration.

## [2.5.0] - 2026-11-19

- Added `proofline rebind` (preview a cited-vs-current diff, then re-anchor with an audited reason), `proofline why` and a read-only `why_decision` MCP tool (deterministic question-to-decision lookup with citation health), and `proofline check-expiry` for `Review by: YYYY-MM-DD` lines. No schema migration.

## [2.4.0] - 2026-11-19

- Added `proofline blame <path>[:line]` and the read-only `blame_location` MCP tool: which approved decisions are anchored at a file or line, with anchor state and current span.

## [2.3.0] - 2026-11-19

- Added an opt-in content-free pull-request comment to the PR gate action, a read-only `search_evidence` MCP tool (`--include-excerpts`), `verify-attestation --revocations`, and `scripts/benchmark_workspace.py`.
- Migration 23 indexes `sources(workspace_id, uri)`; no-change folder re-sync on 10,000 files fell from about 16.5 s to 2.2 s.
- Split the 750-line `cli.main` dispatch into one function per subcommand, removing the `Any` workaround from the mypy cleanup. Raised the coverage gate to 89%.
- Moved the model, extraction, answers/search and action-proposal routes out of `api.py` (1362 to 763 lines). Route modules now build providers through `proofline.provider_runtime.build_generation_provider`, a single call-time seam; tests patch that instead of `proofline.api`. OpenAPI is unchanged.
- Split `portability.py` into `portable_schema`, `portable_validation` and `portable_verify` (public API re-exported), and moved the notes, studio/study-card and decision-relation routes out of `api.py` into their own routers. The OpenAPI surface (70 operations) is unchanged.
- Fixed all remaining mypy errors and removed the module ratchet; every module under `apps/api/proofline` is now type-checked in `make check`. Unreachable missing-row cases now raise explicit errors instead of `AttributeError`.

## [2.2.0] - 2026-11-19

- Added `proofline mcp`, a read-only local MCP server over stdio with title-withholding by default (`docs/mcp.md`).

## [2.1.2] - 2026-11-19

- Added Hypothesis property tests for transitive impact and stale-versus-moved detection.
- Made the PyPI publish verifier retry the clean install until the simple index serves the release.

## [2.1.1] - 2026-11-19

- Added mypy to `make check` with a module ratchet, an 88% coverage gate, and a Python 3.12/3.13 `python-compat` CI job.
- Moved the test client to `httpx2` and removed an ignored `workspace_id` keyword in folder scanning.

## [2.1.0] - 2026-11-19

- Added `proofline sync`, a headless deterministic folder indexer with a stable `--uri-root`.
- Added a reusable composite GitHub Action that gates pull requests on changed decision evidence, with SARIF output.
- Added the pull-request gate recipe (`docs/pr-gate.md`).
- Align development and CI Node.js with jsdom 30 requirements.
- Upgrade React/ReactDOM and their types together with the Vite/React-plugin/jsdom toolchain; deduplicate the workspace runtime.
- Preserve spacing in navigation accessible names and recognize the narrow React 19 production diagnostic URL path in the static egress check.
- Rebuild the packaged web bundle from the upgraded toolchain.

## [2.0.2] - 2026-08-24

## [2.0.1] - 2026-08-24

## English

### 2.0.2

- Added exact-ref CI dispatch, Python and JavaScript/TypeScript CodeQL coverage, pinned Dependabot configuration, and protected-branch release gates.
- Made decision-health JSON output content-free while preserving deterministic stale and impact semantics.
- Added a fail-closed real-pilot dataset freezer with manifest hashes, permission checks, and explicit synthetic-versus-team evidence boundaries.
- Added gated macOS and Windows desktop artifact workflows with lifecycle receipts; current desktop outputs remain experimental, unsigned, and not release-grade.
- Made release qualification reject a stale desktop Cargo lock and constrained local GitHub Release assets to an explicit non-desktop allowlist.
- Published aligned Python, web, desktop metadata, CI artifact names, and plugin manifests for immutable release v2.0.2.

### 2.0.1

- Rebuilt the public, technical, policy, specification, and plugin documentation in English, Vietnamese, and Japanese.
- Replaced raster and Mermaid-era documentation visuals with three self-contained, accessible HTML/SVG diagrams for architecture, decision review, and evidence verification.
- Added a deterministic documentation contract for language order, links, diagrams, forbidden legacy paths, and external diagram dependencies.
- Preserved the 2.0.0 runtime behavior, schemas, conformance vectors, and trust boundaries; this patch updates packaged documentation and release surfaces.

### 2.0.0

- Added deterministic, cycle-safe transitive impact over explicit `based_on` and `implements` relations, exposed through API, CLI, SARIF, and web views.
- Added a persistent decision-review ledger, audited review actions, immutable evidence-binding history, portable review receipts, and stricter backup/import/integrity verification.
- Added Ed25519 attestations for verified Decision Evidence Packages and optional review receipts, with strict schemas, fixed conformance vectors, and explicit trust limits.
- Qualified CI, package/plugin conformance, dependency audits, and a synthetic 10,000-decision review benchmark.

### Earlier releases

- [1.0.1](https://github.com/thangldw/proofline/releases/tag/v1.0.1) added the dependency-free bundled package verifier and aligned public plugin/version surfaces.
- [1.0.0](https://github.com/thangldw/proofline/releases/tag/v1.0.0) established the immutable provenance, stale-decision, evidence-package, backup, API, web, and desktop baseline.

## Tiếng Việt

### 2.0.2

- Bổ sung CI dispatch theo exact ref, CodeQL cho Python và JavaScript/TypeScript, Dependabot config được pin cùng release gate trên protected branch.
- Chuyển decision-health JSON sang content-free nhưng giữ nguyên stale và impact semantics xác định.
- Bổ sung real-pilot dataset freezer fail-closed với manifest hash, permission check và ranh giới rõ giữa synthetic evidence với evidence team thật.
- Bổ sung workflow desktop artifact có gate cho macOS và Windows kèm lifecycle receipt; output desktop hiện vẫn experimental, unsigned và không phải release-grade.
- Bắt release qualification từ chối desktop Cargo lock stale và giới hạn local GitHub Release asset bằng allowlist non-desktop explicit.
- Đồng bộ Python, web, desktop metadata, CI artifact name và plugin manifest cho release bất biến v2.0.2.

### 2.0.1

- Viết lại tài liệu public, technical, policy, specification và plugin theo thứ tự English, Vietnamese, Japanese.
- Thay visual raster và Mermaid cũ bằng ba diagram HTML/SVG self-contained, accessible cho architecture, decision review và evidence verification.
- Bổ sung documentation contract xác định cho thứ tự ngôn ngữ, link, diagram, legacy path bị cấm và external dependency trong diagram.
- Giữ nguyên runtime behavior, schema, conformance vector và trust boundary của 2.0.0; patch này cập nhật packaged documentation cùng release surface.

### 2.0.0

- Bổ sung transitive impact xác định, cycle-safe trên quan hệ explicit `based_on` và `implements`, được cung cấp qua API, CLI, SARIF và web view.
- Bổ sung decision-review ledger persistent, review action có audit, lịch sử evidence-binding bất biến, review receipt portable và xác minh backup/import/integrity chặt hơn.
- Bổ sung attestation Ed25519 cho Decision Evidence Package đã verify và review receipt tùy chọn, kèm schema nghiêm ngặt, conformance vector cố định và giới hạn trust rõ ràng.
- Qualification cho CI, package/plugin conformance, dependency audit và benchmark review synthetic với 10.000 decision.

### Release trước

- [1.0.1](https://github.com/thangldw/proofline/releases/tag/v1.0.1) bổ sung bundled package verifier không cần dependency và đồng bộ public plugin/version surface.
- [1.0.0](https://github.com/thangldw/proofline/releases/tag/v1.0.0) thiết lập baseline cho provenance bất biến, stale decision, evidence package, backup, API, web và desktop.

## 日本語

### 2.0.2

- Exact-ref CI dispatch、Python / JavaScript/TypeScript CodeQL、pin 済み Dependabot configuration、protected-branch release gate を追加しました。
- Deterministic stale / impact semantics を維持しながら、decision-health JSON output を content-free にしました。
- Manifest hash、permission check、synthetic evidence と real-team evidence の明示的境界を備えた fail-closed real-pilot dataset freezer を追加しました。
- Lifecycle receipt を伴う gated macOS / Windows desktop artifact workflow を追加しました。現在の desktop output は experimental、unsigned で release-grade ではありません。
- Release qualification が stale desktop Cargo lock を拒否し、local GitHub Release asset を明示的な non-desktop allowlist に限定するようにしました。
- Immutable v2.0.2 release に向けて Python、web、desktop metadata、CI artifact name、plugin manifest を同期しました。

### 2.0.1

- Public、technical、policy、specification、plugin documentation を English、Vietnamese、Japanese の順で全面再構築しました。
- 旧 raster / Mermaid visual を、architecture、decision review、evidence verification 用の self-contained で accessible な HTML/SVG diagram 3 点に置き換えました。
- Language order、link、diagram、禁止 legacy path、external diagram dependency を検査する deterministic documentation contract を追加しました。
- 2.0.0 の runtime behavior、schema、conformance vector、trust boundary は維持し、この patch では packaged documentation と release surface を更新しました。

### 2.0.0

- 明示的な `based_on` / `implements` 関係に対する決定的で cycle-safe な transitive impact を追加し、API、CLI、SARIF、web view で提供しました。
- Persistent decision-review ledger、監査済み review action、不変 evidence-binding history、portable review receipt、強化した backup/import/integrity verification を追加しました。
- 検証済み Decision Evidence Package と任意 review receipt に対する Ed25519 attestation を、厳格な schema、固定 conformance vector、明示的 trust limit と共に追加しました。
- CI、package/plugin conformance、dependency audit、10,000 decision の synthetic review benchmark を qualification しました。

### 以前の release

- [1.0.1](https://github.com/thangldw/proofline/releases/tag/v1.0.1) は dependency-free bundled package verifier を追加し、public plugin/version surface を統一しました。
- [1.0.0](https://github.com/thangldw/proofline/releases/tag/v1.0.0) は immutable provenance、stale-decision、evidence package、backup、API、web、desktop の baseline を確立しました。

[2.0.2]: https://github.com/thangldw/proofline/releases/tag/v2.0.2
[2.0.1]: https://github.com/thangldw/proofline/releases/tag/v2.0.1
[2.0.0]: https://github.com/thangldw/proofline/releases/tag/v2.0.0
