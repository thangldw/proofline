# Signed attestation specification

## English

`proofline-signed-attestation-v1` is a closed JSON envelope using algorithm `ed25519`. Its signed `proofline-attestation-statement-v1` contains `key_id`, `issued_at`, exact package root/artifact identifiers, and either no receipt or exact receipt/review/DEP-root identifiers. The signature is base64; `key_id` is the SHA-256 identifier of the public key material.

[JSON Schema](v1/schema.json) defines structure. The committed [attestation vector](v1/test-vectors/valid-ed25519.json) and [public key](v1/test-vectors/valid-ed25519-public.pem) verify reference behavior.

```bash
.venv/bin/python scripts/verify_attestation_vector.py \
  spec/signed-attestation/v1/test-vectors/valid-ed25519.json \
  spec/signed-attestation/v1/test-vectors/valid-ed25519-public.pem
```

Verification first verifies the exact package and optional receipt, then checks statement bindings, key identifier, canonical statement bytes, and Ed25519 signature. The verifier selects the trusted public key independently. A valid signature proves matching private-key control for those exact subjects; it does not prove identity, authorization, trusted time, revocation, transparency, or artifact safety. V1 is immutable.

## Tiếng Việt

`proofline-signed-attestation-v1` là JSON envelope closed dùng algorithm `ed25519`. Statement được sign `proofline-attestation-statement-v1` chứa `key_id`, `issued_at`, exact package root/artifact identifier và hoặc không có receipt, hoặc có exact receipt/review/DEP-root identifier. Signature là base64; `key_id` là SHA-256 identifier của public key material.

[JSON Schema](v1/schema.json) định nghĩa structure. [Attestation vector](v1/test-vectors/valid-ed25519.json) và [public key](v1/test-vectors/valid-ed25519-public.pem) đã commit verify reference behavior.

```bash
.venv/bin/python scripts/verify_attestation_vector.py \
  spec/signed-attestation/v1/test-vectors/valid-ed25519.json \
  spec/signed-attestation/v1/test-vectors/valid-ed25519-public.pem
```

Verification trước tiên verify exact package và receipt tùy chọn, rồi check statement binding, key identifier, canonical statement byte và signature Ed25519. Verifier chọn trusted public key độc lập. Signature hợp lệ chứng minh quyền kiểm soát private key tương ứng cho đúng subject; không chứng minh identity, authorization, trusted time, revocation, transparency hoặc artifact safety. V1 là immutable.

## 日本語

`proofline-signed-attestation-v1` は algorithm `ed25519` を使う closed JSON envelope です。署名対象 `proofline-attestation-statement-v1` は `key_id`、`issued_at`、exact package root/artifact identifier、receipt がないこと、または exact receipt/review/DEP-root identifier を含みます。Signature は base64、`key_id` は public key material の SHA-256 identifier です。

[JSON Schema](v1/schema.json) が structure を定義します。Committed [attestation vector](v1/test-vectors/valid-ed25519.json) と [public key](v1/test-vectors/valid-ed25519-public.pem) が reference behavior を検証します。

```bash
.venv/bin/python scripts/verify_attestation_vector.py \
  spec/signed-attestation/v1/test-vectors/valid-ed25519.json \
  spec/signed-attestation/v1/test-vectors/valid-ed25519-public.pem
```

Verification は最初に exact package と任意 receipt を verify し、statement binding、key identifier、canonical statement byte、Ed25519 signature を検査します。Verifier は trusted public key を独立に選択します。有効 signature は正確な subject に対する matching private-key control を証明しますが、identity、authorization、trusted time、revocation、transparency、artifact safety は証明しません。V1 は immutable です。
