# Security / Bảo mật / セキュリティ

- **English:** Report vulnerabilities privately with GitHub Security Advisories. Do not include credentials, private source content or production data.
- **Tiếng Việt:** Báo lỗ hổng riêng tư qua GitHub Security Advisories. Không gửi credential, nội dung nguồn private hoặc dữ liệu production.
- **日本語:** 脆弱性は GitHub Security Advisories で非公開報告し、認証情報、非公開ソース本文、本番データを含めないでください。

SHA-256 roots and review receipts detect mutation; alone they are not signatures, authentication or authorization. Proofline 2.0.0 can sign their identifiers with Ed25519. Verification proves matching private-key control relative to an independently trusted public key; it does not provide legal identity, a CA chain, trusted timestamp, transparency log, revocation or authorization.

Generated private keys are unencrypted PKCS#8 PEM files with mode `0600`. Store them outside repositories and synced folders, restrict backups, rotate them through an external trust process, and never attach them to issues or plugin bundles. Proofline does not store keys in SQLite or telemetry.

The current trust boundary is one local user and local SQLite state. Hosted sync, multi-user permissions, connector identity and remote attestation are outside the implemented boundary. Source/quote content appears in Decision Evidence Packages but not review receipts, signed envelopes, SARIF findings or safe verifier errors.
