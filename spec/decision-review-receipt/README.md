# Decision-review receipt specification

## English

`proofline-decision-review-receipt-v1` is a closed, portable JSON record binding one persisted decision-review snapshot to an exact verified DEP root. It carries decision/review identifiers, cited/current source-version identifiers and hashes, anchor/review state, finding and policy fingerprints, timestamps, `dep_root_hash`, and `receipt_hash`. It excludes source and quote content.

[JSON Schema](v1/schema.json) defines structure. The committed [valid vector](v1/test-vectors/valid-minimal.json), [expected result](v1/test-vectors/expected.json), and [mutations](v1/test-vectors/mutations.json) define reference behavior. Verification canonicalizes the receipt without `receipt_hash`, recomputes SHA-256, validates enum/timestamp/hash forms, and fails closed with stable content-free codes.

```bash
proofline verify-review-receipt spec/decision-review-receipt/v1/test-vectors/valid-minimal.json
```

A valid receipt proves deterministic binding and integrity, not reviewer identity, authorization, source truth, trusted time, or revocation. V1 is immutable; breaking changes require a new schema identity and directory.

## Tiếng Việt

`proofline-decision-review-receipt-v1` là JSON record closed, portable, gắn một persisted decision-review snapshot với đúng DEP root đã verify. Nó mang decision/review identifier, cited/current source-version identifier và hash, anchor/review state, finding và policy fingerprint, timestamp, `dep_root_hash` và `receipt_hash`. Nó loại trừ source và quote content.

[JSON Schema](v1/schema.json) định nghĩa structure. [Valid vector](v1/test-vectors/valid-minimal.json), [expected result](v1/test-vectors/expected.json) và [mutation](v1/test-vectors/mutations.json) đã commit định nghĩa reference behavior. Verification canonicalize receipt không có `receipt_hash`, recompute SHA-256, validate enum/timestamp/hash form và fail closed bằng stable content-free code.

```bash
proofline verify-review-receipt spec/decision-review-receipt/v1/test-vectors/valid-minimal.json
```

Receipt hợp lệ chứng minh deterministic binding và integrity, không chứng minh reviewer identity, authorization, source truth, trusted time hoặc revocation. V1 là immutable; breaking change cần schema identity và directory mới.

## 日本語

`proofline-decision-review-receipt-v1` は、一つの persisted decision-review snapshot を正確な verified DEP root に結び付ける closed/portable JSON record です。Decision/review identifier、cited/current source-version identifier と hash、anchor/review state、finding/policy fingerprint、timestamp、`dep_root_hash`、`receipt_hash` を持ち、source/quote content は除外します。

[JSON Schema](v1/schema.json) が structure を定義します。Committed [valid vector](v1/test-vectors/valid-minimal.json)、[expected result](v1/test-vectors/expected.json)、[mutation](v1/test-vectors/mutations.json) が reference behavior を定義します。Verification は `receipt_hash` を除いて receipt を canonicalize し、SHA-256 を再計算し、enum/timestamp/hash form を validate し、stable content-free code で fail closed します。

```bash
proofline verify-review-receipt spec/decision-review-receipt/v1/test-vectors/valid-minimal.json
```

Valid receipt が証明するのは deterministic binding と integrity であり、reviewer identity、authorization、source truth、trusted time、revocation ではありません。V1 は immutable で、breaking change には新 schema identity と directory が必要です。
