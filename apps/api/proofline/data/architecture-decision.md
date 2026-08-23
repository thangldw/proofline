<!-- Executable source fixture: intentionally English-only to preserve extraction cardinality. -->

# ADR: Immutable evidence index

## Context

Proofline must reproduce which source bytes supported a decision even after the source changes.
Verification must remain available without a hosted service.

## Decision: Store immutable source versions in SQLite

Rationale: Transactional local storage preserves version identity, exact offsets, and hash bindings
inside the same recoverable database.
Status: active

## Assumption: One local runtime owns writes

Rationale: The supported profile has one user and one supervised application runtime.

## Constraint: Package verification works offline

Rationale: Integrity checks cannot depend on model credentials, network access, or mutable search
results.

## Alternative: Keep only the latest source text

Rationale: Mutable text cannot reproduce the exact evidence used for a historical decision.
Status: rejected

## Consequence

Every content change creates a new source version. Review state may change, but historical source
identity and citation spans remain intact.
