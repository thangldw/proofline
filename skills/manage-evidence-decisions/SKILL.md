---
name: manage-evidence-decisions
description: Review, explain, verify, or compare evidence-backed engineering decisions with Proofline. Use for ADRs, architecture decisions, exact source citations, provenance review, stale-decision checks, Decision Evidence Packages, and requests to explain which immutable evidence justified a decision.
---

# Manage evidence-backed decisions

Use Proofline to preserve source identity, source version, and exact cited spans. Keep the distinction between source evidence, an engineering judgment, and a deterministic integrity check explicit.

## Runtime

The bundled verifier is self-contained and uses Python 3.11+ standard-library modules only. Resolve its path relative to this `SKILL.md`; do not search for or install a separate Proofline checkout. Run `python3 scripts/proofline_package.py --help` before an unfamiliar operation.

## Workflow

1. Resolve the user's requested decision or evidence package and the exact local scope.
2. For a new decision, identify the source, immutable version, exact span, decision statement, alternatives, and rationale. Do not invent absent evidence.
3. Use the narrowest bundled command from `references/commands.md`.
4. Verification, explanation, and comparison are read-only. If the user asks to create or revise an ADR, preview the new output path and preserve the source text exactly.
5. Report unresolved citations, changed evidence, missing provenance, and integrity failures directly.
6. Return a decision summary with evidence locations, freshness status, limitations, and next review date or trigger.

## Guardrails

- Never treat a citation as proof that the engineering decision is correct.
- Never rewrite cited source content to make a decision appear current.
- Do not overwrite ADRs, exports, packages, backups, or reports without explicit approval.
- Do not enable an external model or embedding provider unless the user explicitly configures and authorizes it.
- Do not expose source content, local paths, credentials, or evidence packages beyond the user's selected audience. The bundled verifier intentionally reports hashes and span locations rather than quoted source content.

## Output

Return: `decision`, `evidence`, `source_versions`, `freshness`, `integrity`, `limitations`, and `next_action`.
