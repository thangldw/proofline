# Provenance phase closeout — 2026-07-16

Status: **closed**.

This phase established Proofline's verifiable decision-memory vertical slice. Closing the phase
means the scoped behavior, tests, documentation, and local evidence receipts are complete. It does
not mean the product is production-ready or that future roadmap items are cancelled.

## Delivered

- Content-hashed source-version, chunk, citation, transformation, artifact, review, and root nodes.
- Deterministic Decision Evidence Package v1 in canonical JSON and ZIP formats.
- Offline `verify-package`, local `explain`, and content-free package `diff` commands.
- Fail-closed span, hash, relationship, archive, and workspace validation.
- Property and fuzz coverage for citation bounds, workspace isolation, round trips, immutability,
  Markdown, and package archives.
- Every-version database migration tests and ingest/export crash-recovery tests.
- Synthetic 1K, 10K, and 100K provenance benchmarks with explicit qualification limits.
- A reproducible, content-free provenance conformance receipt.
- Documentation and public-page copy centered on verifiable decision memory.

## Verification at closeout

The phase closed after these commands passed from the repository root:

```bash
make test
make verify-provenance
make check
```

The closeout run passed 360 Python tests, 56 web tests, lint and format checks, the production web
build, bundle synchronization, egress validation, provenance conformance, and the extraction,
retrieval, and grounded-answer regression evaluations. The existing FastAPI/Starlette `httpx`
deprecation warning remains non-blocking and does not alter application behavior.

## Explicitly deferred

- Package authenticity, signatures, trust roots, key rotation, revocation, and timestamping.
- A PDF source identity and extraction contract, including PDF metadata fuzzing.
- Representative-corpus production scale limits.
- Real Windows lifecycle evidence, signed installers, notarization, and updater rollback.
- External pilot results, real-model quality evidence, and security qualification.
- Collaboration, shared tenancy, broad connectors, rich editing, canvas, graph databases, and
  generic agents.

These items remain future work and must not be inferred from the completed local conformance tests.

## Reopening criteria

Reopen implementation only for a confirmed regression in the closed contracts or for a roadmap
item with explicit scope, acceptance criteria, failure modes, and an evidence plan. New artifact
categories alone are not sufficient reason to reopen this phase.
