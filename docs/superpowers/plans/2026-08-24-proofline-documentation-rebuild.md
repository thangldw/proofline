# Proofline Documentation Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Proofline's legacy documentation, diagrams, illustrations, specification prose, plugin instructions, and Markdown fixtures with a deterministic trilingual documentation system.

**Architecture:** Public documentation is organized as one file per topic with complete English, Vietnamese, and Japanese sections in that order. A repository-local checker enforces the required file set, language order, link integrity, removal manifest, raster/Mermaid ban, and diagram constraints; three self-contained Diagram Design HTML/SVG artifacts provide the only documentation visuals.

**Tech Stack:** Markdown, Python 3.11, pytest, static HTML/CSS/SVG, Diagram Design validation, Vitest, Playwright, uv, npm.

**Spec:** `docs/superpowers/specs/2026-08-24-proofline-documentation-rebuild-design.md`

## Global Constraints

- English is authoritative; every public human-facing topic then includes a complete Vietnamese translation and a complete Japanese translation.
- Preserve commands, paths, schema identities, field names, error codes, hashes, URLs, and machine-consumed frontmatter.
- Do not duplicate executable fixture decisions across languages because extraction cardinality and exact-span behavior must remain stable.
- Use `proofline-evidence` for the PyPI distribution and `proofline` for the CLI and import package.
- Do not claim hosted sync, shared workspaces, OAuth, organization identity, trusted time, revocation, remote MCP, identity proof from signature validity, or production benchmark evidence.
- All diagrams use `.diagram-design` with exactly `profile: default`; paper `#f5f5f5`, ink `#2d3142`, accent `#eb6c36`.
- Documentation diagrams are static self-contained HTML with embedded CSS and accessible inline SVG; no raster, Mermaid, external images, or animation.
- Preserve runtime application icons, bundled application HTML/JS/CSS, schemas, JSON vectors, PEM fixtures, source code, configuration, `LICENSE`, and release artifacts.
- Do not publish PyPI, GitHub, or plugin releases in this documentation-only change.
- Execute in an isolated `codex/` worktree and create a small commit after each task.

---

### Task 1: Documentation contract and deletion manifest

**Files:**
- Create: `scripts/check_documentation.py`
- Create: `apps/api/tests/test_documentation_contract.py`
- Modify: `apps/api/tests/test_public_page.py`
- Delete: `scripts/render_readme_demo_gif.py`
- Delete: `docs/assets/stale-decision-demo.gif`
- Delete: `docs/assets/stale-decision-report.jpg`
- Delete: `docs/assets/stale-decision-terminal.png`
- Delete: `docs/releases/v1.0.0.md`
- Delete: `docs/releases/v1.0.1.md`
- Delete: `docs/superpowers/plans/2026-08-23-proofline-v1-1-decision-health.md`
- Delete: `docs/superpowers/plans/2026-08-23-proofline-v1-2-v2-impact-attestations.md`
- Delete: `docs/superpowers/specs/2026-08-23-proofline-v1-1-decision-health-design.md`
- Delete: `docs/superpowers/specs/2026-08-23-proofline-v1-2-v2-impact-attestations-design.md`

**Interfaces:**
- Consumes: repository root resolved from `Path(__file__).parents[1]`.
- Produces: `check_documentation(root: Path) -> list[str]` and a CLI returning exit code 0 on success, 1 with one error per stderr line on failure.

- [ ] **Step 1: Write failing contract tests**

Add tests that copy minimal files into `tmp_path`, call `check_documentation`, and assert exact errors for missing required files, wrong language order, a Mermaid fence, a docs raster, a broken relative link, a forbidden legacy path, and an HTML diagram containing an external URL. The repository-wide success assertion is added in Task 5 after every required artifact exists.

```python
def test_checker_rejects_wrong_language_order(tmp_path: Path) -> None:
    write_minimum_tree(tmp_path)
    (tmp_path / "README.md").write_text(
        "## Tiếng Việt\nvi\n## English\nen\n## 日本語\nja\n", encoding="utf-8"
    )
    assert (
        "README.md: language sections must be English, Tiếng Việt, 日本語"
        in check_documentation(tmp_path)
    )
```

- [ ] **Step 2: Run the new tests and confirm the red state**

Run: `.venv/bin/pytest apps/api/tests/test_documentation_contract.py -q`

Expected: collection fails because `scripts.check_documentation` does not exist.

- [ ] **Step 3: Implement the deterministic checker**

Define exact `REQUIRED_TRILINGUAL`, `REQUIRED_DIAGRAMS`, and `FORBIDDEN_PATHS` tuples. Parse Markdown outside fenced code blocks, require headings matching `^#{1,6} (English|Tiếng Việt|日本語)$` in increasing order, resolve repository-relative links after stripping query and fragment components, reject `mermaid` fences and `.png/.jpg/.jpeg/.gif` files below `docs/`, and check every diagram for `<svg`, `<title`, `<desc`, `role="img"`, absence of `http://`, `https://`, `<img`, `<script`, animation elements, and external CSS.

```python
def check_documentation(root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(check_required_paths(root))
    errors.extend(check_language_order(root))
    errors.extend(check_markdown_links(root))
    errors.extend(check_forbidden_content(root))
    errors.extend(check_diagrams(root))
    return sorted(errors)
```

- [ ] **Step 4: Replace obsolete public-page assertions and delete legacy artifacts**

Remove the Mermaid-positive assertion from `test_public_page.py`. Assert the new README product sentence, links to `docs/getting-started.md`, `docs/architecture.md`, `docs/evidence-packages.md`, and `docs/submission/openai-plugin.md`, plus the package/CLI distinction and the current `v2.0.0` scope. Delete only the exact tracked files listed above with `apply_patch`; verify `git status --short` contains no untracked deletion target.

- [ ] **Step 5: Verify the contract task**

Run:

```bash
.venv/bin/pytest apps/api/tests/test_documentation_contract.py apps/api/tests/test_public_page.py -q
.venv/bin/python scripts/check_documentation.py
git diff --check
```

Expected: the checker unit tests pass; invoking the checker on the repository lists only required replacement documents and diagrams that later tasks create.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_documentation.py apps/api/tests/test_documentation_contract.py apps/api/tests/test_public_page.py docs scripts/render_readme_demo_gif.py
git commit -m "test: define documentation rebuild contract"
```

---

### Task 2: Public entry points and policy documents

**Files:**
- Rewrite: `README.md`
- Rewrite: `CHANGELOG.md`
- Rewrite: `CONTRIBUTING.md`
- Rewrite: `PRIVACY.md`
- Rewrite: `SECURITY.md`
- Rewrite: `SUPPORT.md`
- Rewrite: `TERMS.md`
- Create: `docs/README.md`
- Create: `docs/getting-started.md`

**Interfaces:**
- Consumes: documented CLI behavior from `apps/api/proofline/runtime.py`, current version from `pyproject.toml`, and release checks from `scripts/release_check.py`.
- Produces: stable public navigation, exact installation commands, five-minute demo, contribution gates, and English-controlling trilingual policies.

- [ ] **Step 1: Verify every command and public claim against code**

Run `uv run proofline --help`, `uv run proofline demo stale-decision --help`, `uv run proofline serve --help`, `uv run proofline verify-package --help`, and `uv run proofline verify-attestation --help`. Record only command names, options, defaults, and boundaries observed in their output.

- [ ] **Step 2: Rewrite the public entry points from new outlines**

Write complete English, Vietnamese, and Japanese sections in each file. `README.md` contains product boundary, under-five-minute demo, implemented evidence, synthetic benchmark qualification, current limitations, install/package naming, plugin status with observation date, and documentation map. `CHANGELOG.md` retains compact release facts and immutable GitHub release links. `CONTRIBUTING.md` documents environment setup, targeted/full test commands, evidence standards, security reporting, and release immutability.

- [ ] **Step 3: Rewrite policies without weakening boundaries**

Each policy includes scope, local data behavior, optional provider behavior, key handling, incident/contact path, limitations, and English precedence. Preserve the MIT license reference and existing contact URLs; do not introduce warranties, hosted service promises, or organization identity claims.

- [ ] **Step 4: Create the documentation hub and getting-started guide**

`docs/README.md` provides role-based routes for evaluator, integrator, operator, and verifier plus a status legend separating implemented, optional, external state, synthetic evidence, and future work. `docs/getting-started.md` covers `git clone`, `uv sync --extra dev`, stale-decision demo, local server, first package verification, and cleanup without assuming global installation.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/pytest apps/api/tests/test_public_page.py apps/api/tests/test_documentation_contract.py -q
.venv/bin/python scripts/check_documentation.py
.venv/bin/python scripts/release_check.py --tag v2.0.0
git diff --check
```

Expected: only not-yet-created Task 3–5 files remain in checker output; release check returns `{"status": "ready", "tag": "v2.0.0"}`.

```bash
git add README.md CHANGELOG.md CONTRIBUTING.md PRIVACY.md SECURITY.md SUPPORT.md TERMS.md docs/README.md docs/getting-started.md
git commit -m "docs: rebuild public entry points and policies"
```

---

### Task 3: Core technical documentation

**Files:**
- Rewrite: `docs/architecture.md`
- Create: `docs/decision-lifecycle.md`
- Rewrite: `docs/evidence-packages.md`
- Create: `docs/cli-reference.md`
- Create: `docs/api-reference.md`
- Rename and rewrite: `docs/OPERATIONS.md` to `docs/operations.md`
- Create: `docs/release-process.md`
- Rewrite: `docs/releases/v2.0.0.md`
- Rename and rewrite: `docs/submission/DIRECTORY_SUBMISSION.md` to `docs/submission/openai-plugin.md`

**Interfaces:**
- Consumes: routes in `apps/api/proofline/api.py`, `apps/api/proofline/decision_review_api.py`, and `apps/api/proofline/decision_impact_api.py`; CLI parsers in `apps/api/proofline/runtime.py`; schemas/test vectors under `spec/`; workflows under `.github/workflows/`; and current external-state evidence already present in the submission document.
- Produces: authoritative technical topics linked from the public hub; diagram links target Task 5 HTML files.

- [ ] **Step 1: Extract the exact CLI and API surfaces**

Use `rg` over runtime parsers and FastAPI route decorators. Build command and endpoint tables containing only shipped surfaces. Mark workspace headers, mutating endpoints, filesystem effects, exit codes, and local OpenAPI discovery without copying generated OpenAPI wholesale.

- [ ] **Step 2: Write architecture and lifecycle documents**

Explain local-first boundaries, SQLite/FTS ingest, immutable versions/spans, deterministic retrieval and verification, optional AI boundary, historical decision status versus current review state, re-anchoring, resolution, and transitive impact. Link to `diagrams/system-architecture.html` and `diagrams/decision-review-lifecycle.html`; do not embed Mermaid.

- [ ] **Step 3: Write evidence, CLI, API, operations, and release documents**

Separate DEP integrity from signed-attestation authenticity, explain canonicalization/error boundaries, and link to all three specs. Document backup/restore, bulk ingest, integrity checks, key trust, incident response, qualification gates, Trusted Publishing, artifact verification, immutable versioning, and plugin submission without exposing secret values.

- [ ] **Step 4: Rewrite current release and dated plugin submission state**

Keep `docs/releases/v2.0.0.md` as the only in-tree release page and preserve the release-check-compatible path. In `docs/submission/openai-plugin.md`, state the observation date, public directory URL, submitted/public version distinction, reviewer commands, package boundary, and no-remote-MCP limitation; distinguish repository facts from observed external state.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/pytest apps/api/tests/test_public_page.py apps/api/tests/test_documentation_contract.py -q
.venv/bin/python scripts/check_documentation.py
.venv/bin/python scripts/release_check.py --tag v2.0.0
git diff --check
```

Expected: only Task 4 spec/plugin files and Task 5 diagrams remain missing.

```bash
git add docs
git commit -m "docs: rebuild technical documentation"
```

---

### Task 4: Specifications, plugin instructions, and executable Markdown fixtures

**Files:**
- Rewrite: `spec/decision-evidence-package/README.md`
- Rewrite: `spec/decision-evidence-package/VERSIONING.md`
- Rewrite: `spec/decision-evidence-package/v1/test-vectors/README.md`
- Create: `spec/decision-review-receipt/README.md`
- Create: `spec/signed-attestation/README.md`
- Rewrite: `skills/manage-evidence-decisions/SKILL.md`
- Rewrite: `skills/manage-evidence-decisions/references/commands.md`
- Rewrite: `apps/api/proofline/data/architecture-decision.md`
- Rewrite: `examples/architecture-decision.md`
- Rewrite: `apps/web/e2e/fixtures/vertical-path.md`
- Verify: `apps/api/tests/test_openai_plugin_bundle.py`
- Verify: extraction and E2E tests that consume the fixtures

**Interfaces:**
- Consumes: immutable schemas/vectors, `proofline_package.py`, `verify_attestation_vector.py`, plugin manifest, extraction parser, and Playwright fixture expectations.
- Produces: trilingual explanatory prose while preserving English machine frontmatter and tested plugin phrases: `proofline verify-attestation`, `trusted public key`, `Proofline 2.0.0`, and `bundled verifier does not verify Ed25519`.

- [ ] **Step 1: Capture fixture behavior before rewriting**

Run targeted parser, bundled verifier, and vertical-path E2E tests. Record expected decision count, title/status fields, source-span behavior, and hostile-markup inertness. Do not change those assertions merely to accommodate prose.

- [ ] **Step 2: Rewrite specification prose around immutable machine artifacts**

Document schema identity, canonical JSON, root hash, error codes, verification steps, mutation vectors, compatibility/versioning, receipt relationship, and attestation trust. Leave every schema, JSON vector, expected value, mutation, and PEM file byte-for-byte unchanged.

- [ ] **Step 3: Rewrite plugin documents and preserve executable contracts**

Keep valid skill frontmatter. Provide English, Vietnamese, and Japanese workflow guidance for verifying/explaining packages, verifying review receipts, delegating Ed25519 verification to installed Proofline 2.0.0, selecting a trusted public key, and never collecting private keys. Preserve the four exact English phrases asserted by tests.

- [ ] **Step 4: Rewrite fixtures with one synthetic English decision each**

Use new neutral content and preserve parser syntax, number of decisions, expected decision status, exact citation shape, and hostile HTML/script markers used by E2E. Add an adjacent comment explaining that fixtures are intentionally not triplicated because they are source data.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/pytest apps/api/tests/test_openai_plugin_bundle.py apps/api/tests/test_documentation_contract.py -q
make verify-package-conformance
npm --workspace @proofline/web run test:e2e -- e2e/vertical-path.spec.ts
.venv/bin/python scripts/check_documentation.py
git diff --check
```

Expected: package/plugin and fixture tests pass; only Task 5 diagrams remain missing.

```bash
git add spec skills apps/api/proofline/data/architecture-decision.md examples/architecture-decision.md apps/web/e2e/fixtures/vertical-path.md
git commit -m "docs: rebuild specifications and plugin guidance"
```

---

### Task 5: Diagram Design HTML/SVG artifacts

**Files:**
- Create: `.diagram-design`
- Create: `docs/diagrams/system-architecture.html`
- Create: `docs/diagrams/decision-review-lifecycle.html`
- Create: `docs/diagrams/evidence-verification.html`
- Modify: `apps/api/tests/test_documentation_contract.py`
- Modify: technical Markdown only if final diagram filenames or accessible labels require link correction

**Interfaces:**
- Consumes: Diagram Design references `type-architecture.md`, `type-state.md`, `semantic-patterns.md`, default profile marker, and the approved node/connector budgets.
- Produces: three self-contained HTML files, each containing English, Vietnamese, and Japanese accessible SVG figures in order.

- [ ] **Step 1: Load the required Diagram Design references and persist the profile**

Read the architecture, state-machine, semantic-pattern, output-spec, and profile references completely. Write `.diagram-design` as exactly:

```yaml
profile: default
```

- [ ] **Step 2: Build the system architecture diagram**

Use at most eight nodes and ten connectors. Show local source files, deterministic ingest/versioning, SQLite/FTS, decision/citation model, stale/impact engine, evidence package verifier, CLI/API/web/desktop boundary, and optional AI outside the integrity-critical route. Duplicate the figure labels into full Vietnamese and Japanese figures without changing graph semantics.

- [ ] **Step 3: Build the decision-review lifecycle diagram**

Use at most six states and ten transitions. Distinguish accepted historical decision status from current review state, including fresh, review required, re-anchored, resolved, and transitive-impact paths. Use explicit transition labels and no unlabeled crossing connectors.

- [ ] **Step 4: Build the evidence-verification paved-road diagram**

Use at most eight nodes and ten connectors. Show untrusted input, schema/canonicalization, root-hash verification, exact-span checks, review-receipt verification, optional Ed25519 verification with trusted public key, verified result, and fail-closed errors. Keep signature validity separate from identity trust.

- [ ] **Step 5: Run structural and visual verification**

Run the skill's `self_check.py` against all three HTML files, then render at desktop and narrow widths in a browser. Verify no clipped text, overlap, accidental intersections, boundary crowding, broken glyphs, or language-order drift. Correct geometry in the HTML/SVG source and rerun checks.

Add the repository-wide contract assertion now that the complete replacement tree exists:

```python
def test_repository_documentation_contract() -> None:
    assert check_documentation(ROOT) == []
```

- [ ] **Step 6: Verify and commit**

Run:

```bash
.venv/bin/python scripts/check_documentation.py
.venv/bin/pytest apps/api/tests/test_documentation_contract.py apps/api/tests/test_public_page.py -q
git diff --check
```

Expected: documentation checker and targeted tests pass with zero errors.

```bash
git add .diagram-design docs/diagrams docs/architecture.md docs/decision-lifecycle.md docs/evidence-packages.md apps/api/tests/test_documentation_contract.py
git commit -m "docs: add trilingual verification diagrams"
```

---

### Task 6: Full qualification and exact manifest

**Files:**
- Modify only files required to correct failures caused by Tasks 1–5
- Do not modify immutable release artifacts, schemas, vectors, PEM fixtures, or unrelated application code

**Interfaces:**
- Consumes: all rebuilt documentation and the repository's existing qualification commands.
- Produces: a clean branch with an auditable deletion/replacement/addition/preservation/verification report.

- [ ] **Step 1: Run documentation and package gates**

```bash
.venv/bin/python scripts/check_documentation.py
make verify-package-conformance
.venv/bin/python scripts/release_check.py --tag v2.0.0
release_artifact_dir=$(mktemp -d)
uv build --out-dir "$release_artifact_dir"
.venv/bin/python scripts/verify_release_artifacts.py "$release_artifact_dir"/*.whl "$release_artifact_dir"/*.tar.gz
```

- [ ] **Step 2: Run full Python and web gates**

```bash
make test
make check
make audit
npm run test:e2e
```

Expected: Python, web, three egress tests, audit, build, evaluation, and browser E2E all pass. Report actual counts from current output; do not reuse historical counts.

- [ ] **Step 3: Inspect the exact change surface**

```bash
git diff --check HEAD~6..HEAD
git status --short
git diff --name-status HEAD~6..HEAD
rg -n '```mermaid|docs/OPERATIONS.md|DIRECTORY_SUBMISSION.md|stale-decision-demo\.(gif|png|jpg)' . --glob '!docs/superpowers/**' --glob '!.git/**' --glob '!node_modules/**'
find docs -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.gif' \) -print
```

Expected: no whitespace errors, clean status, no forbidden legacy reference outside historical design/plan evidence, and no documentation raster.

- [ ] **Step 4: Commit qualification-only corrections, if any**

If a gate required a correction, return to the owning Task 1–5 file set, rerun that task's targeted gate, and amend its task commit with `git commit --amend --no-edit`. If no correction is necessary, leave the five implementation commits unchanged.

- [ ] **Step 5: Prepare the final report**

Report the branch/worktree, commit list, deleted artifacts, rewritten artifacts, added artifacts, preserved immutable/runtime artifacts, diagram self-check and visual results, actual test counts, audit results, limitations, and the explicit fact that no PyPI/GitHub/plugin release occurred.
