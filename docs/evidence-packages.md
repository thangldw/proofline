# Evidence packages and attestations

## English

### Decision Evidence Package

A Decision Evidence Package (DEP) is a self-contained JSON document or canonical ZIP containing one memory artifact, immutable source-version evidence, exact citation spans, and a root hash. `proofline verify-package PATH` validates schema, identifiers, quote/span hashes, canonical ordering, and the root without database, network, or AI access. The root establishes integrity, not authenticity.

### Decision-review receipt

A `proofline-decision-review-receipt-v1` receipt contains no source or quote content. It binds a decision-review snapshot, policy/result fingerprints, and evidence bindings to an exact verified DEP root. `proofline verify-review-receipt PATH` verifies the portable receipt independently. A receipt proves deterministic binding and integrity, not reviewer identity or source truth.

### Signed attestation

A `proofline-signed-attestation-v1` envelope binds a verified package and optional verified receipt to an Ed25519 signature. Verify with:

```bash
proofline verify-attestation envelope.json \
  --public-key trusted-public.pem \
  --package evidence.json \
  --review-receipt decision-review.json
```

The verifier must obtain the trusted public key through an independent channel. Signature validity proves matching private-key control for the exact subjects; it does not prove legal identity, authorization, trusted time, revocation, transparency-log inclusion, or artifact safety.

### Specifications

- [Decision Evidence Package](../spec/decision-evidence-package/README.md)
- [Decision-review receipt](../spec/decision-review-receipt/README.md)
- [Signed attestation](../spec/signed-attestation/README.md)
- [Trilingual verification diagram](diagrams/evidence-verification.html)

All formats are provider-independent and fail closed on schema, canonicalization, hash, binding, or signature errors. The shipped workflow is single-user and local; these artifacts do not add hosted coordination.

## Tiếng Việt

### Decision Evidence Package

Decision Evidence Package (DEP) là JSON document self-contained hoặc canonical ZIP chứa một memory artifact, evidence của immutable source version, exact citation span và root hash. `proofline verify-package PATH` verify schema, identifier, quote/span hash, canonical ordering và root mà không cần database, network hoặc AI. Integrity không phải authenticity.

### Decision-review receipt

Receipt `proofline-decision-review-receipt-v1` không chứa source hoặc quote content. Nó gắn decision-review snapshot, policy/result fingerprint và evidence binding với đúng DEP root đã verify. `proofline verify-review-receipt PATH` verify receipt portable độc lập. Receipt chứng minh deterministic binding và integrity, không chứng minh reviewer identity hoặc source truth.

### Signed attestation

Envelope `proofline-signed-attestation-v1` gắn package đã verify và receipt tùy chọn đã verify với signature Ed25519. Verify bằng:

```bash
proofline verify-attestation envelope.json \
  --public-key trusted-public.pem \
  --package evidence.json \
  --review-receipt decision-review.json
```

Verifier phải nhận trusted public key qua kênh độc lập. Signature hợp lệ chứng minh quyền kiểm soát private key tương ứng cho đúng subject; không chứng minh legal identity, authorization, trusted time, revocation, transparency-log inclusion hoặc artifact safety.

### Specification

- [Decision Evidence Package](../spec/decision-evidence-package/README.md)
- [Decision-review receipt](../spec/decision-review-receipt/README.md)
- [Signed attestation](../spec/signed-attestation/README.md)
- [Sơ đồ verification ba ngôn ngữ](diagrams/evidence-verification.html)

Mọi format độc lập provider và fail closed khi có lỗi schema, canonicalization, hash, binding hoặc signature. Workflow đã phát hành là single-user và local; các artifact này không bổ sung hosted coordination.

## 日本語

### Decision Evidence Package

Decision Evidence Package (DEP) は、一つの memory artifact、immutable source-version evidence、exact citation span、root hash を含む self-contained JSON document または canonical ZIP です。`proofline verify-package PATH` は database、network、AI なしで schema、identifier、quote/span hash、canonical ordering、root を検証します。Integrity は authenticity ではありません。

### Decision-review receipt

`proofline-decision-review-receipt-v1` receipt は source または quote content を含みません。Decision-review snapshot、policy/result fingerprint、evidence binding を、検証済み DEP の正確な root に結び付けます。`proofline verify-review-receipt PATH` は portable receipt を独立に検証します。Receipt が証明するのは deterministic binding と integrity であり、reviewer identity や source truth ではありません。

### Signed attestation

`proofline-signed-attestation-v1` envelope は検証済み package と任意の検証済み receipt を Ed25519 signature に結び付けます。

```bash
proofline verify-attestation envelope.json \
  --public-key trusted-public.pem \
  --package evidence.json \
  --review-receipt decision-review.json
```

Verifier は trusted public key を独立 channel から取得する必要があります。Signature validity は正確な subject に対する matching private-key control を証明しますが、legal identity、authorization、trusted time、revocation、transparency-log inclusion、artifact safety は証明しません。

### Specification

- [Decision Evidence Package](../spec/decision-evidence-package/README.md)
- [Decision-review receipt](../spec/decision-review-receipt/README.md)
- [Signed attestation](../spec/signed-attestation/README.md)
- [三言語 verification diagram](diagrams/evidence-verification.html)

全 format は provider-independent であり、schema、canonicalization、hash、binding、signature error に対して fail closed します。出荷済み workflow は single-user/local で、これら artifact は hosted coordination を追加しません。
