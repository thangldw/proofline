# Changelog

Proofline follows semantic versioning. A version number identifies a release surface; production
readiness remains an evidence-based claim documented separately.

## [Unreleased]

No unreleased changes.

## [1.0.0] - 2026-07-16

### Verifiable provenance

- Added deterministic JSON/ZIP Decision Evidence Package v1 with hashed source-version, chunk,
  citation, transformation, artifact, review, and root nodes.
- Added offline package verification, local artifact explanation, content-free semantic diff, and
  fail-closed archive validation.
- Added exact-span, workspace, hash, relationship, deterministic round-trip, and immutable-source
  validation across the full decision lineage.

### Reliability

- Added property and fuzz coverage, an every-version migration matrix, and ingest/export
  crash-recovery tests.
- Added a reproducible local provenance conformance receipt and qualified synthetic
  1K/10K/100K provenance benchmark receipt.
- Preserved verified backup/restore, portable transfer, deletion cascade, offline operation, and
  provider isolation.

### Product and documentation

- Closed the first provenance-depth phase with explicit delivered scope, verification evidence,
  deferrals, and reopening criteria.
- Rewrote the public project page and active documentation around verifiable decision memory.
- Retained explicit boundaries: v1.0.0 is experimental and is not production-qualified.

### Limitations

- No package signature or authenticity trust model.
- No PDF source contract or representative-corpus production scale qualification.
- No real Windows lifecycle receipt, signed/notarized installer, external pilot result,
  real-model quality report, security qualification, or production support commitment.

[Unreleased]: https://github.com/thangldw/proofline/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/thangldw/proofline/releases/tag/v1.0.0
