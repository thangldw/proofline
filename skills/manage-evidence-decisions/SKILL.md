---
name: manage-evidence-decisions
description: Create, review, explain, export, verify, or check the freshness of evidence-backed engineering decisions with Proofline. Use for ADRs, architecture decisions, exact source citations, provenance review, stale-decision checks, portable Decision Evidence Packages, and requests to explain which immutable evidence justified a decision.
---

# Manage evidence-backed decisions

Use Proofline to preserve source identity, source version, and exact cited spans. Keep the distinction between source evidence, an engineering judgment, and a deterministic integrity check explicit.

## Setup check

1. Prefer an existing `.venv/bin/proofline` in the plugin or project checkout.
2. If it is missing, explain that Proofline requires Python 3.11+ and local dependencies. Ask before installing dependencies; do not silently run `make setup`.
3. Keep `PROOFLINE_HOME` in a user-approved local directory. Do not point it at a shared or sensitive directory without confirmation.

## Workflow

1. Resolve the user's requested decision or evidence package and the exact local scope.
2. For a new decision, identify the source, immutable version, exact span, decision statement, alternatives, and rationale. Do not invent absent evidence.
3. Use the narrowest Proofline command from `references/commands.md`.
4. Before any write, preview what local database or output path will change. Verification and explanation commands should remain read-only.
5. Report unresolved citations, changed evidence, missing provenance, and integrity failures directly.
6. Return a decision summary with evidence locations, freshness status, limitations, and next review date or trigger.

## Guardrails

- Never treat a citation as proof that the engineering decision is correct.
- Never rewrite cited source content to make a decision appear current.
- Do not overwrite exports, packages, backups, or reports unless the user explicitly authorizes `--force`.
- Do not enable an external model or embedding provider unless the user explicitly configures and authorizes it.
- Do not expose source content, local paths, credentials, or evidence packages beyond the user's selected audience.

## Output

Return: `decision`, `evidence`, `source_versions`, `freshness`, `integrity`, `limitations`, and `next_action`.
