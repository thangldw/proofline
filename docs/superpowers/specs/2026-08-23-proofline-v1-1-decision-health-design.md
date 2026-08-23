# Proofline v1.1 Decision Health Design

## Objective

Turn Proofline's read-only stale-citation detector into an auditable review workflow without
rewriting decision history or weakening the existing deterministic provenance contract.

This milestone adds a persistent review ledger, context-aware deterministic anchor resolution,
policy-driven CI output, and a focused Decision Health web surface. It preserves the local-first,
single-user boundary. Team identity, hosted synchronization, connector permissions, signatures,
and attestation envelopes belong to later milestones.

## Product semantics

`Decision.status` records the human decision lifecycle (`candidate`, `active`, `accepted`,
`rejected`, or `obsolete`). An accepted decision remains accepted when its evidence changes.
Proofline records that change separately as a `DecisionReview` whose effective health is
`review_required`.

This separation prevents a source-ingestion side effect from rewriting a historical approval.
Resolving a review may re-anchor evidence to a new immutable source version, supersede or obsolete
the decision, or waive the finding. Every resolution records the actor, reason, old hashes, new
hashes, and timestamps in the audit log.

The public demo copy changes from “moves the decision to review” to “opens a review for the
accepted decision.” The decision remains accepted until a human explicitly changes its lifecycle.

## Anchor resolution

Each evidence record gains a deterministic context anchor:

- `anchor_version`: `markdown-context-v1`.
- `section_path`: the ordered Markdown heading path containing the cited span.
- `prefix_sha256`: SHA-256 of up to two normalized non-empty lines before the span.
- `suffix_sha256`: SHA-256 of up to two normalized non-empty lines after the span.

Existing evidence is backfilled from its immutable cited `SourceVersion`. These fields describe
context; they never replace `source_version_id`, offsets, lines, quote, or quote hash.

Evidence also gains binding lifecycle metadata: `binding_state` (`active` or `superseded`),
`superseded_at`, and `superseded_by_id`. Citation payload fields remain immutable. Existing evidence
defaults to `active`; decision reads and package export use active evidence unless a history view is
explicitly requested.

The pure resolver compares one citation with the current immutable source version and returns one
of these states:

- `current`: cited version is current and the stored provenance validates.
- `unchanged`: exactly one quote match exists and its section and context hashes match.
- `moved`: exactly one quote match exists but section or surrounding context changed.
- `ambiguous`: more than one exact quote match exists.
- `changed`: no exact match exists, but a deterministic line-diff candidate overlaps the original
  section.
- `deleted`: neither an exact match nor an overlapping line-diff candidate exists.

Only `current` and `unchanged` are healthy. `moved`, `ambiguous`, `changed`, and `deleted` open a
review. Diff candidates are suggestions only and never count as valid evidence. Tie-breaking is
stable by similarity score descending, then start offset ascending. No model provider participates
in classification.

Corrupt source identity, source-version hashes, spans, or anchor data fail closed with content-free
error codes. The resolver never exposes source or quote content in logs.

## Review ledger

Add a `decision_reviews` table with:

- immutable identifiers: `id`, `workspace_id`, `decision_id`, `evidence_id`,
  `cited_source_version_id`, and `current_source_version_id`;
- deduplication: `finding_fingerprint`, unique across one evidence/current-version/reason tuple;
- classification: `anchor_state`, `severity`, `policy_hash`, and current candidate offsets/lines;
- workflow: `state` (`open`, `acknowledged`, `resolved`, `waived`, `superseded`), `resolution`,
  `actor`, `note`, `opened_at`, `updated_at`, and `closed_at`.

`finding_fingerprint` is SHA-256 over a versioned canonical JSON object containing the decision,
evidence, cited version, current version, and anchor state. Re-running refresh is idempotent.

When a newer source version arrives, a refresh supersedes open findings for the previous current
version and opens findings for the new version. If evidence becomes healthy again, previous open or
acknowledged findings resolve automatically with `resolution=source_restored`; this transition is
audited.

Successful source, folder, and Git ingestion refresh affected decisions after the new immutable
source version and chunks are committed. If review refresh fails, ingestion remains committed but
the ingestion job remains `completed` with stage `review_refresh_failed`, a content-free error code,
and `retryable=true`; the UI reports degraded decision health. This avoids rolling back valid
provenance while making the secondary failure visible and retryable.

The existing `check_decision_health()` and `proofline check-decisions` remain read-only. A separate
`refresh_decision_reviews()` service and `proofline refresh-reviews` command persist ledger state.

## Review actions

The web/API workflow supports:

- `acknowledge`: records that the finding has been seen; it still fails policy unless policy says
  acknowledged findings are non-blocking.
- `waive`: requires a non-empty reason and policy permission; the decision and citation do not
  change.
- `reanchor`: requires the expected current source version, exact proposed offsets, and a non-empty
  reason. Proofline validates the new exact span, inserts a new active evidence record bound to the
  current immutable version, marks the previous binding superseded, updates the decision's current
  evidence version, and resolves the review.
- `obsolete_decision`: marks the decision obsolete and resolves all its open reviews.
- `supersede_decision`: links the old decision to an accepted replacement through an existing
  `DecisionRelation`, marks the old decision obsolete, and resolves its reviews.

Re-anchoring never edits an existing `SourceVersion` or existing citation payload. It updates only
the previous evidence binding lifecycle fields. The old evidence remains queryable through the
timeline and remains present in previously exported packages. The operation uses optimistic
concurrency: a changed current source version returns `409 source_version_changed`.

## Policy

Proofline reads an optional repository-local `proofline.toml` using Python's standard `tomllib`.
The v1 schema is:

```toml
version = 1

[decision_health]
fail_on = ["moved", "ambiguous", "changed", "deleted"]
acknowledged_is_blocking = true
allow_waiver = true
max_open_age_days = 14
```

Unknown keys or values fail closed. With no file, these exact defaults apply. The loader converts
the parsed policy to canonical JSON and stores its SHA-256 in findings and review receipts. Policy
changes do not rewrite old reviews; refresh evaluates current findings under the new policy and
records the new hash.

## CLI and CI contract

`proofline check-decisions` keeps the current text output, read-only database behavior, and exit
codes. It gains:

```text
--format text|json|sarif
--policy PATH
--output PATH
```

`sarif` emits SARIF 2.1.0 with stable rule IDs `proofline/<anchor_state>`, artifact URIs from source
URIs, exact current or cited regions, finding fingerprints as partial fingerprints, policy hash in
run properties, and no source or quote content. Blocking findings exit `1`; invalid provenance,
policy, or database state exits `2` with a content-free code.

`proofline refresh-reviews` persists the ledger and emits a content-free JSON summary. It never runs
implicitly from `check-decisions`.

Add a minimal GitHub Actions workflow that runs Python tests, web/egress tests, lint/build, package
conformance, and `check-decisions --format sarif`. The SARIF file is retained as a workflow artifact;
upload to GitHub code scanning is conditional so forks and repositories without the required
security permission still run the gate.

## API

Add these workspace-scoped endpoints:

- `GET /api/v1/decision-health/overview`
- `GET /api/v1/decision-reviews?state=&anchor_state=&severity=&limit=`
- `POST /api/v1/decision-reviews/refresh`
- `GET /api/v1/decision-reviews/{review_id}`
- `PATCH /api/v1/decision-reviews/{review_id}` for acknowledge or waive
- `POST /api/v1/decision-reviews/{review_id}/reanchor`
- `POST /api/v1/decision-reviews/{review_id}/resolve` for obsolete or supersede actions

All lookups enforce workspace ownership. Mutation endpoints write `AuditEvent` rows in the same
transaction. Errors are stable content-free codes suitable for CLI and UI mapping.

## Web application

Add `Decision Health` as the first primary navigation item. Its badge is the count of open and
acknowledged reviews. The page contains:

- four summary metrics: healthy accepted decisions, review required, overdue, and waived;
- filterable review inbox sorted by severity, age, then deterministic ID;
- a detail panel with decision statement, cited/current version hashes, before/after line locations,
  anchor classification, deterministic candidates, policy result, and audit timeline;
- acknowledge, waive, re-anchor, obsolete, and supersede actions with explicit confirmation where
  evidence or decision lifecycle changes.

The page never labels a decision itself “unapproved” merely because review is required. It renders
“Accepted · review required.” Source text is loaded only when the user opens a detail; list and
overview responses remain content-free.

Implement the page in focused modules (`DecisionHealthView.tsx`, `DecisionReviewDetail.tsx`, and
`decision-health.css`) and extract shared navigation/types from the current `App.tsx` only where
needed. Do not refactor unrelated Notes, Study, Studio, or model-provider flows.

## Evidence packages and compatibility

Decision Evidence Package v1 remains byte-for-byte compatible. Packages created before a source
change retain their accepted review state and remain verifiable; they are historical evidence, not
live-health snapshots.

Add a separate canonical `proofline-decision-review-receipt-v1` document that binds review ID,
finding fingerprint, cited/current source-version hashes, anchor state, policy hash, resolution,
timestamps, and the original DEP root hash. Its verifier is dependency-free and shares canonical
JSON and error-code conventions with DEP v1.

Portable backup/export/import includes decision reviews and new anchor fields. Import validates all
references and fingerprints before mutation. Existing exports remain importable with deterministic
anchor backfill.

## Migration and recovery

A numbered migration adds evidence anchor and binding-lifecycle columns plus `decision_reviews`,
indexes workspace/state, decision, evidence, current version, and fingerprint, then backfills
anchors from immutable cited versions. Migration is atomic and idempotent under the existing
migration runner.

Backup verification treats `decision_reviews` as a required core table only after the migration is
recorded. Restore continues to verify into a separate location before atomic replacement. Live
integrity verification checks anchor hashes, review ownership, fingerprints, allowed transitions,
and audit references.

## Validation

Tests must prove:

- unique unchanged evidence is healthy; moved-context, duplicate, changed, and deleted evidence are
  classified deterministically;
- corrupt identities, versions, spans, anchors, reviews, and fingerprints fail closed;
- ingestion opens one idempotent review and preserves `Decision.status=accepted`;
- subsequent versions supersede, restore, or reopen reviews deterministically;
- re-anchoring preserves the previous citation payload as superseded history while package export
  uses only active evidence;
- acknowledge, waive, re-anchor, obsolete, and supersede actions enforce policy, workspace scope,
  optimistic concurrency, and audit logging;
- legacy text/JSON CLI behavior and database byte/mtime preservation remain intact;
- SARIF contains stable rules, fingerprints, exact locations, policy hash, and no source content;
- DEP v1 canonical vectors and mutation error codes remain unchanged;
- review receipts verify offline and fail every committed mutation vector;
- backup, portable export/import, and integrity verification cover new state;
- the Decision Health UI works at 1280px and 390x844 without horizontal overflow;
- all Python, web, egress, lint, build, evaluation, demo, and release checks pass.

The existing synthetic 100,000-document benchmark remains labeled synthetic. Add a review-refresh
benchmark over 10,000 accepted decisions with deterministic fixture generation, reporting database
size, refresh latency, verification latency, and peak Python memory without claiming hosted or team
production capacity.

## Release boundary

Milestone v1.1 is complete only when the repository is clean, all validation above passes from a
fresh checkout, documentation no longer overstates automatic decision mutation, the missing DEP
format documentation exists, dependency audit has no known high or critical issue in shipped
runtime paths, and an upgrade/rollback receipt has been captured.

PyPI, GitHub, and ChatGPT plugin publication occur only after the later v1.2 and v2 milestones pass
their own specs and the final unified version is fixed. No public version is changed during this
milestone.
