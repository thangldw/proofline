# AGENTS.md

These instructions apply to the entire repository.

## Mission

Build Proofline as an evidence-first Engineering Decision Memory system. Every
derived claim, decision, or answer must be traceable to an immutable source
identity and an exact source span.

## Current phase

The project is pre-alpha. Work toward the smallest end-to-end vertical slice
described in the root README and current roadmap. Do not add a rich editor,
canvas, collaboration, generic agents, graph database, or additional connector
matrix unless a tracked milestone explicitly requires it.

## Engineering rules

- Preserve provenance across every transformation.
- Prefer deterministic parsing and retrieval before introducing an LLM.
- Keep provider-specific AI code behind interfaces.
- Use migrations for persistent schema changes.
- Never silently discard ingestion or extraction failures.
- Deletion must include derived chunks and indexes.
- Do not log source contents, credentials, or model prompts by default.
- Add tests for behavior changes and regressions.
- Keep local development functional without external services.

## Definition of done

A change is done when its behavior is tested, user-visible configuration is
documented, failure modes are explicit, and the relevant quality commands pass.
Planned behavior must not be presented as implemented behavior.

