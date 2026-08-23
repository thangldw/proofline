# CLI reference

## English

Run `proofline COMMAND --help` for the exact option schema. Commands return zero on success and non-zero on invalid input, failed verification, policy failure, or runtime error. Verification commands do not mutate their inputs.

| Group | Commands | Contract |
|---|---|---|
| Local app | `serve`, `launch`, `seed` | Run local API/UI or index the bundled example. `serve` accepts host, port, data directory, lifecycle files, web directory, and API-only mode. |
| Evaluation | `eval`, `eval-grounded`, `eval-extraction`, `eval-real-model-preflight`, `eval-real-model`, `benchmark` | Run versioned evaluation or benchmark plans; real-model commands require explicit provider configuration. |
| Indexing | `embed` | Incrementally embed current source chunks using configured providers. |
| Portable snapshot | `export`, `verify-export`, `import` | Export, verify, restore, or explicitly merge portable JSON state. |
| Evidence package | `export-package`, `verify-package`, `explain`, `diff` | Export or independently verify a DEP; explain content-free provenance; verify both packages before diffing. |
| Review receipt | `export-review-receipt`, `verify-review-receipt` | Bind a persisted review to a verified DEP and verify the receipt offline. |
| Attestation | `generate-attestation-key`, `attest`, `verify-attestation` | Generate a local Ed25519 keypair, sign exact verified subjects, or verify against a trusted public key. |
| Recovery | `backup`, `verify-backup`, `restore-backup`, `verify-integrity` | Create/verify SQLite backup, atomically restore with rollback output, or check live provenance. |
| Decision health | `check-decisions`, `refresh-reviews`, `check-impacts` | Run read-only stale/impact CI checks or persist the current review ledger. |
| Demo | `demo stale-decision` | Run the self-contained stale-citation story; output directory reuse requires `--force`. |

Common verification examples:

```bash
proofline verify-package evidence.json
proofline verify-review-receipt decision-review.json
proofline verify-attestation envelope.json --public-key trusted.pem --package evidence.json
proofline check-decisions --policy proofline.toml --format sarif
proofline check-impacts --format sarif
```

`verify-package`, `verify-review-receipt`, `verify-attestation`, `verify-backup`, and `verify-integrity` fail closed. Safe errors identify the failed contract without returning confidential source text.

## Tiếng Việt

Chạy `proofline COMMAND --help` để xem option schema chính xác. Command trả zero khi thành công và non-zero khi input sai, verification fail, policy fail hoặc runtime error. Verification command không mutate input.

| Nhóm | Command | Contract |
|---|---|---|
| Local app | `serve`, `launch`, `seed` | Chạy API/UI local hoặc index bundled example. `serve` nhận host, port, data directory, lifecycle file, web directory và API-only mode. |
| Evaluation | `eval`, `eval-grounded`, `eval-extraction`, `eval-real-model-preflight`, `eval-real-model`, `benchmark` | Chạy versioned evaluation hoặc benchmark plan; real-model command cần provider configuration explicit. |
| Indexing | `embed` | Incremental embed current source chunk bằng provider đã cấu hình. |
| Portable snapshot | `export`, `verify-export`, `import` | Export, verify, restore hoặc explicit merge portable JSON state. |
| Evidence package | `export-package`, `verify-package`, `explain`, `diff` | Export hoặc verify DEP độc lập; explain provenance không trả content; verify cả hai package trước diff. |
| Review receipt | `export-review-receipt`, `verify-review-receipt` | Gắn persisted review với DEP đã verify và verify receipt offline. |
| Attestation | `generate-attestation-key`, `attest`, `verify-attestation` | Generate keypair Ed25519 local, sign exact verified subject hoặc verify với trusted public key. |
| Recovery | `backup`, `verify-backup`, `restore-backup`, `verify-integrity` | Tạo/verify SQLite backup, atomic restore có rollback output hoặc check live provenance. |
| Decision health | `check-decisions`, `refresh-reviews`, `check-impacts` | Chạy stale/impact CI check read-only hoặc persist review ledger hiện tại. |
| Demo | `demo stale-decision` | Chạy stale-citation story self-contained; reuse output directory cần `--force`. |

Ví dụ verification phổ biến:

```bash
proofline verify-package evidence.json
proofline verify-review-receipt decision-review.json
proofline verify-attestation envelope.json --public-key trusted.pem --package evidence.json
proofline check-decisions --policy proofline.toml --format sarif
proofline check-impacts --format sarif
```

`verify-package`, `verify-review-receipt`, `verify-attestation`, `verify-backup` và `verify-integrity` fail closed. Safe error chỉ ra contract bị fail mà không trả confidential source text.

## 日本語

正確な option schema は `proofline COMMAND --help` で確認します。Command は成功時 zero、invalid input、verification failure、policy failure、runtime error では non-zero を返します。Verification command は入力を変更しません。

| Group | Command | Contract |
|---|---|---|
| Local app | `serve`, `launch`, `seed` | Local API/UI を実行、または bundled example を index します。`serve` は host、port、data directory、lifecycle file、web directory、API-only mode を受け取ります。 |
| Evaluation | `eval`, `eval-grounded`, `eval-extraction`, `eval-real-model-preflight`, `eval-real-model`, `benchmark` | Versioned evaluation または benchmark plan を実行します。Real-model command には explicit provider configuration が必要です。 |
| Indexing | `embed` | 設定済み provider で current source chunk を incremental embed します。 |
| Portable snapshot | `export`, `verify-export`, `import` | Portable JSON state を export、verify、restore、または explicit merge します。 |
| Evidence package | `export-package`, `verify-package`, `explain`, `diff` | DEP を export/independent verify し、content-free provenance を explain し、両 package を verify 後に diff します。 |
| Review receipt | `export-review-receipt`, `verify-review-receipt` | Persisted review を verified DEP に結び付け、receipt を offline verify します。 |
| Attestation | `generate-attestation-key`, `attest`, `verify-attestation` | Local Ed25519 keypair の生成、exact verified subject の署名、trusted public key による検証を行います。 |
| Recovery | `backup`, `verify-backup`, `restore-backup`, `verify-integrity` | SQLite backup の作成/検証、rollback output 付き atomic restore、live provenance check を行います。 |
| Decision health | `check-decisions`, `refresh-reviews`, `check-impacts` | Read-only stale/impact CI check、または current review ledger の persist を行います。 |
| Demo | `demo stale-decision` | Self-contained stale-citation story を実行します。Output directory の再利用には `--force` が必要です。 |

一般的な verification 例：

```bash
proofline verify-package evidence.json
proofline verify-review-receipt decision-review.json
proofline verify-attestation envelope.json --public-key trusted.pem --package evidence.json
proofline check-decisions --policy proofline.toml --format sarif
proofline check-impacts --format sarif
```

`verify-package`、`verify-review-receipt`、`verify-attestation`、`verify-backup`、`verify-integrity` は fail closed します。Safe error は confidential source text を返さず、失敗 contract を示します。
