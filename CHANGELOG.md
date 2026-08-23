# Proofline changelog / Lịch sử thay đổi / 変更履歴

## [2.0.0] - 2026-08-23

### English

- Added deterministic, cycle-safe transitive impact across explicit `based_on` and `implements` decision relations, with API, CLI, SARIF and web cockpit projections.
- Added the persistent decision-review ledger, audited review actions, immutable evidence-binding history, portable review receipts and stricter backup/import/integrity verification.
- Added Ed25519 signed attestations for verified Decision Evidence Packages and optional review receipts, including strict schemas, fixed conformance vectors and explicit trust limitations.
- Added CI, qualified 10,000-decision review benchmark evidence, full dependency audit gates and updated public plugin workflows.

### Tiếng Việt

- Bổ sung transitive impact xác định, cycle-safe qua quan hệ `based_on` và `implements` explicit; hỗ trợ API, CLI, SARIF và web cockpit.
- Bổ sung review ledger, thao tác audit, lịch sử evidence binding bất biến, review receipt portable và xác minh backup/import/integrity chặt hơn.
- Bổ sung signed attestation Ed25519 cho package và review receipt đã xác minh, kèm schema nghiêm ngặt, conformance vector và giới hạn trust rõ ràng.

### 日本語

- 明示的な `based_on` / `implements` 関係に限定した、cycle-safe で決定的な推移的影響を API、CLI、SARIF、web cockpit に追加しました。
- review ledger、監査済み action、不変 evidence-binding 履歴、portable receipt、強化された backup/import/integrity 検証を追加しました。
- 検証済み package と任意 receipt を対象とする Ed25519 signed attestation、厳格な schema、固定 vector、trust 制約を追加しました。

## [1.0.1] - 2026-08-02

### English

- Added a dependency-free verifier for Decision Evidence Packages to the public ChatGPT and Codex plugin bundle.
- Added a synthetic package fixture, public-directory metadata, and automated bundle conformance tests.
- Submitted the skills-only plugin to OpenAI, received approval, and published version 1.0.1 to the public Plugins Directory.
- Aligned the Python, web, desktop, Claude, Kimi and Codex version surfaces for the GitHub patch release.

### Tiếng Việt

- Bổ sung bộ xác minh Decision Evidence Package không cần dependency cho bundle plugin ChatGPT và Codex công khai.
- Bổ sung fixture tổng hợp, metadata cho public directory và kiểm thử tương thích bundle tự động.
- Đã gửi plugin dạng skills-only lên OpenAI, được duyệt và xuất bản phiên bản 1.0.1 lên Plugins Directory công khai.
- Đồng bộ version Python, web, desktop, Claude, Kimi và Codex cho bản vá GitHub.

### 日本語

- 公開 ChatGPT / Codex プラグイン bundle に、外部依存のない Decision Evidence Package 検証器を追加しました。
- 合成 fixture、公開 directory metadata、bundle 適合テストを追加しました。
- skills-only プラグインは OpenAI の承認を受け、バージョン 1.0.1 を公開 Plugins Directory に掲載しました。
- GitHub patch release 向けに Python、Web、desktop、Claude、Kimi、Codex の version を統一しました。

## [1.0.0] - 2026-07-26

### English

- Consolidated every merged provenance, stale-decision, evidence-package, backup and local UI capability into the `1.0.0` baseline.
- Kept deterministic exact-span checks, offline package verification and fail-closed integrity behavior.
- Removed automatic GitHub Actions and historical release documentation.

### Tiếng Việt

- Hợp nhất toàn bộ tính năng provenance, phát hiện quyết định lỗi thời, evidence package, backup và UI local đã merge vào baseline `1.0.0`.
- Giữ kiểm tra exact-span xác định, xác minh package offline và cơ chế fail-closed.
- Xóa GitHub Actions tự động và tài liệu release lịch sử.

### 日本語

- マージ済みの来歴、古い判断の検出、証拠パッケージ、バックアップ、ローカル UI を `1.0.0` に統合しました。
- 決定的な引用範囲検査、オフライン検証、fail-closed の整合性を維持しました。
- 自動 GitHub Actions と過去リリース文書を削除しました。

[2.0.0]: https://github.com/thangldw/proofline/releases/tag/v2.0.0
[1.0.1]: https://github.com/thangldw/proofline/releases/tag/v1.0.1
[1.0.0]: https://github.com/thangldw/proofline/releases/tag/v1.0.0
