# Proofline v1.2/v2: Transitive Decision Impact and Signed Attestations

**Status:** Approved for implementation by the repository owner on 2026-08-23.

## Scope

This milestone extends the deterministic decision-health path. It does not add inferred
relationships, generic RAG, hosted sync, organization identity, or an AI dependency.

v1.2 answers: which still-current decisions are transitively exposed when an explicit dependency
has an unresolved evidence review? v2 answers: did a holder of a trusted Ed25519 private key sign
this exact Decision Evidence Package and optional review receipt?

## Transitive impact contract

Only active `based_on` and `implements` relations propagate impact. For both kinds, the source
decision depends on the target decision, so impact travels from target to source. `supersedes`,
`contradicts`, and `considered` never propagate. Expired or not-yet-effective relations and
obsolete decisions are excluded.

Roots are active or accepted decisions with an `open` or `acknowledged` decision review. A result
contains the root review and decision, impacted decision, ordered relation and decision path,
depth, evaluation time, and a versioned SHA-256 fingerprint. The traversal is cycle-safe. If
multiple paths exist, Proofline chooses the shortest path and then the lexicographically smallest
sequence of relation IDs. Direct root decisions are not returned as transitive impacts.

Impact is derived, read-only state. Closing a root review, expiring/removing a relation, or
obsoleting a dependent decision removes the result without a second mutable ledger. The existing
decision status and review ledger are never changed by impact calculation.

The service supports an explicit `as_of` timestamp for reproducible audits. CLI output defaults to
the current UTC time and emits it. The API exposes workspace-scoped impact results. `check-impacts`
supports text, JSON, and SARIF; any impact exits 1, invalid provenance/database state exits 2.
The decision-health cockpit shows transitive counts and canonical paths without source content.

## Signed attestation contract

The envelope schema is `proofline-signed-attestation-v1`. Its signed statement contains:

- a Decision Evidence Package root hash and artifact ID;
- an optional decision-review receipt hash, review ID, and its bound DEP root;
- an RFC 3339 UTC issuance time;
- the Ed25519 algorithm and SHA-256 key ID derived from the raw public key.

The signature is Ed25519 over a domain-separated canonical JSON statement. The envelope contains
the statement, public-key ID, and base64 signature, but not the public key. Verification requires
an explicitly supplied trusted public key and first verifies envelope shape, key ID, signature,
and subject linkage. Signing first verifies the DEP and optional receipt and rejects a receipt
bound to another DEP.

Key generation writes PKCS#8 PEM private keys with mode `0600` and SubjectPublicKeyInfo PEM public
keys. Existing outputs are never overwritten without `--force`. No key material enters SQLite,
logs, exports, packages, or plugin assets.

Attestation proves integrity and control of a corresponding private key relative to the supplied
public key. It does not prove a legal identity, CA trust chain, trusted timestamp, transparency-log
inclusion, key revocation, or artifact safety. These limitations are mandatory in documentation.

## Portability and compatibility

Existing DEP, review-receipt, export, backup, and database schemas remain compatible. No database
migration is required. `cryptography` becomes a bounded runtime dependency for Ed25519 operations;
all AI-provider egress tests remain zero-egress. Existing unsigned DEP and review receipt verify
commands remain unchanged.

## Validation

- Unit tests cover edge direction, excluded relation kinds, temporal bounds, cycles, competing
  paths, workspace isolation, review closure, obsolete decisions, stable fingerprints, JSON/SARIF,
  and deterministic ordering.
- Attestation tests cover key permissions, known-key sign/verify, wrong key, tampered statement,
  tampered signature, malformed base64, oversized/duplicate-key JSON, DEP/receipt mismatch, atomic
  output, and no private-key leakage.
- API and web tests cover impact list/summary/path rendering and empty/error states.
- Conformance fixtures verify a fixed Ed25519 vector.
- Full Python, web, egress, build, E2E, package conformance, dependency audit, release check, stale
  demo, DEP verification, review-receipt verification, impact check, and attestation verification
  must pass before publication.

## Release boundary

The public release is `2.0.0` because signed attestations add a new trust contract. Publication
requires one clean release commit, built sdist/wheel verification, PyPI upload, public PyPI install
smoke, source tag/release, and an update to the existing public ChatGPT/OpenAI plugin listing. Any
credential, account approval, or directory-review boundary is reported with the exact prepared
artifact and submission state; it is not represented as published until externally confirmed.
