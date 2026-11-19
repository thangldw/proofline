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

The verifier must obtain the trusted public key through an independent channel. Signature validity proves matching private-key control for the exact subjects; it does not prove legal identity, authorization, trusted time, transparency-log inclusion, or artifact safety.

Key revocation is verifier-side and opt-in: `proofline verify-attestation ... --revocations revoked.json` rejects any attestation signed by a listed key with `key_revoked`. The file is `{"schema": "proofline-key-revocations-v1", "revoked": [{"key_id": "<64 hex>", "reason": "optional"}]}`, at most 256 KiB and 1000 entries. Because `issued_at` is chosen by the signer and there is no trusted timestamp, a revoked key is rejected regardless of the time it claims. You must obtain the revocation file through the same independent channel as the trusted public key; Proofline does not distribute or refresh revocation lists.

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

Verifier phải nhận trusted public key qua kênh độc lập. Signature hợp lệ chứng minh quyền kiểm soát private key tương ứng cho đúng subject; không chứng minh legal identity, authorization, trusted time, transparency-log inclusion hoặc artifact safety.

Thu hồi khoá do verifier tự quyết và là tùy chọn: `proofline verify-attestation ... --revocations revoked.json` từ chối mọi attestation ký bởi khoá có trong danh sách với mã `key_revoked`. File có dạng `{"schema": "proofline-key-revocations-v1", "revoked": [{"key_id": "<64 hex>", "reason": "tùy chọn"}]}`, tối đa 256 KiB và 1000 mục. Vì `issued_at` do bên ký chọn và chưa có trusted timestamp nên khoá bị thu hồi bị từ chối bất kể thời điểm nó khai báo. Bạn phải lấy file thu hồi qua cùng kênh độc lập với trusted public key; Proofline không phân phối hay làm mới danh sách.

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

Verifier は trusted public key を独立 channel から取得する必要があります。Signature validity は正確な subject に対する matching private-key control を証明しますが、legal identity、authorization、trusted time、transparency-log inclusion、artifact safety は証明しません。

Key revocation は verifier 側の opt-in です: `proofline verify-attestation ... --revocations revoked.json` は、一覧に載る key で署名された attestation を `key_revoked` で拒否します。File は `{"schema": "proofline-key-revocations-v1", "revoked": [{"key_id": "<64 hex>", "reason": "任意"}]}` 形式で、最大 256 KiB・1000 件です。`issued_at` は署名者が選ぶ値で trusted timestamp がないため、失効 key は主張する時刻に関係なく拒否されます。Revocation file は trusted public key と同じ独立 channel で入手してください。Proofline は失効 list を配布・更新しません。

### Specification

- [Decision Evidence Package](../spec/decision-evidence-package/README.md)
- [Decision-review receipt](../spec/decision-review-receipt/README.md)
- [Signed attestation](../spec/signed-attestation/README.md)
- [三言語 verification diagram](diagrams/evidence-verification.html)

全 format は provider-independent であり、schema、canonicalization、hash、binding、signature error に対して fail closed します。出荷済み workflow は single-user/local で、これら artifact は hosted coordination を追加しません。

