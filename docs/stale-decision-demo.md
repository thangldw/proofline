# Stale decision demo

The demo is Proofline's smallest product story: an accepted ADR cites exact requirement lines, the
requirement changes, and Proofline makes the review need visible while preserving the original
evidence.

## Run it

```bash
proofline demo stale-decision
```

The command is credential-free, does not read or modify the user's Proofline database, and uses an
ephemeral in-memory SQLite database. By default it writes artifacts to
`proofline-demo-stale-decision/`. It refuses to replace that directory; use `--force` only when the
existing demo artifacts are disposable, or select another path with `--output-dir`.

The scenario is deterministic in meaning:

1. `ADR-007` is accepted with one citation to `requirement.md:42-48`.
2. The requirement is ingested again under the same stable source identity, creating a new
   immutable source version.
3. The cited quote is compared with the current version. Because it no longer resolves exactly,
   the decision requires review.
4. The original, approved source version remains available in a Decision Evidence Package.

The generated files have distinct trust roles:

| File | Role |
| --- | --- |
| `evidence.zip` | Normative DEP v1 package; independently verifiable offline |
| `report.html` | Escaped, CSP-restricted human projection; readable offline but not the normative package |
| `decision-health.json` | Content-free receipt with decision/source IDs, cited/current version hashes, exact old locator, quote hash, and package root |

Verify the package with `proofline verify-package
proofline-demo-stale-decision/evidence.zip`. Verification recomputes all node hashes, exact spans,
parent references, and the package root. It does not need the demo database or health receipt.

## CI check

Run against an existing initialized Proofline state directory:

```bash
PROOFLINE_HOME=/path/to/state proofline check-decisions
```

The command is read-only: it does not run migrations, ingest sources, repair evidence, or update
review state. It checks accepted and active decisions. A source revision is allowed when every
approved exact quote still resolves; a changed quote exits `1` and reports the original locator.
Missing evidence, missing versions, and corrupt stored spans fail closed with content-free codes.
An absent or uninitialized database returns `database_unavailable`; the command never creates or
migrates one. Use `--format json` for CI annotations.

## Explicit limits

- Exact-quote continuity is deterministic but not semantic equivalence. Rewording requires human
  review even when meaning appears unchanged.
- The stale check does not claim source authenticity or author identity.
- `decision-health.json` is a diagnostic receipt, not DEP v1 and not independently verified by
  `verify-package`.
- DEP preserves the old evidence and proves its internal integrity; it does not prove that the new
  requirement is correct.
