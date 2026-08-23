# Proofline Post-Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the verified post-release gaps without expanding Proofline beyond its local-first, single-user trust boundary.

**Architecture:** Four independently testable deliverables cover exact-ref CI/security, public contracts, real-pilot evidence capture, and fail-closed desktop packaging. GitHub settings are applied only after repository changes pass and merge.

**Tech Stack:** GitHub Actions, Python 3.11+, pytest, PyYAML, FastAPI/CLI runtime, Tauri 2, Rust, npm.

**Spec:** `docs/superpowers/specs/2026-08-24-proofline-post-release-hardening-design.md`

## Global Constraints

- Keep the authoritative product boundary one local user, local SQLite, and user-controlled files.
- Do not claim hosted sync, team production evidence, trusted time, revocation, or signed native distribution without external proof.
- Preserve the immutable 2.0.1 tag and published artifacts.
- New public Markdown uses English, Vietnamese, Japanese order.
- Behavior changes follow red-green TDD; configuration is validated locally and on GitHub.

---

### Task 1: Exact-ref CI and security automation

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/codeql.yml`
- Create: `.github/dependabot.yml`
- Modify: `apps/api/tests/test_public_page.py`

**Interfaces:**
- Consumes: Git ref string supplied as `inputs.source_ref`.
- Produces: full CI results for an explicit immutable ref; CodeQL databases for Python and JavaScript/TypeScript.

- [ ] Add a failing workflow-contract test that parses CI YAML and requires `workflow_dispatch.inputs.source_ref` plus checkout `with.ref` on every CI job.
- [ ] Run `.venv/bin/pytest apps/api/tests/test_public_page.py -q` and confirm the contract fails because manual exact-ref dispatch is absent.
- [ ] Add `workflow_dispatch` with optional `source_ref`, wire every checkout to `${{ inputs.source_ref || github.sha }}`, add pinned CodeQL actions, and add weekly Dependabot ecosystems.
- [ ] Run the focused test, parse all workflow YAML, and run the documentation checker.
- [ ] Commit as `ci: add exact-ref and security verification`.

### Task 2: Issues #7 and #8 contracts

**Files:**
- Modify: `apps/api/tests/test_sarif.py`
- Modify: `docs/cli-reference.md`
- Modify: `apps/api/tests/test_evidence_packages.py`
- Modify: `apps/api/proofline/evidence_packages.py`

**Interfaces:**
- Consumes: `proofline check-decisions --format json`; a verified DEP document.
- Produces: stable content-free JSON keys/exit behavior; responsive offline HTML with complete provenance.

- [ ] Add a failing CLI test asserting exact top-level and finding keys for a blocking review-required result, exit code `1`, and absence of source content.
- [ ] Run the focused test and confirm it fails on the incomplete contract assertion.
- [ ] Make only the required serializer adjustment if the current output is not already sufficient; document the literal example in English, Vietnamese, Japanese.
- [ ] Add a failing HTML test requiring `@media (max-width:640px)`, one-column decision records, smaller container padding, and `overflow-wrap:anywhere`.
- [ ] Run the HTML test and confirm the media-rule failure.
- [ ] Add the minimal responsive CSS without hiding or truncating any field.
- [ ] Run focused CLI/HTML tests and `scripts/check_documentation.py`.
- [ ] Commit as `fix: lock public decision report contracts`.

### Task 3: Real-pilot dataset freezer

**Files:**
- Create: `scripts/freeze_pilot_dataset.py`
- Create: `apps/api/tests/test_freeze_pilot_dataset.py`
- Create: `docs/pilot.md`
- Modify: `docs/README.md`

**Interfaces:**
- Consumes: directory containing `questions.jsonl`, `attempts.csv`, `citations.csv`, `weekly-usage.csv`, and `commercial-signals.csv`.
- Produces: atomic `manifest.json` with `artifact_status=frozen_private_dataset`, explicit dataset version, and SHA-256 for every input.

- [ ] Add failing tests for a valid real dataset, missing files, synthetic/template markers, empty files, and overwrite refusal.
- [ ] Run the focused test and confirm import failure because the freezer does not exist.
- [ ] Implement `freeze_pilot_dataset(directory: Path, dataset_version: str, force: bool = False) -> dict` and a CLI wrapper.
- [ ] Run focused freezer and existing analyzer tests.
- [ ] Add the trilingual collection/freeze/analyze/signoff guide and link it from the documentation hub.
- [ ] Run documentation and leakage checks.
- [ ] Commit as `feat: add fail-closed pilot evidence freezer`.

### Task 4: Desktop release credential gate and workflow

**Files:**
- Create: `scripts/desktop_release_gate.py`
- Create: `apps/api/tests/test_desktop_release_gate.py`
- Create: `.github/workflows/desktop-artifacts.yml`
- Modify: `docs/operations.md`
- Modify: `apps/api/tests/test_release.py`

**Interfaces:**
- Consumes: target platform, `release_grade` flag, and presence-only credential flags.
- Produces: stable JSON approval for experimental builds or fail-closed release-grade errors; macOS/Windows artifacts and qualification receipts from manual Actions runs.

- [ ] Add failing tests for experimental approval, macOS missing Developer ID/notarization inputs, Windows missing Authenticode inputs, and release-grade approval when all presence flags exist.
- [ ] Run the focused test and confirm import failure because the gate does not exist.
- [ ] Implement the pure credential gate and CLI without reading or printing secret values.
- [ ] Add the manual matrix workflow; experimental artifacts remain explicitly unsigned, while release-grade jobs call the gate before build and never auto-publish.
- [ ] Document the trilingual signing/notarization boundary and receipt interpretation.
- [ ] Run focused tests, workflow parsing, desktop debug build, and documentation checks.
- [ ] Commit as `ci: add fail-closed desktop artifact workflow`.

### Task 5: Integration and live GitHub verification

**Files:**
- Modify only files required by verification findings.

**Interfaces:**
- Consumes: completed task commits.
- Produces: reviewed branch, merged main, exact-ref CI run, CodeQL analysis, branch protection, cleaned issue backlog, and repository homepage metadata.

- [ ] Run `make test`, `make check`, `make verify-package-conformance`, `npm run test:e2e`, workflow syntax checks, and desktop build checks.
- [ ] Review the full diff against the design and correct only evidenced gaps.
- [ ] Push `codex/proofline-hardening`, open a PR, wait for CI/CodeQL, and merge only when required checks pass.
- [ ] Dispatch exact-ref CI with `source_ref=v2.0.1` and record the run URL.
- [ ] Close issue #6 as obsolete; close #7 and #8 with merged-test evidence.
- [ ] Set repository homepage and protect `main` with PR, required CI checks, linear history, no force-push, and no deletion.
- [ ] Query branch protection, CodeQL alerts, open issues/PRs, Actions, and clean local state before completion claims.

## Tiếng Việt

Plan chia thành năm task độc lập: exact-ref CI/security; contract issue #7/#8; freezer cho pilot thật; desktop gate/workflow; integration và live GitHub verification. Mọi behavior change phải có failing test trước, còn claim team pilot hoặc signed native artifact bị chặn khi chưa có evidence ngoài repository.

## 日本語

Plan は五つの独立 task に分かれます。Exact-ref CI/security、issue #7/#8 contract、real-pilot freezer、desktop gate/workflow、integration と live GitHub verification です。Behavior change は failing test を先に作り、external evidence がない team pilot や signed native artifact claim は fail closed にします。
