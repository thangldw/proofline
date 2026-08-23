# Proofline v1.1 Decision Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an auditable, deterministic stale-decision review workflow while preserving accepted decision history and Decision Evidence Package v1 compatibility.

**Architecture:** A pure anchor resolver classifies citations without AI, a policy loader decides which findings block, and a review service persists idempotent cases separately from `Decision.status`. CLI, API, and web consume the same service; review receipts, portability, integrity checks, and CI extend the deterministic verification boundary.

**Tech Stack:** Python 3.11+, SQLAlchemy 2, SQLite/FTS5, FastAPI/Pydantic 2, React 18, TypeScript 5, Vitest, pytest/Hypothesis, SARIF 2.1.0.

**Spec:** `docs/superpowers/specs/2026-08-23-proofline-v1-1-decision-health-design.md`

## Global Constraints

- Keep `Decision.status=accepted` when evidence becomes stale; health is represented by `DecisionReview`.
- Preserve Decision Evidence Package v1 canonical bytes, schema, verifier behavior, and mutation error codes.
- Preserve legacy `check-decisions` text/JSON behavior and read-only database byte/mtime behavior.
- Do not log source content, quotes, prompts, secrets, or raw provider errors.
- No AI provider may participate in anchor classification, policy evaluation, review refresh, SARIF, or receipt verification.
- Existing exports remain importable; all new writes use the current export schema after its version is advanced.
- Work in the isolated `codex/proofline-vnext` branch, use TDD for every behavior change, verify after each task, and commit each task independently.

---

### Task 1: Deterministic Context Anchor Resolver

**Files:**
- Create: `apps/api/proofline/anchors.py`
- Create: `apps/api/tests/test_anchors.py`
- Modify: `apps/api/proofline/decision_health.py`
- Modify: `apps/api/tests/test_decision_health.py`

**Interfaces:**
- Produces: `EvidenceAnchor`, `AnchorCandidate`, `AnchorResolution` dataclasses.
- Produces: `build_evidence_anchor(content: str, start_offset: int, end_offset: int) -> EvidenceAnchor`.
- Produces: `resolve_evidence_anchor(*, quote: str, cited_anchor: EvidenceAnchor, current_content: str) -> AnchorResolution`.
- Produces: anchor states `current`, `unchanged`, `moved`, `ambiguous`, `changed`, `deleted`.

- [ ] **Step 1: Write resolver tests that name the production defect**

```python
def test_duplicate_quote_is_ambiguous_instead_of_healthy():
    cited = "# Queue\n\nUse SQLite.\n"
    anchor = build_evidence_anchor(cited, 9, 20)
    current = "# Queue\n\nUse SQLite.\n\n# Cache\n\nUse SQLite.\n"

    result = resolve_evidence_anchor(
        quote="Use SQLite.", cited_anchor=anchor, current_content=current
    )

    assert result.state == "ambiguous"
    assert [item.start_offset for item in result.candidates] == [9, 31]
```

Add separate tests for same-section unchanged, different-section moved, deterministic changed
candidate ordering, deleted content, CRLF normalization, Unicode headings, invalid offsets, and
empty context. In `test_decision_health.py`, add a regression proving duplicate quotes now produce
a finding.

- [ ] **Step 2: Run RED tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_anchors.py apps/api/tests/test_decision_health.py`

Expected: collection fails because `proofline.anchors` does not exist, then the duplicate-quote
regression fails against the current substring-membership behavior.

- [ ] **Step 3: Implement the pure resolver**

Use frozen dataclasses and content-free values:

```python
AnchorState = Literal["current", "unchanged", "moved", "ambiguous", "changed", "deleted"]


@dataclass(frozen=True)
class EvidenceAnchor:
    version: str
    section_path: tuple[str, ...]
    prefix_sha256: str
    suffix_sha256: str


@dataclass(frozen=True)
class AnchorCandidate:
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    section_path: tuple[str, ...]
    similarity: float


@dataclass(frozen=True)
class AnchorResolution:
    state: AnchorState
    candidates: tuple[AnchorCandidate, ...]
```

Parse ATX Markdown headings without external libraries. Normalize context lines with Unicode NFC,
trim surrounding whitespace, and collapse internal whitespace. Hash canonical newline-joined
context with SHA-256. Use `difflib.SequenceMatcher(autojunk=False)` only to suggest `changed`
candidates; require same terminal section heading and similarity `>=0.60`. Suggestions remain
stale regardless of score.

- [ ] **Step 4: Replace substring health logic with the resolver**

In `check_decision_health`, build the cited anchor from the immutable cited version and use the
resolver for newer versions. Emit no finding for `unchanged`; emit `reason=anchor_state` for every
other non-current state. Preserve all existing provenance validation before resolution.

- [ ] **Step 5: Run GREEN and regression tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_anchors.py apps/api/tests/test_decision_health.py`

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/proofline/anchors.py apps/api/proofline/decision_health.py \
  apps/api/tests/test_anchors.py apps/api/tests/test_decision_health.py
git commit -m "feat: classify stale evidence anchors deterministically"
```

---

### Task 2: Versioned Decision Health Policy

**Files:**
- Create: `apps/api/proofline/decision_policy.py`
- Create: `apps/api/tests/test_decision_policy.py`
- Create: `proofline.toml`

**Interfaces:**
- Produces: `DecisionHealthPolicy(version, fail_on, acknowledged_is_blocking, allow_waiver, max_open_age_days)`.
- Produces: `load_decision_policy(path: Path | None) -> DecisionHealthPolicy`.
- Produces: `policy_sha256(policy: DecisionHealthPolicy) -> str`.
- Produces: `DecisionPolicyError(code: str)` with content-free codes.

- [ ] **Step 1: Write policy parser tests**

```python
def test_default_policy_has_stable_hash():
    policy = load_decision_policy(None)
    assert policy.fail_on == frozenset({"moved", "ambiguous", "changed", "deleted"})
    assert policy.acknowledged_is_blocking is True
    assert policy.allow_waiver is True
    assert policy.max_open_age_days == 14
    assert policy_sha256(policy) == policy_sha256(load_decision_policy(None))
```

Add tests for the committed `proofline.toml`, unknown top-level keys, unknown section keys, wrong
version, invalid states, booleans encoded as integers, and days outside `1..3650`.

- [ ] **Step 2: Run RED tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_decision_policy.py`

Expected: fail because `proofline.decision_policy` does not exist.

- [ ] **Step 3: Implement strict TOML parsing and canonical hashing**

Use `tomllib`, reject extra keys, and serialize this exact canonical object with sorted compact JSON:

```python
{
    "acknowledged_is_blocking": policy.acknowledged_is_blocking,
    "allow_waiver": policy.allow_waiver,
    "fail_on": sorted(policy.fail_on),
    "max_open_age_days": policy.max_open_age_days,
    "version": policy.version,
}
```

Errors are `policy_file_unavailable`, `policy_toml_invalid`, `policy_schema_invalid`, or
`policy_version_unsupported` and never include paths or TOML content.

- [ ] **Step 4: Add the default repository policy**

```toml
version = 1

[decision_health]
fail_on = ["moved", "ambiguous", "changed", "deleted"]
acknowledged_is_blocking = true
allow_waiver = true
max_open_age_days = 14
```

- [ ] **Step 5: Run GREEN tests and lint**

Run: `.venv/bin/pytest -q apps/api/tests/test_decision_policy.py && .venv/bin/ruff check apps/api/proofline/decision_policy.py apps/api/tests/test_decision_policy.py`

Expected: pass with no warnings.

- [ ] **Step 6: Commit**

```bash
git add proofline.toml apps/api/proofline/decision_policy.py apps/api/tests/test_decision_policy.py
git commit -m "feat: add versioned decision health policy"
```

---

### Task 3: Review Ledger Schema and Migration v22

**Files:**
- Modify: `apps/api/proofline/models.py`
- Modify: `apps/api/proofline/migrations.py`
- Modify: `apps/api/proofline/schemas.py`
- Modify: `apps/api/tests/test_migrations.py`
- Create: `apps/api/tests/test_decision_review_models.py`

**Interfaces:**
- Produces: `DecisionReview` SQLAlchemy model and evidence binding/anchor columns.
- Produces: `DecisionReviewRead`, `DecisionReviewOverview`, `DecisionReviewAction`,
  `DecisionReviewReanchor`, and `DecisionReviewResolve` Pydantic models.
- Migration number: `22`, description `decision evidence review ledger`.

- [ ] **Step 1: Write migration and model tests**

Create a v21 database with one accepted decision and evidence, run `initialize_database()` twice,
then assert:

```python
assert versions == list(range(1, 23))
assert evidence["anchor_version"] == "markdown-context-v1"
assert evidence["binding_state"] == "active"
assert evidence["prefix_sha256"] == hashlib.sha256(b"").hexdigest()
assert review_columns >= {
    "finding_fingerprint",
    "anchor_state",
    "policy_hash",
    "state",
    "resolution",
}
```

Model tests must prove the fingerprint unique constraint and source-version/evidence foreign keys
are enforced.

- [ ] **Step 2: Run RED tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_migrations.py apps/api/tests/test_decision_review_models.py`

Expected: fail because migration 22 and `DecisionReview` are absent.

- [ ] **Step 3: Add evidence lifecycle and anchor fields**

Add nullable migration columns, backfill every row via `build_evidence_anchor`, then expose non-null
ORM defaults:

```python
anchor_version: Mapped[str] = mapped_column(String(40), default="markdown-context-v1")
section_path: Mapped[list[str]] = mapped_column(JSON, default=list)
prefix_sha256: Mapped[str] = mapped_column(String(64))
suffix_sha256: Mapped[str] = mapped_column(String(64))
binding_state: Mapped[str] = mapped_column(String(20), default="active", index=True)
binding_root_id: Mapped[str] = mapped_column(String(36), index=True)
superseded_at: Mapped[datetime | None] = mapped_column(nullable=True)
superseded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
```

- [ ] **Step 4: Add `DecisionReview` and indexes**

Use UUID primary key, workspace/decision/evidence/version foreign keys, `String` enums, nullable
candidate coordinates, and a unique index on `finding_fingerprint`. Add composite indexes for
`(workspace_id, state, opened_at)` and `(decision_id, state)`.

- [ ] **Step 5: Add strict API schemas**

Actions use discriminated literal values:

```python
class DecisionReviewAction(BaseModel):
    action: Literal["acknowledge", "waive"]
    reason: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def require_waiver_reason(self):
        if self.action == "waive" and not (self.reason or "").strip():
            raise ValueError("waive requires a reason")
        return self
```

- [ ] **Step 6: Run GREEN tests and full migration suite**

Run: `.venv/bin/pytest -q apps/api/tests/test_migrations.py apps/api/tests/test_decision_review_models.py`

Expected: pass; migration is idempotent.

- [ ] **Step 7: Commit**

```bash
git add apps/api/proofline/models.py apps/api/proofline/migrations.py \
  apps/api/proofline/schemas.py apps/api/tests/test_migrations.py \
  apps/api/tests/test_decision_review_models.py
git commit -m "feat: add decision review ledger schema"
```

---

### Task 4: Idempotent Review Refresh Service and Ingestion Integration

**Files:**
- Create: `apps/api/proofline/decision_reviews.py`
- Create: `apps/api/tests/test_decision_reviews.py`
- Modify: `apps/api/proofline/decision_health.py`
- Modify: `apps/api/proofline/ingestion.py`
- Modify: `apps/api/tests/test_ingestion.py`
- Modify: `apps/api/tests/test_ingestion_recovery.py`

**Interfaces:**
- Produces: `review_fingerprint(...) -> str`.
- Produces: `refresh_decision_reviews(session: Session, *, workspace_id: str, source_ids: set[str] | None = None, policy: DecisionHealthPolicy | None = None) -> ReviewRefreshSummary`.
- Produces: `DecisionReviewError(code: str)`.

- [ ] **Step 1: Write review refresh RED tests**

```python
def test_refresh_opens_one_review_without_changing_accepted_decision(session):
    source, decision = accepted_decision(session)
    ingest_changed_version(session, source)

    first = refresh_decision_reviews(session, workspace_id=source.workspace_id)
    second = refresh_decision_reviews(session, workspace_id=source.workspace_id)

    assert first.opened == 1
    assert second.opened == 0
    assert session.get(Decision, decision.id).status == "accepted"
    assert session.scalar(select(func.count()).select_from(DecisionReview)) == 1
```

Add tests for superseding an old finding on another source revision, `source_restored`, workspace
scope, policy hash changes, corrupt provenance rollback, and content-free errors.

- [ ] **Step 2: Run RED service tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_decision_reviews.py`

Expected: fail because the service is absent.

- [ ] **Step 3: Implement canonical fingerprints and refresh transitions**

Hash compact sorted JSON containing schema `proofline-decision-review-finding-v1`, decision ID,
evidence ID, cited/current version IDs, and anchor state. Query only active evidence on accepted or
active decisions in the workspace. Flush all transitions and `AuditEvent` rows, but leave commit
ownership with the caller.

- [ ] **Step 4: Integrate staged ingestion after provenance commit**

After successful `ingest_source(..., commit=False)`, call refresh for `{source.id}` in the same
transaction that marks the job succeeded. If refresh raises `DecisionReviewError`, keep the source
and version, set job `state="failed"`, `stage="review_refresh"`, the safe error code,
`retryable=True`, and commit. Extend `retry_ingestion_job` to claim this stage and retry review
refresh without replaying source ingestion.

- [ ] **Step 5: Run ingestion RED/GREEN cycle**

Run: `.venv/bin/pytest -q apps/api/tests/test_decision_reviews.py apps/api/tests/test_ingestion.py apps/api/tests/test_ingestion_recovery.py`

Expected: pass; existing idempotency and recovery tests remain green.

- [ ] **Step 6: Commit**

```bash
git add apps/api/proofline/decision_reviews.py apps/api/proofline/decision_health.py \
  apps/api/proofline/ingestion.py apps/api/tests/test_decision_reviews.py \
  apps/api/tests/test_ingestion.py apps/api/tests/test_ingestion_recovery.py
git commit -m "feat: refresh decision reviews after ingestion"
```

---

### Task 5: Audited Review Actions and Evidence Re-anchoring

**Files:**
- Modify: `apps/api/proofline/decision_reviews.py`
- Create: `apps/api/tests/test_decision_review_actions.py`
- Modify: `apps/api/proofline/evidence_packages.py`
- Modify: `apps/api/tests/test_evidence_packages.py`

**Interfaces:**
- Produces: `apply_review_action(session, review_id, action, *, actor, policy) -> DecisionReview`.
- Produces: `reanchor_review(session, review_id, payload, *, actor) -> DecisionReview`.
- Produces: `resolve_review(session, review_id, payload, *, actor) -> DecisionReview`.

- [ ] **Step 1: Write action and concurrency tests**

Cover acknowledge, waiver disabled, waiver reason required, second action conflict, cross-workspace
404 mapping input, stale expected-version conflict, exact re-anchor span validation, obsolete, and
supersede. Prove re-anchor inserts new active evidence, marks only prior active evidence
superseded, preserves its `binding_root_id`, keeps citation payload fields unchanged, and writes one
audit event.

- [ ] **Step 2: Run RED tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_decision_review_actions.py apps/api/tests/test_evidence_packages.py`

Expected: fail because action functions are absent and package export still includes all evidence.

- [ ] **Step 3: Implement explicit transition matrix**

```python
ALLOWED_TRANSITIONS = {
    "open": {"acknowledged", "waived", "resolved", "superseded"},
    "acknowledged": {"waived", "resolved", "superseded"},
    "resolved": set(),
    "waived": set(),
    "superseded": set(),
}
```

Use `UPDATE ... WHERE state=:expected AND current_source_version_id=:expected_version` and require
one affected row. Write `AuditEvent` before commit. `supersede_decision` requires an accepted target
in the same workspace and creates one `supersedes` relation.

- [ ] **Step 4: Filter current reads and DEP export to active evidence**

Update decision serialization and `build_decision_package()` to include only
`binding_state="active"`. Preserve canonical DEP vectors because migrated legacy rows default to
active and no DEP fields change.

- [ ] **Step 5: Run GREEN tests and DEP conformance**

Run: `.venv/bin/pytest -q apps/api/tests/test_decision_review_actions.py apps/api/tests/test_evidence_packages.py apps/api/tests/test_provenance_conformance.py`

Expected: pass with unchanged DEP root hashes for canonical fixtures.

- [ ] **Step 6: Commit**

```bash
git add apps/api/proofline/decision_reviews.py apps/api/proofline/evidence_packages.py \
  apps/api/tests/test_decision_review_actions.py apps/api/tests/test_evidence_packages.py
git commit -m "feat: add audited decision review actions"
```

---

### Task 6: Read-only CLI Policy Gate and SARIF 2.1.0

**Files:**
- Create: `apps/api/proofline/sarif.py`
- Create: `apps/api/tests/test_sarif.py`
- Modify: `apps/api/proofline/cli.py`
- Modify: `apps/api/tests/test_decision_health.py`

**Interfaces:**
- Produces: `build_decision_health_sarif(findings, policy) -> dict`.
- Extends: `proofline check-decisions --format text|json|sarif --policy PATH --output PATH`.
- Adds: `proofline refresh-reviews --policy PATH`.

- [ ] **Step 1: Write SARIF and compatibility tests**

Assert SARIF `$schema`, version `2.1.0`, stable rule IDs, file URI, one-based region, policy hash,
fingerprint, no quote/source content, deterministic JSON, atomic output refusal, and exit codes 0/1/2.
Keep the existing tests that compare database bytes and mtime before/after `check-decisions`.

- [ ] **Step 2: Run RED tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_sarif.py apps/api/tests/test_decision_health.py`

Expected: fail because `sarif` is not accepted and output/policy flags are absent.

- [ ] **Step 3: Implement SARIF projection**

Use rule IDs `proofline/moved`, `proofline/ambiguous`, `proofline/changed`, and
`proofline/deleted`; map severity to SARIF `warning` except overdue findings, which are `error`.
Use finding fingerprint under `partialFingerprints.prooflineFinding/v1`. Never include snippets.

- [ ] **Step 4: Extend CLI without initializing a missing database**

Parse policy before opening the database. For `--output`, use the existing atomic JSON writer and
refuse overwrite. `refresh-reviews` initializes/migrates an existing writable database, commits the
service summary, and returns content-free JSON.

- [ ] **Step 5: Run GREEN tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_sarif.py apps/api/tests/test_decision_health.py`

Expected: pass; read-only tests preserve bytes, mtime, and directory entries.

- [ ] **Step 6: Commit**

```bash
git add apps/api/proofline/sarif.py apps/api/proofline/cli.py \
  apps/api/tests/test_sarif.py apps/api/tests/test_decision_health.py
git commit -m "feat: emit decision health SARIF"
```

---

### Task 7: Workspace-scoped Decision Review API

**Files:**
- Create: `apps/api/proofline/decision_review_api.py`
- Create: `apps/api/tests/test_decision_review_api.py`
- Modify: `apps/api/proofline/api.py`
- Modify: `apps/api/proofline/main.py`

**Interfaces:**
- Produces the seven endpoints listed in the design spec under `/api/v1`.
- Keeps `apps/api/proofline/api.py` compatibility by including a focused child router.

- [ ] **Step 1: Write endpoint tests before the router**

Use the real test database and assert overview counts, deterministic sorting, filters, limits
`1..200`, content-free list payloads, detail candidates, workspace isolation, 409 optimistic
concurrency, action audit events, and stable HTTP error detail codes.

- [ ] **Step 2: Run RED tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_decision_review_api.py`

Expected: every new endpoint returns 404.

- [ ] **Step 3: Implement a focused router**

Reuse `resolve_workspace_id`; add a local `get_workspace_review()` helper; map
`DecisionReviewError.code` to 404 for ownership/not-found, 409 for state/version conflicts, 422 for
policy/action validation, and 500 only for fail-closed integrity errors. Do not return exception
messages.

- [ ] **Step 4: Include the router and keep legacy API tests green**

Run: `.venv/bin/pytest -q apps/api/tests/test_decision_review_api.py apps/api/tests/test_api.py apps/api/tests/test_workspaces.py`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/proofline/decision_review_api.py apps/api/proofline/api.py \
  apps/api/proofline/main.py apps/api/tests/test_decision_review_api.py
git commit -m "feat: expose decision review API"
```

---

### Task 8: Decision Health Web Cockpit

**Files:**
- Create: `apps/web/src/DecisionHealthView.tsx`
- Create: `apps/web/src/DecisionReviewDetail.tsx`
- Create: `apps/web/src/DecisionHealthView.test.tsx`
- Create: `apps/web/src/decision-health.css`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/api.test.ts`
- Modify: `apps/web/src/types.ts`
- Modify: `apps/web/e2e/vertical-path.spec.ts`

**Interfaces:**
- Produces: `DecisionReview`, `DecisionHealthOverview`, `DecisionReviewFilters`, and action payload TypeScript types.
- Produces: `api.decisionHealthOverview()`, `api.decisionReviews(filters)`, `api.decisionReview(id)`, `api.refreshDecisionReviews()`, `api.updateDecisionReview(id, payload)`, `api.reanchorDecisionReview(id, payload)`, and `api.resolveDecisionReview(id, payload)`.

- [ ] **Step 1: Write API client and view RED tests**

Test repeated filters, workspace header, summary cards, “Accepted · review required,” deterministic
inbox order, details loaded only on open, no quote in list rendering, acknowledge, waiver reason,
re-anchor confirmation, obsolete confirmation, loading/error/empty states, and badge count.

- [ ] **Step 2: Run RED web tests**

Run: `npm --workspace @proofline/web test -- --run src/api.test.ts src/DecisionHealthView.test.tsx`

Expected: fail because types, API methods, and components are absent.

- [ ] **Step 3: Implement types and API methods**

All methods use the existing `request<T>` wrapper so workspace scope and content-free error mapping
remain consistent. Encode filters with `URLSearchParams` and omit empty values.

- [ ] **Step 4: Implement focused cockpit components**

Render four metric cards, semantic table/list markup, state/severity filters, and a lazy detail
drawer. Use existing CSS variables; add no remote assets or analytics. Destructive lifecycle actions
require a confirmation dialog; acknowledge does not.

- [ ] **Step 5: Add navigation and refresh integration**

Make `Decision Health` the first nav item and default view. Fetch only overview during the global
refresh; the page owns review list/detail requests to avoid adding source content or unbounded work
to application startup.

- [ ] **Step 6: Run GREEN unit and egress tests**

Run: `npm run test:web`

Expected: all web and three egress tests pass.

- [ ] **Step 7: Run responsive e2e**

Run: `npm run test:e2e -- --grep "decision health"`

Expected: pass at desktop and 390x844 with `document.documentElement.scrollWidth <= innerWidth`.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/DecisionHealthView.tsx apps/web/src/DecisionReviewDetail.tsx \
  apps/web/src/DecisionHealthView.test.tsx apps/web/src/decision-health.css \
  apps/web/src/App.tsx apps/web/src/api.ts apps/web/src/api.test.ts apps/web/src/types.ts \
  apps/web/e2e/vertical-path.spec.ts
git commit -m "feat: add decision health cockpit"
```

---

### Task 9: Review Receipts, Portability, Backup, and Integrity

**Files:**
- Create: `apps/api/proofline/review_receipts.py`
- Create: `apps/api/tests/test_review_receipts.py`
- Create: `spec/decision-review-receipt/v1/schema.json`
- Create: `spec/decision-review-receipt/v1/test-vectors/valid-minimal.json`
- Create: `spec/decision-review-receipt/v1/test-vectors/expected.json`
- Create: `spec/decision-review-receipt/v1/test-vectors/mutations.json`
- Modify: `apps/api/proofline/portability.py`
- Modify: `apps/api/proofline/portable_import.py`
- Modify: `apps/api/proofline/backup.py`
- Modify: `apps/api/proofline/integrity.py`
- Modify: `apps/api/proofline/cli.py`
- Modify: `skills/manage-evidence-decisions/scripts/proofline_package.py`
- Modify: `apps/api/tests/test_portability.py`
- Modify: `apps/api/tests/test_portable_import.py`
- Modify: `apps/api/tests/test_backup.py`
- Modify: `apps/api/tests/test_integrity.py`
- Modify: `apps/api/tests/test_openai_plugin_bundle.py`

**Interfaces:**
- Produces: `build_review_receipt(review, dep_root_hash) -> dict` and `verify_review_receipt(document) -> dict`.
- Adds CLI: `export-review-receipt REVIEW_ID --package PACKAGE --output PATH` and `verify-review-receipt PATH`.
- Adds plugin verifier command: `proofline_package.py verify-review PATH`.

- [ ] **Step 1: Commit schema/vector tests first**

The valid vector contains only UUIDs, hashes, states, policy hash, timestamps, and DEP root—no
source or quote content. Mutation vectors change each bound hash, state, timestamp, and root and
expect one stable error code per mutation.

- [ ] **Step 2: Run RED receipt tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_review_receipts.py apps/api/tests/test_openai_plugin_bundle.py`

Expected: fail because receipt builders and plugin command are absent.

- [ ] **Step 3: Implement canonical receipt build/verify and CLI**

Use the existing canonical JSON and atomic writer. Verification recomputes `receipt_hash` over the
document without that field, validates all SHA-256 strings and timestamps, and verifies the supplied
DEP before allowing export.

- [ ] **Step 4: Advance portable export to v3 with legacy upgrades**

Add active/superseded evidence metadata and reviews to the canonical table order and counts. Upgrade
v1/v2 documents by deriving active bindings and an empty review list. Preview, replace, and merge
validate anchors, fingerprints, states, and foreign keys before mutation.

- [ ] **Step 5: Extend backup and live integrity checks**

Add `decision_reviews` to required tables after migration 22. Verify anchor hashes, evidence binding
chains without cycles, exactly one active binding per `(decision_id, binding_root_id)`, review
ownership/fingerprint/state, and audit object references.

- [ ] **Step 6: Run GREEN recovery suites**

Run: `.venv/bin/pytest -q apps/api/tests/test_review_receipts.py apps/api/tests/test_portability.py apps/api/tests/test_portable_import.py apps/api/tests/test_backup.py apps/api/tests/test_integrity.py apps/api/tests/test_openai_plugin_bundle.py`

Expected: pass, including old export and DEP fixtures.

- [ ] **Step 7: Commit**

```bash
git add apps/api/proofline/review_receipts.py apps/api/proofline/portability.py \
  apps/api/proofline/portable_import.py apps/api/proofline/backup.py \
  apps/api/proofline/integrity.py apps/api/proofline/cli.py \
  skills/manage-evidence-decisions/scripts/proofline_package.py \
  spec/decision-review-receipt apps/api/tests/test_review_receipts.py \
  apps/api/tests/test_portability.py apps/api/tests/test_portable_import.py \
  apps/api/tests/test_backup.py apps/api/tests/test_integrity.py \
  apps/api/tests/test_openai_plugin_bundle.py
git commit -m "feat: verify portable decision review receipts"
```

---

### Task 10: CI, Security, Documentation, Benchmark, and Milestone Gate

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `docs/evidence-packages.md`
- Create: `scripts/benchmark_decision_reviews.py`
- Create: `apps/api/tests/test_decision_review_benchmark.py`
- Modify: `apps/api/proofline/provenance_benchmark.py`
- Modify: `apps/api/proofline/stale_decision_demo.py`
- Modify: `apps/api/tests/test_decision_health.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `SECURITY.md`
- Modify: `Makefile`
- Modify: `package-lock.json`

**Interfaces:**
- CI jobs: Python/test-and-quality, web/test-build-egress, package-conformance, decision-health-SARIF.
- Benchmark schema: `proofline-decision-review-refresh-benchmark-v1`.

- [ ] **Step 1: Write failing documentation/release and benchmark tests**

Add tests that require the DEP documentation link target, correct demo wording, committed default
policy, CI commands, SARIF artifact path, benchmark qualification, and no hosted/team claim.

- [ ] **Step 2: Run RED tests**

Run: `.venv/bin/pytest -q apps/api/tests/test_public_page.py apps/api/tests/test_release.py apps/api/tests/test_decision_review_benchmark.py`

Expected: fail on missing docs, workflow, and benchmark.

- [ ] **Step 3: Fix the npm high vulnerability with the smallest lockfile change**

Run: `npm audit --json` and identify the dependency path. Update only the owning direct dependency
or add a root `overrides` entry for `nanoid` at the first patched compatible version. Run
`npm install`, then require `npm audit --omit=dev --audit-level=high` and the full web suite to pass.

- [ ] **Step 4: Add minimal CI and technical documentation**

Use Python 3.11 and Node 20, `npm ci`, editable dev install, `make test`, `make check`, DEP/review
receipt conformance, and SARIF generation. Document root hash as integrity, not authenticity; explain
accepted decision versus review state; retain explicit single-user/local-first limitations.

- [ ] **Step 5: Implement and run the qualified benchmark**

Generate 10,000 accepted synthetic decisions in a temporary SQLite database, revise their sources,
refresh reviews, verify ledger integrity, and report database bytes, refresh/verify latency, and
peak Python memory. The JSON qualification must say it excludes connectors, auth, hosted sync,
network, and team production capacity.

- [ ] **Step 6: Run the complete milestone gate**

Run:

```bash
make test
make check
npm run test:e2e
.venv/bin/proofline demo stale-decision --output-dir /tmp/proofline-v1-1-demo
.venv/bin/proofline verify-package /tmp/proofline-v1-1-demo/evidence.zip
.venv/bin/proofline verify-review-receipt /tmp/proofline-v1-1-demo/decision-review.json
.venv/bin/python scripts/release_check.py --tag v1.0.1
npm audit --omit=dev --audit-level=high
```

Expected: all tests/checks pass; demo says “Accepted · review required”; both package and review
receipt verify; no runtime high/critical vulnerability; the version remains `1.0.1` because this is
an internal milestone.

- [ ] **Step 7: Commit milestone evidence**

```bash
git add .github/workflows/ci.yml docs/evidence-packages.md README.md docs/architecture.md \
  docs/OPERATIONS.md SECURITY.md Makefile package-lock.json \
  scripts/benchmark_decision_reviews.py apps/api/proofline/provenance_benchmark.py \
  apps/api/proofline/stale_decision_demo.py apps/api/tests/test_decision_health.py \
  apps/api/tests/test_decision_review_benchmark.py apps/api/tests/test_public_page.py \
  apps/api/tests/test_release.py
git commit -m "chore: gate decision health milestone"
```

---

## Milestone Completion Review

- [ ] Map every design-spec validation bullet to a passing test or command output.
- [ ] Confirm `git status --short` is clean and commits are task-scoped.
- [ ] Confirm no public version, tag, GitHub release, PyPI artifact, or plugin submission changed.
- [ ] Record exact test counts, dependency-audit scope, benchmark environment, and synthetic qualification.
- [ ] Start a separate approved spec and plan for v1.2 transitive impact and attestations.
