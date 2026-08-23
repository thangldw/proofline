# Security

## English

Report vulnerabilities privately through [GitHub Security Advisories](https://github.com/thangldw/proofline/security/advisories/new). Do not include credentials, private source content, private keys, or production data in public issues.

SHA-256 roots and review receipts detect mutation; alone they are not signatures, authentication, or authorization. Proofline 2.0.1 can sign verified subject identifiers with Ed25519. Verification proves matching private-key control relative to an independently trusted public key; it does not establish legal identity, a CA chain, trusted time, transparency, revocation, authorization, or artifact safety.

Generated private keys are unencrypted PKCS#8 PEM files with owner-only mode `0600` where descriptor permission enforcement is available. Key generation fails closed with `secure_permissions_unsupported` otherwise, including CPython 3.12 on Windows. On such systems, use an external owner-only ACL or key-management process. Keep keys outside repositories and synced folders, restrict backups, rotate trust externally, and never attach keys to issues or plugin bundles. Proofline does not store keys in SQLite or telemetry.

The implemented trust boundary is one local user and local SQLite state. Hosted sync, multi-user permission enforcement, connector identity, remote attestation, trusted time, and revocation are outside scope. Source and quote content can appear in Decision Evidence Packages but not in review receipts, signed envelopes, SARIF findings, or safe verifier errors. English controls if a translation conflicts.

## Tiếng Việt

Báo vulnerability riêng tư qua [GitHub Security Advisories](https://github.com/thangldw/proofline/security/advisories/new). Không đưa credential, private source content, private key hoặc production data vào public issue.

SHA-256 root và review receipt phát hiện mutation; riêng chúng không phải signature, authentication hoặc authorization. Proofline 2.0.1 có thể ký verified subject identifier bằng Ed25519. Verification chứng minh quyền kiểm soát private key tương ứng với trusted public key độc lập; không thiết lập legal identity, CA chain, trusted time, transparency, revocation, authorization hoặc artifact safety.

Private key được generate là file PKCS#8 PEM không mã hoá với mode chỉ owner `0600` khi hệ thống có thể enforce descriptor permission. Nếu không, key generation fail closed với `secure_permissions_unsupported`, bao gồm CPython 3.12 trên Windows. Trên hệ đó, dùng ACL chỉ owner hoặc key-management process bên ngoài. Để key ngoài repository và synced folder, giới hạn backup, rotate trust bằng quy trình ngoài và không đính kèm key vào issue hoặc plugin bundle. Proofline không lưu key trong SQLite hoặc telemetry.

Trust boundary đã triển khai là một người dùng local và SQLite state local. Hosted sync, multi-user permission enforcement, connector identity, remote attestation, trusted time và revocation nằm ngoài phạm vi. Source và quote content có thể xuất hiện trong Decision Evidence Package nhưng không có trong review receipt, signed envelope, SARIF finding hoặc safe verifier error. English có hiệu lực nếu bản dịch xung đột.

## 日本語

Vulnerability は [GitHub Security Advisories](https://github.com/thangldw/proofline/security/advisories/new) で非公開報告してください。Credential、private source content、private key、production data を public issue に含めないでください。

SHA-256 root と review receipt は mutation を検出しますが、それ自体は signature、authentication、authorization ではありません。Proofline 2.0.1 は verified subject identifier を Ed25519 で署名できます。Verification は独立に信頼した public key に対応する private key の制御を証明しますが、legal identity、CA chain、trusted time、transparency、revocation、authorization、artifact safety は確立しません。

生成する private key は暗号化されていない PKCS#8 PEM で、descriptor permission を強制できる環境では owner-only mode `0600` を使用します。それ以外では、CPython 3.12 on Windows を含め `secure_permissions_unsupported` で fail closed します。その環境では外部の owner-only ACL または key-management process を使ってください。Key は repository と synced folder の外に置き、backup を制限し、外部 trust process で rotate し、issue や plugin bundle に添付しないでください。Proofline は key を SQLite や telemetry に保存しません。

実装済み trust boundary は一人の local user と local SQLite state です。Hosted sync、multi-user permission enforcement、connector identity、remote attestation、trusted time、revocation は範囲外です。Source と quote content は Decision Evidence Package に含まれ得ますが、review receipt、signed envelope、SARIF finding、safe verifier error には含まれません。翻訳が競合する場合は English を優先します。
