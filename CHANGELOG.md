# Proofline changelog

## [2.0.2] - 2026-08-24

## [2.0.1] - 2026-08-24

## English

### 2.0.2

- Added exact-ref CI dispatch, Python and JavaScript/TypeScript CodeQL coverage, pinned Dependabot configuration, and protected-branch release gates.
- Made decision-health JSON output content-free while preserving deterministic stale and impact semantics.
- Added a fail-closed real-pilot dataset freezer with manifest hashes, permission checks, and explicit synthetic-versus-team evidence boundaries.
- Added gated macOS and Windows desktop artifact workflows with lifecycle receipts; current desktop outputs remain experimental, unsigned, and not release-grade.
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
