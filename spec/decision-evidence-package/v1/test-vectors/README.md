# DEP v1 test vectors

## English

`valid-minimal.json` is a complete deterministic fixture. A conforming verifier returns the artifact ID, citation count, schema identity, and root hash in `expected.json`.

`mutations.json` applies each JSON Pointer replacement to a fresh copy of the valid fixture. A conforming verifier rejects every mutation with its listed stable code: `source_content_invalid`, `citation_span_invalid`, `artifact_node_hash_mismatch`, or `review_node_hash_mismatch`. Human wording may differ; the reference code is the tested contract.

```bash
proofline verify-package spec/decision-evidence-package/v1/test-vectors/valid-minimal.json
pytest -q apps/api/tests/test_dep_format.py
```

Run from the repository root. The fixture is synthetic, contains no user data, and does not establish source authenticity.

## Tiếng Việt

`valid-minimal.json` là deterministic fixture đầy đủ. Verifier conforming trả artifact ID, citation count, schema identity và root hash trong `expected.json`.

`mutations.json` áp từng JSON Pointer replacement vào fresh copy của valid fixture. Verifier conforming reject mọi mutation bằng stable code được liệt kê: `source_content_invalid`, `citation_span_invalid`, `artifact_node_hash_mismatch` hoặc `review_node_hash_mismatch`. Human wording có thể khác; reference code là tested contract.

```bash
proofline verify-package spec/decision-evidence-package/v1/test-vectors/valid-minimal.json
pytest -q apps/api/tests/test_dep_format.py
```

Chạy từ repository root. Fixture là synthetic, không chứa user data và không thiết lập source authenticity.

## 日本語

`valid-minimal.json` は完全な deterministic fixture です。Conforming verifier は `expected.json` の artifact ID、citation count、schema identity、root hash を返します。

`mutations.json` は各 JSON Pointer replacement を valid fixture の fresh copy に適用します。Conforming verifier は全 mutation を、記載された stable code `source_content_invalid`、`citation_span_invalid`、`artifact_node_hash_mismatch`、`review_node_hash_mismatch` のいずれかで reject します。Human wording は異なってもよく、reference code が tested contract です。

```bash
proofline verify-package spec/decision-evidence-package/v1/test-vectors/valid-minimal.json
pytest -q apps/api/tests/test_dep_format.py
```

Repository root から実行します。Fixture は synthetic で user data を含まず、source authenticity を確立しません。
