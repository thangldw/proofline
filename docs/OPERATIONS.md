# Proofline operations / Vận hành / 運用

## English

Use `make setup`, `make test`, `make check`, `make verify-package-conformance`, `npm run test:e2e` and `make audit` before release. `make audit` covers installed Python dependencies with `pip-audit` and production npm dependencies. Back up the local Proofline home before migration or import, verify the backup, and restore into a separate location first. Release `v2.0.0` only from a clean commit after `scripts/release_check.py --tag v2.0.0` passes. The release entrypoints publish the exact qualified wheel and sdist with Twine, bind their SHA-256 digests to the public version-specific PyPI JSON response, then install `proofline-evidence==2.0.0` without a local cache in a fresh environment and run the stale-decision demo. The PyPI distribution is `proofline-evidence`; the import package and CLI remain `proofline`.

Run `proofline refresh-reviews --policy proofline.toml` after bulk ingestion, then export the historical Decision Evidence Package before exporting its review receipt. Preserve both artifacts. `proofline verify-integrity` validates active/superseded binding chains, review fingerprints and audit references. A restore requires a rollback output for an existing database and verifies the candidate before atomic replacement.

Run `proofline check-impacts --format sarif` at the same release gate as `check-decisions`. Generate attestation keys once in a restricted local directory, distribute only the public key through an independent trusted channel, and sign only after both package and receipt verification pass. Back up or rotate private keys outside Proofline; there is no built-in revocation service.

PyPI publication precedes the public Git tag and GitHub release. If PyPI accepts only one artifact,
rerun the same release: `publish_pypi.py` verifies the existing artifact digest, uploads only the
missing exact artifact, and waits for both public digests before the isolated install smoke.

On CPython 3.12 for Windows, `generate-attestation-key` intentionally fails closed because owner-only descriptor modes are unavailable. Provision the PKCS#8 Ed25519 key with an external owner-only Windows ACL workflow; the Windows artifact gate verifies this stable failure and then qualifies `attest`/`verify-attestation` using an ephemeral externally generated key.

## Tiếng Việt

Trước khi phát hành, chạy toàn bộ test/check/conformance/E2E/audit. Chỉ phát hành `v2.0.0` từ commit sạch sau khi `scripts/release_check.py --tag v2.0.0` đạt. Giữ private key ngoài repository và phân phối public key qua kênh tin cậy độc lập.

## 日本語

リリース前に test、check、conformance、E2E、audit をすべて実行します。`scripts/release_check.py --tag v2.0.0` が成功した clean commit からのみ公開し、private key は repository 外で保護します。

Secrets, source content and prompts must not be written to logs. / Không ghi secret, nội dung nguồn hoặc prompt vào log. / secret、ソース本文、prompt をログへ記録しないでください。
