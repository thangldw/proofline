# Proofline operations / Vận hành / 運用

## English

Use `make setup`, `make test`, `make check` and `npm run test:e2e` before release. Back up the local Proofline home before migration or import, verify the backup, and restore into a separate location first. Release `v1.0.0` only from a clean commit after `scripts/release_check.py --tag v1.0.0` passes.

## Tiếng Việt

Trước khi phát hành, chạy `make setup`, `make test`, `make check` và `npm run test:e2e`. Backup Proofline home trước migration/import, xác minh backup và restore thử vào vị trí tách biệt. Chỉ phát hành `v1.0.0` từ commit sạch sau khi `scripts/release_check.py --tag v1.0.0` đạt.

## 日本語

リリース前に `make setup`、`make test`、`make check`、`npm run test:e2e` を実行します。migration や import の前に Proofline home をバックアップし、検証後、別の場所へ復元テストしてください。`scripts/release_check.py --tag v1.0.0` が成功したクリーンな commit からのみ公開します。

Secrets, source content and prompts must not be written to logs. / Không ghi secret, nội dung nguồn hoặc prompt vào log. / secret、ソース本文、prompt をログへ記録しないでください。
