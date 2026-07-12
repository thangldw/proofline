# Coding Agent Implementation Spec

**Audience:** Codex, Claude, and other coding agents  
**Document status:** Baseline operating contract  
**Implementation status:** Workflow and root quality commands are implemented

This document explains how an agent should turn an approved Proofline issue into a safe,
reviewable change. It supplements, and never overrides, repository instructions, human
requests, or accepted ADRs.

## Mission

Implement the smallest complete behavior that advances the evidence-first Engineering Decision
Memory vertical slice. Preserve local-first operation, exact provenance, model neutrality, and
human control of derived memory.

Do not expand the task into a rich editor, generic agent framework, broad connector matrix,
cloud platform, or graph visualization.

## Authority order

When instructions conflict, use this order:

1. explicit human request for the current task;
2. repository-level agent instructions and security policy;
3. accepted ADRs and versioned contracts;
4. the product brief and architecture;
5. the roadmap;
6. reasonable implementation judgment within the requested scope.

Report a conflict instead of silently choosing a materially different product direction.

## Required task packet

Before implementation, establish:

```text
Goal:             one observable outcome
In scope:         concrete behavior and files/boundaries
Out of scope:     tempting adjacent work
Acceptance:       testable conditions
Dependencies:     issues, migrations, contracts, providers
Risk:             data loss, security, privacy, egress, compatibility
Verification:     tests, checks, fixtures, evaluation delta
Status language:  what becomes implemented versus remains planned
```

If an item can be resolved safely by inspecting the repository, inspect it. Ask a human only
when the missing decision would materially change user behavior, data compatibility, security,
licensing, or scope.

## Execution protocol

### 1. Inspect

- Read applicable instructions and the documents linked from `docs/README.md`.
- Inspect the worktree, current implementation, tests, migrations, and recent history.
- Identify user-owned changes and avoid overwriting unrelated work.
- Confirm actual commands from repository manifests. At present, use `make setup`, `make test`,
  `make check`, and `make format`; `make dev-api` and `make dev-web` run the two development
  processes. Never assume more commands exist.

### 2. Plan

- Decompose the issue into the smallest end-to-end change.
- Name contracts and invariants affected.
- Identify how failure, retry, deletion, and migration behave.
- Decide which tests prove acceptance before writing broad implementation.
- Add an ADR when the work changes a durable architecture decision.

### 3. Implement

- Keep domain logic independent of framework and provider code.
- Treat imported content and model output as untrusted.
- Use stable, typed errors and visible job states.
- Make writes idempotent where retries are possible.
- Preserve source version and span hashes through every derived object.
- Persist model provenance without secrets or unnecessary source content.
- Keep model-derived memory in `candidate` state until a human review action.
- Avoid opportunistic refactors outside the issue unless required for correctness.

### 4. Verify

Run the exact repository-provided checks relevant to the changed boundary. At minimum:

- focused tests for the change;
- broader tests affected by its contracts;
- type checking and linting;
- migration tests for storage changes;
- golden/evaluation tests for parsing, retrieval, extraction, or answers;
- a manual or automated vertical-path check for user-facing behavior; and
- a worktree diff review for accidental files, secrets, and unsupported claims.

Never report a check as passed unless it was run successfully. If an environment prevents a
check, state the command, blocker, and remaining risk.

### 5. Hand off

The final handoff must be concise and evidence-based:

```text
Outcome:       what now works
Key changes:   important files/boundaries
Verification:  commands and results
Limitations:   planned behavior not implemented
Risks:         migration/security/provider/data caveats
Follow-up:     only the next safe, scoped step
```

Update documentation status when a capability actually becomes implemented. Do not rewrite
planned architecture as past-tense shipped behavior merely because scaffolding exists.

## Definition of done for an agent task

A task is done only when:

- all acceptance criteria within scope are met;
- implementation, tests, schemas, migrations, and docs agree;
- relevant checks pass or explicit blockers and risks are reported;
- error and degraded states are observable;
- no credentials or private pilot data were introduced;
- remote egress remains explicit;
- source/citation invariants and human-review semantics are preserved;
- unrelated user changes remain intact; and
- the handoff distinguishes implemented, tested, untested, planned, and deferred behavior.

## Specialized task rules

### Ingestion

Specify stable identity, version trigger, parser version, supported encoding, span unit,
idempotency key, terminal states, retry policy, and delete/re-index behavior. Include malformed,
renamed, duplicated, and partially processed fixtures.

### Model providers

Implement a capability adapter, not provider checks in domain code. Normalize timeouts, rate
limits, authentication errors, cancellation, and invalid structured output. Add credential-free
contract tests and an explicit health check. Never fall back from local to remote without user
authorization.

### Extraction and memory

Version prompts and schemas. Link every extracted field to evidence where possible. Reject or
dead-letter invalid output. Do not infer confidence from eloquent language. Preserve correction
history and never silently overwrite an accepted memory.

### Retrieval and answering

Keep ranking deterministic under test. Record channel scores in debug data. Bound context and
deduplicate spans. Validate every citation after generation. Prefer insufficient evidence over
an unsupported completion.

### Storage and migrations

Use committed forward migrations and real-database tests. Define rollback/recovery even if a
down migration is unsafe. Never rewrite a migration that may have shipped. Test deletion and
orphan behavior transactionally.

### UI

Show provenance, status, errors, and retry controls before decorative visualization. Imported
content must be escaped or sanitized. Accessibility and keyboard behavior are acceptance
criteria, not later polish.

## Parallel-agent coordination

When multiple agents work concurrently:

- assign non-overlapping ownership by package or clearly bounded file set;
- appoint one integration owner for shared contracts and migrations;
- communicate contract changes before dependents code against them;
- avoid simultaneous edits to workspace manifests, lockfiles, migrations, and shared schemas;
- rebase or reconcile against the current shared worktree before final verification; and
- let the integration owner run repository-wide checks and resolve semantic conflicts.

Agents must not create parallel implementations of the same contract merely to avoid
coordination.

## Stop-and-escalate conditions

Stop and request a maintainer decision when a task requires:

- changing the repository license or contributor-rights model;
- sending data remotely by default;
- destructive migration or deletion semantics not covered by acceptance criteria;
- weakening exact citation or human-review invariants;
- adopting a cloud service, graph database, event broker, or second runtime as a durable
  dependency;
- exposing the local API beyond loopback;
- using private pilot data in tests or logs; or
- expanding into an explicitly deferred product surface.

For ordinary implementation ambiguity within an accepted boundary, make the smallest reversible
choice, document it, and continue.
