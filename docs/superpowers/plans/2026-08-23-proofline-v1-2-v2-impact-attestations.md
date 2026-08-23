# Proofline v1.2/v2 Impact and Attestations Implementation Plan

> Execute sequentially with TDD in `codex/proofline-vnext`; commit each completed task.

**Goal:** Ship deterministic transitive decision impact and Ed25519-signed evidence attestations,
then publish Proofline 2.0.0 to PyPI and update its public ChatGPT plugin listing.

**Architecture:** A read-only graph service derives impacts from the existing review ledger and
explicit temporal relations. A separate cryptographic module signs verified portable artifact
identifiers with domain-separated canonical JSON. CLI/API/web are projections of those services.

---

## Task 1: Deterministic impact graph

- Add failing graph tests for propagation direction, excluded kinds, temporal relations, cycles,
  competing paths, root closure, obsolete nodes, workspace isolation, stable fingerprints, and
  ordering.
- Implement `decision_impacts.py` without persistence or decision mutation.
- Run the focused tests and commit `feat: compute transitive decision impact`.

## Task 2: Impact CLI, SARIF, and API

- Add failing CLI/API tests for text/JSON/SARIF, exit codes, explicit `--as-of`, workspace scope,
  empty state, and content-free failures.
- Add schemas, `/decision-impacts`, `/decision-impacts/summary`, SARIF projection, and
  `check-impacts`.
- Run focused tests and commit `feat: expose transitive decision impact`.

## Task 3: Impact cockpit

- Add failing React tests for summary counts, canonical path, empty/error states, and responsive
  accessible controls.
- Extend the existing decision-health cockpit and API types/client; keep source/quote content out.
- Run web tests/build/egress and commit `feat: show transitive impact paths`.

## Task 4: Ed25519 attestation core

- Add bounded `cryptography` dependency and failing tests for key generation permissions,
  canonical sign/verify, wrong key, tampering, malformed/oversized/duplicate-key envelopes,
  receipt linkage, atomic writes, and no key leakage.
- Implement `attestations.py` with strict schema, domain separation, public-key-derived key IDs,
  and explicit trust limitations.
- Add a fixed conformance vector and commit `feat: sign evidence attestations`.

## Task 5: Attestation CLI and plugin workflow

- Add failing command tests, then implement `generate-attestation-key`, `attest`, and
  `verify-attestation`.
- Update the public plugin skill and standalone workflow documentation to use package commands;
  do not embed private keys or claim identity assurance.
- Run focused CLI/plugin/package-conformance tests and commit
  `feat: add portable attestation workflow`.

## Task 6: v2 release hardening

- Update architecture, operations, security, evidence-package docs, README, changelog, release
  notes, privacy/terms/support only where the new local cryptographic behavior changes them.
- Update every version surface to `2.0.0`, refresh bundled web assets/locks, add CI impact SARIF and
  attestation conformance gates, and update release checks.
- Run full Python/web/egress/build/E2E/conformance/audit/demo/release gates from a clean commit.
- Commit `chore: prepare proofline 2.0.0 release`.

## Task 7: Publish and verify

- Build sdist/wheel, inspect contents/metadata, install each artifact in isolated environments, and
  run CLI/demo/attestation smoke tests.
- Publish to PyPI using the configured credential/trusted-publisher path; verify the public JSON
  metadata and install the exact public artifact.
- Push the clean release source, create/push `v2.0.0`, and create the source release if repository
  permissions allow.
- Update the existing OpenAI/ChatGPT plugin submission to `2.0.0`; record submission/review/public
  listing state exactly and verify the public listing after approval.
