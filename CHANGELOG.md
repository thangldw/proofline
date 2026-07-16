# Changelog

Proofline follows semantic versioning while pre-alpha APIs and schemas may still change. Historical
details remain available in Git tags and GitHub Releases; this file tracks only the active release
line.

## [Unreleased]

### Added

- Added deterministic JSON/ZIP Decision Evidence Package v1 export with hashed source-version,
  chunk, citation, transformation, artifact, and review nodes; offline verification, artifact
  explanation, content-free semantic diff commands, and fail-closed archive validation.
- Added property/fuzz provenance coverage, an every-version migration upgrade matrix, package
  publish and ingestion-stage fault recovery, a machine-readable local conformance receipt, and a
  qualified 1K/10K/100K deterministic provenance benchmark receipt.

### Changed

- Closed the provenance-depth implementation phase on 2026-07-16 with an explicit delivery,
  verification, deferral, and reopening record.
- Consolidated active documentation around v0.14.17 and removed superseded roadmaps, audits,
  historical release-note copies, screenshots, receipts, unused platform icons, and generated
  development artifacts. Product behavior and evaluation fixtures are unchanged.
- Standardized offline system typography and added labelled collaborative-canvas diagrams for
  architecture, lifecycle, evaluation, recovery, roadmap, and release workflows.
- Rewrote the public project page and active Markdown documentation around verifiable decision
  memory, Decision Evidence Packages, provenance depth, and explicit pre-alpha boundaries.

## [0.14.17] - 2026-07-14

### Added

- A real-Windows local release workflow for wheel, frozen sidecar, MSI, NSIS, platform receipt, and
  direct GitHub publication without CI.
- A frozen private-pilot analyzer that verifies hashes, versions, identifiers, foreign keys, and
  citation resolution before emitting aggregate-only metrics.

### Current release surface

- Immutable ingestion and exact evidence across files, notes, folders, and local Git repositories.
- Grounded retrieval, governed memory, study workflows, action proposals, and Evidence Studio.
- Portable evidence archive v2, verified backup/restore, OS keyring support, bundled web launcher,
  and experimental Tauri desktop packaging.

### Limitations

- No real Windows receipt, signed/notarized installer, external pilot result, or production claim.
- Real-model comparison and security qualification have not been completed.

[Unreleased]: https://github.com/thangldw/proofline/compare/v0.14.17...HEAD
[0.14.17]: https://github.com/thangldw/proofline/releases/tag/v0.14.17
