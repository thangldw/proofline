# Decision Evidence Package

Decision Evidence Package (DEP) is an open, implementation-neutral format for carrying one
engineering decision together with the immutable source version, exact cited spans,
transformation lineage, review state, and a deterministic Merkle root.

The current media types are canonical JSON and a deterministic ZIP containing exactly one stored
entry named `evidence.json`. The normative structural contract is the
[v1 JSON Schema](v1/schema.json). Hashing and semantic validation rules that JSON Schema cannot
express are defined in [the Proofline format documentation](../../docs/evidence-packages.md).

Implementations may use the committed [test vectors](v1/test-vectors/README.md) without Proofline,
a database, credentials, or network access. See the [versioning policy](VERSIONING.md) before
extending or consuming the format.

License: the specification, schemas, and test vectors are published under the repository's MIT
License.
