# Decision Evidence Packages

This is the center of Proofline's current technical direction: verifiable decision memory. The
project is deepening provenance before adding more artifact categories.

Proofline can export one decision or memory as a self-contained, verifiable JSON or ZIP package.
The package contains the immutable source-version text, cited chunk nodes, exact citation spans,
transformation receipt, artifact content, review state, parent hashes, and one root hash.

This first version deliberately covers only `Decision`-backed memory artifacts. It is not a generic
artifact graph, signature format, or proof that a source was trustworthy. SHA-256 verification
establishes internal integrity after a root hash is known; it does not establish who created the
package or when.

## Commands

Find an artifact ID in the Decisions or Memories view, then run:

```bash
proofline explain ARTIFACT_ID
proofline export-package ARTIFACT_ID --output evidence.zip
proofline verify-package evidence.zip
proofline diff before.zip after.zip
```

`explain` reads the local database and prints the artifact, review state, transformation lineage,
immutable source identity, and citations. It omits the full source text from its output.

`verify-package` requires no database or model provider. It recomputes every node hash and checks:

- source content length and SHA-256;
- chunk ownership, content SHA-256, exact offsets, lines, and source-version parent;
- citation ownership, offsets, lines, exact quote, and quote SHA-256;
- transformation inputs and model-run parent lineage;
- artifact-to-transformation and artifact-to-citation relationships;
- review-to-artifact relationship;
- the package root hash.

The package writer creates private `0600` files and refuses to overwrite an existing path unless
`--force` is supplied.

An output path ending in `.zip` creates a deterministic archive containing exactly one stored entry,
`evidence.json`. Other suffixes retain the plain canonical JSON representation. Verification detects
the container from its bytes rather than trusting the filename. ZIP verification rejects extra or
duplicate entries, traversal paths, symlinks, encryption, unsupported compression, oversized
metadata, malformed central directories, and archives above the configured bound.

`diff` verifies both inputs before comparing them. Its content-free report identifies changed
source metadata fields, citation node hashes added or removed, transformation changes, semantic
artifact fields, and review fields. It does not print source text, statements, or rationale.

For a credential-free end-to-end check of the production SQLite paths, run:

```bash
make verify-provenance
```

This regenerates `evals/provenance/conformance-v1.json`. The content-free receipt covers repeated
package roots, deterministic ZIP bytes, verification, source-revision stability, portable
export/import root preservation, and live database integrity. It is local conformance evidence,
not a signature, authenticity proof, model evaluation, or production-scale qualification.

## Hash contract

Nodes use canonical JSON with sorted keys, compact separators, UTF-8, and domain-separated SHA-256.
A chunk hash binds its source-version parent, content, ordinal, and locator. A citation hash binds
the source-version, every overlapping chunk node, locator, and quote. The artifact hash binds
semantic content, its transformation, and citations. Mutable review state is a separate child node,
so a status change produces a new package root without changing the artifact content hash.

Package creation time and application version are informational manifest fields and are excluded
from the root. Exporting unchanged state twice therefore produces the same root hash.

## Failure modes

Commands fail closed with content-free error codes. A malformed, oversized, unsupported, or
hash-mismatched package is rejected. Package verification never repairs data. Deleted source
versions cannot be used to create a new package, but an already exported self-contained package
remains independently verifiable.

The current upload contract accepts `markdown`, `text`, and `note`; local Git has its own
deterministic ingestion path. No PDF parser or PDF source contract exists in this vertical slice,
so PDF metadata fuzzing is intentionally deferred until that input is opened. Package JSON and ZIP
archive inputs are fuzzed now.
