# Proofline operations / Vận hành / 運用

## English

Use `make setup`, `make test`, `make check`, `make verify-package-conformance`, `npm run test:e2e` and `npm audit --omit=dev --audit-level=high` before release. Back up the local Proofline home before migration or import, verify the backup, and restore into a separate location first. Release `v1.0.1` only from a clean commit after `scripts/release_check.py --tag v1.0.1` passes.

Run `proofline refresh-reviews --policy proofline.toml` after bulk ingestion, then export the historical Decision Evidence Package before exporting its review receipt. Preserve both artifacts. `proofline verify-integrity` validates active/superseded binding chains, review fingerprints and audit references. A restore requires a rollback output for an existing database and verifies the candidate before atomic replacement.

## Tiếng Việt

Trước khi phát hành, chạy `make setup`, `make test`, `make check` và `npm run test:e2e`. Backup Proofline home trước migration/import, xác minh backup và restore thử vào vị trí tách biệt. Chỉ phát hành `v1.0.1` từ commit sạch sau khi `scripts/release_check.py --tag v1.0.1` đạt.

## 日本語

リリース前に `make setup`、`make test`、`make check`、`npm run test:e2e` を実行します。migration や import の前に Proofline home をバックアップし、検証後、別の場所へ復元テストしてください。`scripts/release_check.py --tag v1.0.1` が成功したクリーンな commit からのみ公開します。

Secrets, source content and prompts must not be written to logs. / Không ghi secret, nội dung nguồn hoặc prompt vào log. / secret、ソース本文、prompt をログへ記録しないでください。
