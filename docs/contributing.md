# Contributing to Proofline

**Document status:** Baseline workflow  
**Repository status:** Foundation / pre-alpha

Thank you for helping build Proofline. The project values small, evidence-backed changes that
preserve provenance, local ownership, and model independence.

## Before contributing

Read, in order:

1. [Product brief](./product-brief.md)
2. [MVP architecture](./architecture.md)
3. [ADR-0001](./adr/0001-scope-and-stack.md)
4. [90-day roadmap](./roadmap-90-days.md)

The MVP is intentionally narrow. A feature being useful does not automatically make it part of
the current milestone.

## Contribution types

- **Bug fix:** include reproduction, expected behavior, risk, and regression test.
- **Feature:** link an approved issue with user outcome and acceptance criteria.
- **Architecture change:** add or supersede an ADR before coupling code to the decision.
- **Provider adapter:** demonstrate capability checks, normalized errors, schema validation,
  redacted logs, and credential-free contract tests.
- **Parser/connector:** define identity, versioning, span semantics, path/security boundaries,
  deletion behavior, fixtures, and failure diagnostics.
- **Evaluation change:** document dataset provenance, labels, version, measurement procedure,
  and limitations.
- **Documentation:** state whether behavior is proposed, planned, or implemented and link the
  verification source for implementation claims.

## Issue readiness

An implementation issue is ready when it contains:

- the user or operator problem;
- in-scope and out-of-scope behavior;
- testable acceptance criteria;
- affected architecture boundaries;
- privacy, security, migration, and deletion considerations;
- dependencies and known blockers; and
- expected tests and documentation updates.

Ambiguous issues should be refined before code is written. Prefer a small vertical behavior
over a broad layer with no user-visible path.

## Branch and pull request workflow

1. Create a focused branch from the current default branch.
2. Inspect existing work and avoid overwriting unrelated changes.
3. Add or update tests with the implementation.
4. Run the repository-provided formatting, lint, type-check, test, migration, and build commands.
5. Update documentation and status labels to match actual behavior.
6. Open a pull request that explains outcome, design, verification, risks, and deferred work.

Current root quality commands are:

```bash
make test
make check
make format
```

Use `make setup` once, then run `make dev-api` and `make dev-web` in separate terminals. The
root README and Makefile are the current command source of truth. Always inspect them before
assuming additional commands exist.

## Change discipline

- Keep domain modules independent of FastAPI, SQLite, and provider SDKs.
- Validate all external, parser, API, database JSON, and model data at boundaries.
- Preserve immutable source versions and exact-span invariants.
- Never create accepted memory directly from model output.
- Make processing states and recoverable failures inspectable.
- Keep remote model egress explicit and redact source content and secrets from logs.
- Add migrations; do not mutate released schema history.
- Avoid a new dependency when a small local implementation is sufficient. Document why any
  security-sensitive or runtime dependency is needed.
- Do not add a new connector, provider, database, or deployment mode without an owner and
  contract-test plan.

## Tests expected by boundary

| Change | Minimum verification |
| --- | --- |
| Domain rule | Unit tests for success, rejection, and state transitions |
| Database | Real migration and repository integration tests in a temporary database |
| Parser | Golden fixtures, encoding/offset checks, malformed input, and version changes |
| Model adapter | Fake/recorded contract tests, timeout/error normalization, redaction |
| Retrieval | Deterministic ranking tests plus evaluation-set delta |
| Citation | Span hash validation and adversarial invalid identifiers/offsets |
| UI workflow | Component tests and at least one end-to-end happy/failure path |
| Deletion | Preview, cascade, retry/rollback, and orphan checks |

Live provider tests must be opt-in, clearly named, and excluded from default CI unless a
maintainer-managed test account and spending limit exist.

The credential-free supported-platform smoke can also be run locally:

```bash
python scripts/platform_smoke.py
```

CI is configured to run this installed-package smoke and the web production build on Ubuntu and
macOS 14. It is a pre-alpha source-development check, not a native packaging or production-support
claim.

## Pull request description

Use this minimum structure:

```markdown
## Outcome
What user-visible or operator-visible behavior changed?

## Scope
What is deliberately not included?

## Design
Which boundaries and decisions are affected?

## Verification
Exact commands and results; evaluation delta if relevant.

## Risk and rollback
Migration, privacy, security, provider, deletion, and compatibility concerns.

## Documentation
Files updated and whether the capability is planned or implemented.
```

## Review priorities

Reviewers should check, in order:

1. evidence/citation correctness and data-loss risk;
2. privacy, remote egress, secret handling, and imported-input safety;
3. domain boundary and migration compatibility;
4. failure observability, idempotency, and recovery;
5. tests and reproducibility;
6. performance within the documented scale envelope; and
7. maintainability and clarity.

## Commit and generated-content policy

Keep commits reviewable and describe the intent, not only the files changed. Generated code,
fixtures, prompts, or documentation remain the contributor's responsibility: review them,
remove unsupported claims, and record the generator/model only where project policy requires
reproducibility. Never commit credentials, private pilot data, raw proprietary source content,
or provider responses containing it.

## Licensing and contributor rights

Contributions are currently governed by the repository's MIT license. The project has not
adopted a CLA, DCO, dual license, or open-core licensing boundary. Maintainers must settle and
document any change before requesting additional contributor rights.
