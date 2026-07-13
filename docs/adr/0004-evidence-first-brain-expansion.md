# ADR 0004: Evidence-first brain expansion

**Status:** Accepted  
**Date:** 2026-07-13

## Context

Proofline's immutable source/version/span model can support personal capture and learning
workflows without weakening its Engineering Decision Memory core. The proposed “second brain”,
“learning brain”, “third brain”, and “team brain” labels are otherwise too broad and could lead
to a rich editor, generic agents, or collaboration features before the trust model is ready.

## Decision

We will deliver the expansion as bounded, evidence-first vertical slices:

1. **v0.12 — Personal Second Brain.** User-authored plain Markdown notes are sources with a
   stable `note://` identity, immutable revisions, deterministic tags and wiki-links, exact-span
   backlinks, existing search/citation behavior, and existing deletion cascade. This is quick
   capture, not a rich-text editor.
2. **v0.13 — Learning Brain.** Study prompts, flashcards, and review state may be derived only
   from immutable source spans. Every card or answer must retain exact evidence and expose
   failures; deterministic generation comes before optional models.
3. **v0.14 — Third Brain AI.** Suggestions and plans must be citation-grounded, reviewable, and
   unable to silently mutate sources or accepted memory. This is not a generic autonomous agent.
4. **v0.15 — Team Brain.** Shared workspaces remain gated on authentication, RBAC, organization
   audit, synchronization semantics, and permission-aware retrieval. It is planned, not yet
   implemented.

Engineering artifacts remain the primary product surface. Personal and learning workflows reuse
the same provenance contract rather than creating a parallel note database.

## Consequences

- A note edit creates a new `SourceVersion`; old citations remain resolvable.
- Wiki-links and tags are parsed deterministically with exact offsets. Backlinks identify the
  immutable source version in which the link occurs.
- No graph database, canvas, rich-text editor, real-time collaboration, or autonomous write-back
  is introduced by this decision.
- Each later milestone needs its own tested acceptance criteria before documentation may call it
  implemented.
