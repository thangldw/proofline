# Proofline command selection

## English

Resolve `SCRIPT` as `scripts/proofline_package.py` relative to the skill directory.

```bash
python3 SCRIPT verify PATH
python3 SCRIPT verify-review PATH
python3 SCRIPT explain PATH
python3 SCRIPT diff OLD_PATH NEW_PATH
```

`verify` accepts canonical JSON or a ZIP containing exactly one uncompressed `evidence.json`. `verify-review` accepts a decision-review receipt. `explain` returns verified provenance without source/quote content. `diff` verifies both packages before returning changed fields and hashes. All are read-only, emit JSON on stdout, and return a stable content-free `error` on stderr with exit status 2 for invalid input.

Smoke fixture: `python3 SCRIPT verify references/fixtures/valid-minimal.json`. It is synthetic and contains no user data.

The public plugin does not mutate a Proofline database or export from one. For ingest, stale scans, receipt export, or package export, direct the user to the [full local application](https://github.com/thangldw/proofline) and obtain approval before installation or local writes.

The bundled verifier does not verify Ed25519. With installed Proofline 2.0.0, verify the exact subjects against a user-selected trusted public key:

```bash
proofline verify-attestation ATTESTATION \
  --public-key TRUSTED_PUBLIC_KEY \
  --package PACKAGE \
  [--review-receipt RECEIPT]
```

Signing is a separate explicitly requested local action. Never read or return `PRIVATE_KEY`:

```bash
proofline attest --package PACKAGE [--review-receipt RECEIPT] \
  --private-key PRIVATE_KEY --output ATTESTATION
```

Verification establishes integrity and matching key control; it does not establish identity, a CA chain, trusted timestamp, transparency-log inclusion, authorization, or revocation.

## Tiếng Việt

Resolve `SCRIPT` là `scripts/proofline_package.py` relative với skill directory.

```bash
python3 SCRIPT verify PATH
python3 SCRIPT verify-review PATH
python3 SCRIPT explain PATH
python3 SCRIPT diff OLD_PATH NEW_PATH
```

`verify` nhận canonical JSON hoặc ZIP chứa đúng một `evidence.json` uncompressed. `verify-review` nhận decision-review receipt. `explain` trả verified provenance không có source/quote content. `diff` verify cả hai package trước khi trả changed field và hash. Tất cả là read-only, emit JSON ở stdout và trả stable content-free `error` ở stderr với exit status 2 cho invalid input.

Smoke fixture: `python3 SCRIPT verify references/fixtures/valid-minimal.json`. Fixture là synthetic và không chứa user data.

Public plugin không mutate Proofline database hoặc export từ database. Với ingest, stale scan, receipt export hoặc package export, hướng người dùng tới [full local application](https://github.com/thangldw/proofline) và lấy approval trước installation hoặc local write.

Bundled verifier không verify Ed25519. Với Proofline 2.0.0 đã cài, verify exact subject với trusted public key do người dùng chọn:

```bash
proofline verify-attestation ATTESTATION \
  --public-key TRUSTED_PUBLIC_KEY \
  --package PACKAGE \
  [--review-receipt RECEIPT]
```

Signing là local action riêng được request rõ ràng. Không đọc hoặc trả `PRIVATE_KEY`:

```bash
proofline attest --package PACKAGE [--review-receipt RECEIPT] \
  --private-key PRIVATE_KEY --output ATTESTATION
```

Verification thiết lập integrity và matching key control; không thiết lập identity, CA chain, trusted timestamp, transparency-log inclusion, authorization hoặc revocation.

## 日本語

`SCRIPT` は skill directory からの相対 path `scripts/proofline_package.py` として解決します。

```bash
python3 SCRIPT verify PATH
python3 SCRIPT verify-review PATH
python3 SCRIPT explain PATH
python3 SCRIPT diff OLD_PATH NEW_PATH
```

`verify` は canonical JSON、または uncompressed `evidence.json` を一つだけ含む ZIP を受け取ります。`verify-review` は decision-review receipt を受け取ります。`explain` は source/quote content なしで verified provenance を返します。`diff` は両 package を verify してから changed field/hash を返します。全 command は read-only で stdout に JSON を出し、invalid input では stderr に stable content-free `error`、exit status 2 を返します。

Smoke fixture：`python3 SCRIPT verify references/fixtures/valid-minimal.json`。Synthetic で user data はありません。

Public plugin は Proofline database を変更せず、database から export しません。Ingest、stale scan、receipt/package export には user を [full local application](https://github.com/thangldw/proofline) へ案内し、installation/local write 前に approval を得ます。

Bundled verifier は Ed25519 を検証しません。Installed Proofline 2.0.0 で、exact subject を user-selected trusted public key に対して verify します。

```bash
proofline verify-attestation ATTESTATION \
  --public-key TRUSTED_PUBLIC_KEY \
  --package PACKAGE \
  [--review-receipt RECEIPT]
```

Signing は別の explicit requested local action です。`PRIVATE_KEY` を読んだり返したりしません。

```bash
proofline attest --package PACKAGE [--review-receipt RECEIPT] \
  --private-key PRIVATE_KEY --output ATTESTATION
```

Verification は integrity と matching key control を確立しますが、identity、CA chain、trusted timestamp、transparency-log inclusion、authorization、revocation は確立しません。
