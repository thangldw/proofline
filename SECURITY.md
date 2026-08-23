# Security / Bảo mật / セキュリティ

- **English:** Report vulnerabilities privately with GitHub Security Advisories. Do not include credentials, private source content or production data.
- **Tiếng Việt:** Báo lỗ hổng riêng tư qua GitHub Security Advisories. Không gửi credential, nội dung nguồn private hoặc dữ liệu production.
- **日本語:** 脆弱性は GitHub Security Advisories で非公開報告し、認証情報、非公開ソース本文、本番データを含めないでください。

SHA-256 roots and review receipts detect mutation; they are not signatures, authentication or authorization. The current trust boundary is one local user and local SQLite state. Hosted sync, multi-user permissions, connector identity and remote attestation are outside the implemented boundary. Source/quote content appears in Decision Evidence Packages but not review receipts, SARIF findings or safe verifier errors.
