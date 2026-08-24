# Proofline v2.0.2 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release the hardening currently on `main` as one source-aligned Proofline v2.0.2 across PyPI, GitHub Releases, and the OpenAI Plugins Directory.

**Architecture:** Treat the existing `main` commit as the behavioral baseline and make one release-preparation commit that changes version contracts and release documentation only. Merge through protected `main`, publish Python artifacts with Trusted Publishing, tag the exact verified commit, then package and submit the skills-only plugin from that same tag.

**Tech Stack:** Python 3.11+, uv, pytest, Ruff, npm workspaces, Vitest, Playwright, Rust/Tauri metadata, GitHub Actions, PyPI Trusted Publishing, OpenAI Plugins portal.

**Spec:** `docs/superpowers/specs/2026-08-24-proofline-v2.0.2-release-design.md`

## Global Constraints

- Release version is exactly `2.0.2`; Git tag is exactly `v2.0.2`.
- Preserve immutable v2.0.1 artifacts and historical evidence.
- Exclude pending dependency-major updates and unsigned desktop packages.
- Preserve English, Vietnamese, Japanese documentation order.
- Never claim plugin approval or publication before external observation.
- Require user confirmation immediately before the final portal Submit action.

---

### Task 1: Version-contract red gate

**Files:**
- Modify: `apps/api/tests/test_openai_plugin_bundle.py`
- Modify: `apps/api/tests/test_release.py`
- Modify: `apps/api/tests/test_public_page.py`

**Interfaces:**
- Consumes: existing release metadata validation and documentation contracts.
- Produces: assertions for current version `2.0.2`, its workflow artifact names, current release page, and plugin runtime boundary.

- [ ] **Step 1: Change only current-version assertions from 2.0.1 to 2.0.2**

Keep historical v2.0.1 record assertions unchanged; update only tests that identify the current release or current plugin runtime.

- [ ] **Step 2: Run the focused tests and verify they fail for missing 2.0.2 surfaces**

Run:

```bash
.venv/bin/pytest apps/api/tests/test_release.py apps/api/tests/test_openai_plugin_bundle.py apps/api/tests/test_public_page.py -q
```

Expected: failures identify 2.0.1 metadata, workflow artifact names, documentation links, or missing `docs/releases/v2.0.2.md`.

### Task 2: Align release metadata and documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `apps/api/proofline/__init__.py`
- Modify: `apps/web/package.json`
- Modify: `apps/desktop/package.json`
- Modify: `apps/desktop/src-tauri/Cargo.toml`
- Modify: `apps/desktop/src-tauri/Cargo.lock`
- Modify: `apps/desktop/src-tauri/tauri.conf.json`
- Modify: `package-lock.json`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.kimi-plugin/plugin.json`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/publish-pypi.yml`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `SECURITY.md`
- Modify: `docs/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/submission/openai-plugin.md`
- Modify: `scripts/check_documentation.py`
- Modify: `skills/manage-evidence-decisions/SKILL.md`
- Modify: `skills/manage-evidence-decisions/references/commands.md`
- Create: `docs/releases/v2.0.2.md`

**Interfaces:**
- Consumes: the `2.0.2` assertions from Task 1 and hardening history from `v2.0.1..b50c33b`.
- Produces: source-aligned package, runtime, web, desktop, workflow, lockfile, plugin, and current-documentation versions.

- [ ] **Step 1: Set all machine-readable current versions to 2.0.2**

Use package-manager lockfile updates where available, then verify `scripts/release_check.py --tag v2.0.2` reads every required surface as `2.0.2`.

- [ ] **Step 2: Update current-version prose without changing historical evidence**

Keep the v2.0.1 release page, submission identifier, submitted ZIP digest, public timestamps, prior release-process observation, and post-release hardening design statements intact. Point current navigation, architecture, security, plugin runtime instructions, and documentation contract to v2.0.2.

- [ ] **Step 3: Add trilingual release notes and changelog entries**

Describe exact-ref CI, CodeQL/Dependabot hardening, content-free decision-health output, pilot freezer, and experimental desktop build gates. State that real-team pilot and signed/notarized desktop release evidence remain unavailable.

- [ ] **Step 4: Run focused release and documentation tests**

Run:

```bash
.venv/bin/pytest apps/api/tests/test_release.py apps/api/tests/test_openai_plugin_bundle.py apps/api/tests/test_public_page.py apps/api/tests/test_documentation_contract.py -q
.venv/bin/python scripts/release_check.py --tag v2.0.2
```

Expected: all focused tests pass and release check returns `{"status":"ready","tag":"v2.0.2"}`.

- [ ] **Step 5: Commit the release preparation**

```bash
git add .
git commit -m "release: prepare v2.0.2"
```

### Task 3: Qualify and integrate the exact release commit

**Files:**
- Verify: entire repository

**Interfaces:**
- Consumes: clean release-preparation commit.
- Produces: locally qualified commit merged through protected `main` with all required remote checks green.

- [ ] **Step 1: Run the full local release gates**

```bash
make test
make check
make verify-package-conformance
npm run test:e2e
make audit
.venv/bin/python scripts/release_check.py --tag v2.0.2
```

- [ ] **Step 2: Build and qualify wheel and sdist from a clean archive of the commit**

Use `python -m build`, `scripts/verify_release_artifacts.py`, `twine check`, and `scripts/qualify_python_artifact.py` against both exact v2.0.2 files; compute SHA-256 digests.

- [ ] **Step 3: Request code review, push, and open a PR to main**

Review the exact diff against this plan, resolve important findings, push `codex/release-v2.0.2`, and open a PR against `main`.

- [ ] **Step 4: Wait for all required GitHub checks and merge**

Merge only when every required check passes. Confirm the merged `main` SHA before publishing.

### Task 4: Publish PyPI and GitHub artifacts

**Files:**
- External: PyPI project `proofline-evidence`
- External: Git tag and GitHub Release `v2.0.2`

**Interfaces:**
- Consumes: exact merged `main` SHA and qualified release artifacts.
- Produces: publicly verifiable PyPI files, immutable Git tag, GitHub Release assets, and SHA-256 records.

- [ ] **Step 1: Dispatch the PyPI Trusted Publisher workflow from main**

Wait for build, publish, and public-verification jobs; stop if any digest or version check fails.

- [ ] **Step 2: Verify the public PyPI files and fresh-install smoke**

Compare both public digests to the workflow artifacts, install `proofline-evidence==2.0.2` without cache in a fresh environment, confirm `proofline --version`, and run `proofline demo stale-decision` plus package verification.

- [ ] **Step 3: Tag the same merged commit and create the GitHub Release**

Create annotated tag `v2.0.2`, push it, and publish the qualified wheel, sdist, web archive, plugin ZIP, platform receipt where qualified, and `SHA256SUMS` with `docs/releases/v2.0.2.md` as notes.

- [ ] **Step 4: Verify the public GitHub Release**

Confirm tag target, asset names, sizes, and public SHA-256 digests match the exact local bytes.

### Task 5: Submit and verify the ChatGPT plugin

**Files:**
- External artifact: `proofline-plugin-v2.0.2.zip`
- Modify after external observation: `docs/submission/openai-plugin.md`

**Interfaces:**
- Consumes: skills-only plugin content from exact tag `v2.0.2`.
- Produces: verified ZIP digest, portal submission record, and evidence that distinguishes submitted, approved, and published states.

- [ ] **Step 1: Build and inspect the skills-only ZIP from the exact tag**

Match the previously approved skills-only layout: include `.codex-plugin/plugin.json`, `assets/plugin-icon.png`, and `skills/manage-evidence-decisions/` with its bundled verifier and fixture only. Reject secrets, private keys, databases, caches, generated application bundles, and unrelated source files.

- [ ] **Step 2: Verify the extracted ZIP in a clean directory**

Run the bundled evidence-package and review-receipt verifiers plus manifest/version/content checks from the extracted archive; compute its SHA-256 digest.

- [ ] **Step 3: Prepare the authenticated portal form**

Upload the exact ZIP and inspect displayed name, developer, version `2.0.2`, skill, permissions, and validation results.

- [ ] **Step 4: Ask for action-time confirmation and submit**

Request confirmation only when the portal is ready for the final Submit click, then perform the representational action after confirmation.

- [ ] **Step 5: Observe status and record exact evidence**

Record submission identifier, ZIP digest, timestamp, and observed scanning, review, approval, or publication state without extrapolation. If a documentation-only evidence commit is required, merge it without altering tag `v2.0.2` or published artifacts.
