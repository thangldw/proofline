# Decision Evidence Package specification

## English

Decision Evidence Package (DEP) is an implementation-neutral format carrying one engineering memory artifact, its immutable source version, exact cited spans, transformation lineage, review snapshot, and deterministic Merkle root. The v1 schema identity is `proofline-decision-evidence-package-v1`.

### Normative artifacts

- [JSON Schema](v1/schema.json) defines the closed structural contract.
- [Test vectors](v1/test-vectors/README.md) define one valid package, expected result, invalid mutations, and stable reference-verifier error codes.
- [Versioning policy](VERSIONING.md) defines immutability and compatibility.
- [Format guide](../../docs/evidence-packages.md) explains verification and trust boundaries.

Media are canonical JSON or a deterministic ZIP containing exactly one stored, uncompressed `evidence.json` entry. Semantic verification recomputes source content, citation spans, node hashes, ordered Merkle nodes, and `root_hash`; JSON Schema alone is insufficient. Verification needs no Proofline database, credential, network, or AI provider.

The root proves package integrity and lineage only. It does not prove source truth, source authenticity, reviewer identity, authorization, trusted time, or revocation. The specification, schema, and vectors use the repository's [MIT License](../../LICENSE).

## Tiếng Việt

Decision Evidence Package (DEP) là format trung lập implementation, mang một engineering memory artifact, immutable source version của nó, exact cited span, transformation lineage, review snapshot và deterministic Merkle root. Schema identity v1 là `proofline-decision-evidence-package-v1`.

### Normative artifact

- [JSON Schema](v1/schema.json) định nghĩa structural contract đóng.
- [Test vector](v1/test-vectors/README.md) định nghĩa một package hợp lệ, expected result, invalid mutation và stable error code của reference verifier.
- [Versioning policy](VERSIONING.md) định nghĩa immutability và compatibility.
- [Format guide](../../docs/evidence-packages.md) giải thích verification và trust boundary.

Media là canonical JSON hoặc deterministic ZIP chứa đúng một entry stored, uncompressed tên `evidence.json`. Semantic verification recompute source content, citation span, node hash, ordered Merkle node và `root_hash`; chỉ JSON Schema là chưa đủ. Verification không cần Proofline database, credential, network hoặc AI provider.

Root chỉ chứng minh package integrity và lineage. Nó không chứng minh source truth, source authenticity, reviewer identity, authorization, trusted time hoặc revocation. Specification, schema và vector dùng [MIT License](../../LICENSE) của repository.

## 日本語

Decision Evidence Package (DEP) は、一つの engineering memory artifact、その immutable source version、exact cited span、transformation lineage、review snapshot、deterministic Merkle root を運ぶ implementation-neutral format です。V1 schema identity は `proofline-decision-evidence-package-v1` です。

### Normative artifact

- [JSON Schema](v1/schema.json) が closed structural contract を定義します。
- [Test vector](v1/test-vectors/README.md) が valid package、expected result、invalid mutation、reference verifier の stable error code を定義します。
- [Versioning policy](VERSIONING.md) が immutability と compatibility を定義します。
- [Format guide](../../docs/evidence-packages.md) が verification と trust boundary を説明します。

Media は canonical JSON、または stored/uncompressed の `evidence.json` entry を一つだけ含む deterministic ZIP です。Semantic verification は source content、citation span、node hash、ordered Merkle node、`root_hash` を再計算します。JSON Schema だけでは不十分です。Verification に Proofline database、credential、network、AI provider は不要です。

Root が証明するのは package integrity と lineage だけです。Source truth、source authenticity、reviewer identity、authorization、trusted time、revocation は証明しません。Specification、schema、vector は repository の [MIT License](../../LICENSE) に従います。
