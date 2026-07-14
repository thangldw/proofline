# Repository instructions

Build Proofline as an evidence-first Engineering Decision Memory. Every derived claim, decision,
or answer must resolve to an immutable source identity and exact source span.

## Scope

The project is experimental pre-alpha. Work on the smallest tracked vertical slice. Do not add a
rich editor, canvas, generic agents, graph database, collaboration, or connector matrix unless the
current roadmap explicitly opens that milestone.

## Engineering rules

- Preserve provenance across every transformation.
- Prefer deterministic parsing and retrieval before an LLM.
- Keep provider-specific AI code behind interfaces.
- Use migrations for persistent schema changes.
- Never hide ingestion or extraction failures.
- Cascade deletion through chunks, indexes, and derived records.
- Do not log source content, credentials, or prompts by default.
- Test behavior changes and regressions.
- Keep local development functional without external services.
- Use only offline system font stacks; do not add remote fonts or font packages.
- Use the documented collaborative-canvas palette and labelled Mermaid connectors for useful
  architecture, graph, and workflow diagrams.

## Completion rule

Behavior is complete only when tested, user-visible configuration is documented, failure modes are
explicit, and relevant quality commands pass. Never describe planned behavior as implemented.
