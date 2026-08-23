# Proofline operations / Vận hành / 運用

## English

Use `make setup`, `make test`, `make check`, `make verify-package-conformance`, `npm run test:e2e` and `npm audit --omit=dev --audit-level=high` before release. Back up the local Proofline home before migration or import, verify the backup, and restore into a separate location first. Release `v2.0.0` only from a clean commit after `scripts/release_check.py --tag v2.0.0` passes.

Run `proofline refresh-reviews --policy proofline.toml` after bulk ingestion, then export the historical Decision Evidence Package before exporting its review receipt. Preserve both artifacts. `proofline verify-integrity` validates active/superseded binding chains, review fingerprints and audit references. A restore requires a rollback output for an existing database and verifies the candidate before atomic replacement.

Run `proofline check-impacts --format sarif` at the same release gate as `check-decisions`. Generate attestation keys once in a restricted local directory, distribute only the public key through an independent trusted channel, and sign only after both package and receipt verification pass. Back up or rotate private keys outside Proofline; there is no built-in revocation service.

## Tiếng Việt

Trước khi phát hành, chạy toàn bộ test/check/conformance/E2E/audit. Chỉ phát hành `v2.0.0` từ commit sạch sau khi `scripts/release_check.py --tag v2.0.0` đạt. Giữ private key ngoài repository và phân phối public key qua kênh tin cậy độc lập.

## 日本語

リリース前に test、check、conformance、E2E、audit をすべて実行します。`scripts/release_check.py --tag v2.0.0` が成功した clean commit からのみ公開し、private key は repository 外で保護します。

Secrets, source content and prompts must not be written to logs. / Không ghi secret, nội dung nguồn hoặc prompt vào log. / secret、ソース本文、prompt をログへ記録しないでください。
