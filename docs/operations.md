# Operations

## English

### Local state and recovery

Select local state with `--data-dir` or `PROOFLINE_HOME`. Before migration, bulk import, or restore, create and verify a backup:

```bash
proofline backup --output proofline-backup.db
proofline verify-backup proofline-backup.db
proofline restore-backup proofline-backup.db --rollback-output proofline-before-restore.db
proofline verify-integrity
```

Restore verifies the candidate before atomic replacement. When a database exists, preserve rollback output. Keep backups and exported packages under user-controlled access and retention.

### Bulk ingest and decision health

After bulk ingest, run `proofline refresh-reviews --policy proofline.toml`, then `proofline check-decisions --policy proofline.toml --format sarif` and `proofline check-impacts --format sarif`. Export the historical DEP before its review receipt and retain both. `verify-integrity` checks active/superseded binding chains, review fingerprints, and audit references.

### Attestation keys

Generate a key once in a restricted local directory. Distribute only the public key through an independent trusted channel. Sign only verified package/receipt subjects. Keep private keys outside repositories and synced folders; backup and rotation are external processes because Proofline has no revocation service.

On CPython 3.12 for Windows, owner-only descriptor modes are unavailable and key generation fails closed with `secure_permissions_unsupported`. Provision the PKCS#8 Ed25519 private key through an external owner-only Windows ACL workflow.

### Desktop artifact qualification

Run the manual `Desktop artifacts` GitHub Actions workflow with an immutable `source_ref`. With
`release_grade=false`, it builds isolated 14-day workflow artifacts only: macOS uses an ad-hoc
signature and Windows remains unsigned. These artifacts are experimental, are not attached to a
GitHub Release, and are not distribution evidence.

`release_grade=true` fails before build unless every platform credential is present. macOS requires
`APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `KEYCHAIN_PASSWORD`,
`APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, and `APPLE_TEAM_ID`. Windows requires
`WINDOWS_CERTIFICATE`, `WINDOWS_CERTIFICATE_PASSWORD`, `WINDOWS_CERTIFICATE_THUMBPRINT`, and
`WINDOWS_TIMESTAMP_URL`. Store them only as Actions secrets. The workflow follows the
[Tauri macOS signing/notarization contract](https://v2.tauri.app/distribute/sign/macos/) and
[Tauri Windows signing contract](https://v2.tauri.app/distribute/sign/windows/).

The pre-build gate proves only credential presence. A release-grade receipt is emitted only after
native validation: `codesign`, Gatekeeper, and stapled notarization tickets on macOS; valid
Authenticode status for the Tauri executable and every installer on Windows. It still does not
prove installer UX, upgrade/rollback behavior, SmartScreen reputation, or production readiness.
Without a successful release-grade receipt, there is no signed desktop distribution claim.

### Qualification and incidents

Run `make test`, `make check`, `make verify-package-conformance`, `npm run test:e2e`, and `make audit` before a release. Do not log secrets, source content, prompts, private keys, or full evidence packages. Preserve the failing input privately, collect sanitized command/version/error data, stop mutations when integrity fails, and follow [Security](../SECURITY.md) for disclosure.

## Tiếng Việt

### Local state và recovery

Chọn local state bằng `--data-dir` hoặc `PROOFLINE_HOME`. Trước migration, bulk import hoặc restore, tạo và verify backup:

```bash
proofline backup --output proofline-backup.db
proofline verify-backup proofline-backup.db
proofline restore-backup proofline-backup.db --rollback-output proofline-before-restore.db
proofline verify-integrity
```

Restore verify candidate trước atomic replacement. Khi database đã tồn tại, phải giữ rollback output. Backup và package export phải nằm dưới access/retention do người dùng kiểm soát.

### Bulk ingest và decision health

Sau bulk ingest, chạy `proofline refresh-reviews --policy proofline.toml`, rồi `proofline check-decisions --policy proofline.toml --format sarif` và `proofline check-impacts --format sarif`. Export DEP lịch sử trước review receipt của nó và giữ cả hai. `verify-integrity` check active/superseded binding chain, review fingerprint và audit reference.

### Attestation key

Generate key một lần trong restricted local directory. Chỉ phân phối public key qua trusted channel độc lập. Chỉ sign package/receipt subject đã verify. Giữ private key ngoài repository và synced folder; backup và rotation là quy trình bên ngoài vì Proofline không có revocation service.

Trên CPython 3.12 for Windows, owner-only descriptor mode không có và key generation fail closed với `secure_permissions_unsupported`. Provision private key PKCS#8 Ed25519 bằng external owner-only Windows ACL workflow.

### Qualification desktop artifact

Chạy workflow GitHub Actions manual `Desktop artifacts` với `source_ref` immutable. Khi
`release_grade=false`, workflow chỉ tạo artifact isolated có retention 14 ngày: macOS dùng ad-hoc
signature và Windows không sign. Đây là artifact experimental, không được gắn vào GitHub Release
và không phải distribution evidence.

`release_grade=true` fail trước build nếu thiếu credential platform. macOS cần
`APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `KEYCHAIN_PASSWORD`,
`APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD` và `APPLE_TEAM_ID`. Windows cần
`WINDOWS_CERTIFICATE`, `WINDOWS_CERTIFICATE_PASSWORD`, `WINDOWS_CERTIFICATE_THUMBPRINT` và
`WINDOWS_TIMESTAMP_URL`. Chỉ lưu chúng dưới dạng Actions secret. Workflow tuân theo contract
[Tauri macOS signing/notarization](https://v2.tauri.app/distribute/sign/macos/) và
[Tauri Windows signing](https://v2.tauri.app/distribute/sign/windows/).

Pre-build gate chỉ chứng minh credential có mặt. Release-grade receipt chỉ được tạo sau native
validation: `codesign`, Gatekeeper và stapled notarization ticket trên macOS; Authenticode status
valid cho Tauri executable cùng mọi installer trên Windows. Receipt vẫn không chứng minh installer
UX, upgrade/rollback, SmartScreen reputation hoặc production readiness. Nếu chưa có release-grade
receipt thành công thì chưa có claim signed desktop distribution.

### Qualification và incident

Chạy `make test`, `make check`, `make verify-package-conformance`, `npm run test:e2e` và `make audit` trước release. Không log secret, source content, prompt, private key hoặc full evidence package. Giữ failing input ở private, thu command/version/error đã sanitize, dừng mutation khi integrity fail và làm theo [Security](../SECURITY.md) để disclosure.

## 日本語

### Local state と recovery

Local state は `--data-dir` または `PROOFLINE_HOME` で選択します。Migration、bulk import、restore の前に backup を作成・検証します。

```bash
proofline backup --output proofline-backup.db
proofline verify-backup proofline-backup.db
proofline restore-backup proofline-backup.db --rollback-output proofline-before-restore.db
proofline verify-integrity
```

Restore は atomic replacement 前に candidate を検証します。既存 database がある場合は rollback output を保持します。Backup と export package は user-controlled access/retention の下に置きます。

### Bulk ingest と decision health

Bulk ingest 後に `proofline refresh-reviews --policy proofline.toml`、続いて `proofline check-decisions --policy proofline.toml --format sarif` と `proofline check-impacts --format sarif` を実行します。Historical DEP を review receipt より先に export し、両方を保持します。`verify-integrity` は active/superseded binding chain、review fingerprint、audit reference を検査します。

### Attestation key

制限した local directory で一度 key を生成し、public key だけを独立 trusted channel で配布します。検証済み package/receipt subject だけを sign します。Private key は repository と synced folder の外に置きます。Proofline に revocation service はないため backup/rotation は外部 process です。

CPython 3.12 for Windows では owner-only descriptor mode がなく、key generation は `secure_permissions_unsupported` で fail closed します。External owner-only Windows ACL workflow で PKCS#8 Ed25519 private key を provision してください。

### Desktop artifact qualification

Manual GitHub Actions workflow `Desktop artifacts` を immutable `source_ref` で実行します。
`release_grade=false` では 14 日 retention の isolated workflow artifact のみを作成し、macOS
は ad-hoc signature、Windows は unsigned のままです。これは experimental artifact であり、
GitHub Release には添付されず、distribution evidence ではありません。

`release_grade=true` は platform credential が一つでも不足すると build 前に失敗します。
macOS には `APPLE_CERTIFICATE`、`APPLE_CERTIFICATE_PASSWORD`、`KEYCHAIN_PASSWORD`、
`APPLE_SIGNING_IDENTITY`、`APPLE_ID`、`APPLE_PASSWORD`、`APPLE_TEAM_ID` が必要です。
Windows には `WINDOWS_CERTIFICATE`、`WINDOWS_CERTIFICATE_PASSWORD`、
`WINDOWS_CERTIFICATE_THUMBPRINT`、`WINDOWS_TIMESTAMP_URL` が必要です。Actions secret として
のみ保存します。Workflow は [Tauri macOS signing/notarization contract](https://v2.tauri.app/distribute/sign/macos/)
と [Tauri Windows signing contract](https://v2.tauri.app/distribute/sign/windows/) に従います。

Pre-build gate が証明するのは credential presence だけです。Release-grade receipt は macOS
で `codesign`、Gatekeeper、stapled notarization ticket、Windows で Tauri executable と全
installer の valid Authenticode status を native validation した後だけ生成されます。
Installer UX、upgrade/rollback、SmartScreen reputation、production readiness は証明しません。
成功した release-grade receipt がなければ signed desktop distribution claim はありません。

### Qualification と incident

Release 前に `make test`、`make check`、`make verify-package-conformance`、`npm run test:e2e`、`make audit` を実行します。Secret、source content、prompt、private key、full evidence package を log しません。Failing input は非公開で保持し、sanitize 済み command/version/error を収集し、integrity failure 時は mutation を停止し、disclosure は [Security](../SECURITY.md) に従います。
