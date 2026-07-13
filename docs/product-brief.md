# Product Brief: Proofline

**Document status:** Baseline product intent  
**Implementation status:** Foundation vertical slice in progress  
**Last updated:** 2026-07-12

## Product statement

Proofline is an open-source, evidence-first Engineering Decision Memory. It is intended to
help engineers answer questions such as:

> Why was this architecture chosen, which assumptions supported it, where was it implemented,
> and is that decision still valid?

Proofline should ingest engineering artifacts that already exist, extract reviewable memory,
and answer with citations to exact source spans. It should not require teams to migrate their
writing into a new editor.

## The problem

Engineering context is fragmented across ADRs, Markdown files, pull requests, issues, meeting
notes, and commits. Search can recover matching documents but often cannot reconstruct:

- the decision that was made and alternatives that were rejected;
- the assumptions and constraints that were true at the time;
- the evidence supporting a conclusion;
- which later decision superseded an earlier one;
- where a decision was implemented; or
- whether an AI-generated answer is grounded or inferred.

This causes repeated investigations, slow onboarding, contradictory implementation, and
decisions that outlive the assumptions that justified them.

## Initial users

The initial individual users are staff and principal engineers, tech leads, architects, and
engineering managers. The initial team profile is a 5–50 person engineering organization that
has meaningful technical documentation and source-control history, and values local or
self-hosted processing.

Proofline remains primarily optimized for engineering decision memory. Evidence-first personal
capture and learning workflows are an experimental extension accepted in ADR 0004; consumer
journaling and company-wide enterprise search remain outside the current scope.

## Product principles

1. **Evidence before fluency.** A short, qualified answer with precise evidence is better than
   a confident answer without support.
2. **Sources remain authoritative.** Extracted memories are derived, inspectable, reversible,
   and never silently replace source material.
3. **Local-first by default.** A useful single-user workflow must work with local storage.
   Cloud services may add convenience, not data captivity.
4. **Model-agnostic by contract.** Domain behavior must not depend on one model vendor.
5. **Human-governed memory.** Users must be able to inspect, accept, correct, obsolete, merge,
   export, and delete AI-derived memory.
6. **Engineering-native capture.** Integrate with existing artifacts instead of creating a new
   rich-text authoring environment.
7. **Observable pipelines.** Users should be able to tell what was indexed, what failed, what
   model ran, and why evidence was retrieved.

## Current foundation

The runnable foundation implements Markdown/text upload, deterministic chunks, SQLite FTS5
search, and source/chunk provenance. Explicitly marked English/Vietnamese decisions are extracted
without a model and linked to exact evidence. A React/Vite console supports upload, search,
source and decision browsing, and evidence inspection. The API supports source deletion with
derived versions, chunks, embeddings, decisions, evidence, audit content, and FTS rows removed.
A metadata-only preview reports the exact impact before deletion; ingestion jobs remain as safe,
detached diagnostics.

Synchronous ingestion attempts persist inspectable success/failure jobs without storing source
content in error records. Decisions support governed status/correction actions with an append-only
before/after audit trail. A provider-neutral gateway supports fake and OpenAI-compatible generation
with remote egress disabled by default and secret-safe model-run diagnostics. Ingestion jobs use
private integrity-checked staged input, atomic domain/job commits, bounded retry, dead-letter state,
idempotency keys, and startup recovery. It does **not** yet implement scalable vector retrieval or
desktop packaging. Registered-root folder scans are available
for explicit, on-demand Markdown/text import; missing files are previewed and require an exact-set
confirmation on a subsequent clean rescan before deletion, while unambiguous same-content renames
preserve source identity. An opt-in single-process polling watcher invokes those scans sequentially,
uses fresh sessions, and never confirms deletion. The current hybrid answer
path combines
lexical and dense retrieval through RRF and enforces server-owned evidence IDs plus exact immutable
citations. Dense scoring is intentionally bounded and not yet a large-vault performance claim.
Generation providers can also create decision candidates, but only after structured-output and
evidence-ID validation; candidates remain unaccepted until the user reviews them.
The bounded Personal Second Brain slice adds plain Markdown quick capture as a `note` source kind.
Notes use generated stable identities, immutable content revisions, deterministic exact-span tags
and wiki-links, and current-version backlinks; they do not introduce a rich-text editor or a
parallel provenance model.
The Learning Brain slice deterministically derives study cards from explicit `Q:`/`A:` pairs. Each
answer is an exact immutable source span, reviews are append-only, and source revisions supersede
rather than rewrite historical cards. Optional model-generated questions remain unimplemented.
The Third Brain slice persists only citation-grounded action proposals from the existing validated
generation pipeline. Candidates retain model-run lineage, require explicit human accept/reject,
and cannot write back to sources or governed memory.
The Studio slice derives nine local artifact views from one immutable source version. Every report
section, slide, storyboard scene, mind-map branch, card, quiz answer, infographic fact and table row
retains an exact source span. Audio narration uses browser speech and is not a generated media file.

## MVP outcome

The first complete vertical slice will:

1. import a local folder containing Markdown and ADR files;
2. preserve source identity, content hash, and exact text spans;
3. index content incrementally for lexical and semantic retrieval;
4. extract candidate decisions, assumptions, alternatives, and evidence;
5. let a user review derived memories;
6. answer a question using retrieved evidence;
7. distinguish direct evidence, synthesis, inference, and insufficient evidence; and
8. open each citation at the relevant source span.

Git history and GitHub ingestion are the next planned source family after the local-folder
slice is reliable.

## First-class concepts

| Concept | Meaning |
| --- | --- |
| Source | An imported artifact with stable identity and version history |
| Source span | Exact offsets and quoted content from one source version |
| Claim | A proposition either stated in a source or derived from evidence |
| Decision | A chosen course of action with status and temporal validity |
| Assumption | A condition believed true when a decision was made |
| Constraint | A limit that shaped a decision |
| Alternative | An option considered but not chosen |
| Evidence | A source span supporting or contradicting a claim |
| Relation | A typed, inspectable link such as `supports`, `contradicts`, or `supersedes` |
| Memory revision | A user or system change to derived memory with an audit trail |

## Answer contract

Every material statement in an answer must be classified as one of:

- **Direct evidence:** explicitly stated in a cited source span.
- **Synthesis:** combines two or more cited spans without adding an unsupported fact.
- **Inference:** a model-generated conclusion, visibly labeled and accompanied by evidence.
- **Insufficient evidence:** the system cannot support a reliable answer.

Document-level references alone do not satisfy the MVP citation requirement. A citation must
identify a source version and a bounded span that the user can inspect.

## MVP scope

### In scope

- Local single-user workspace.
- Local folder import and incremental re-indexing.
- Markdown and ADR-shaped Markdown.
- Exact-span provenance and citation opening.
- Full-text search plus an embedding interface.
- Provider adapters for OpenAI-compatible remote APIs and a local runtime endpoint.
- Structured extraction with schema validation and recoverable failures.
- Review queue for candidate decisions and assumptions.
- Ask-and-answer workflow grounded in workspace sources.
- Exportable, documented data structures.
- Pipeline status, errors, and retry controls.

### Explicitly out of scope for the MVP

- A rich-text or Notion-like editor.
- Canvas, whiteboard, or graph visualization as a primary experience.
- Real-time multiplayer editing.
- General-purpose autonomous agents.
- Mobile applications.
- Email, calendar, Slack, Teams, Jira, or Confluence connectors.
- Managed cloud sync, billing, SSO, RBAC, or enterprise control plane.
- A custom model runtime or graph database.
- Server-rendered or downloadable podcast audio, video and presentation files.
- Silent autonomous mutation of approved memories.

## Trust and governance requirements

- Imported source content must not be sent to a remote provider without an explicit provider
  configuration that makes this behavior clear.
- Every derived object must record its creator (`user`, `import`, or `model`), model identity
  when applicable, timestamp, source version, and evidence links.
- Deleting a source must offer deletion of derived chunks, embeddings, evidence, and orphaned
  memory, with a preview of impact.
- Model output must be treated as untrusted input and validated before persistence.
- A failed extraction must not block source search or make the source appear fully processed.

## Success measures

The first pilot should measure outcomes, not volume of notes or tokens:

| Metric | Initial target | Measurement intent |
| --- | ---: | --- |
| Citation precision | >= 90% | Cited span directly supports the associated statement |
| Useful-answer rate | >= 65% | Pilot user marks answer useful for the real question |
| Time-to-context reduction | >= 50% | Median time versus the user's current workflow |
| Indexing visibility | 100% | Every discovered source has a visible terminal state |
| Deletion integrity | 100% in test suite | Selected source and scoped derived data are removed |
| Weekly pilot usage | >= 3 of 5 teams | Evidence of repeated value rather than demo appeal |

Targets are hypotheses until a pilot dataset and baseline exist.

## Commercial and open-source direction

The community product should remain useful locally and self-hosted, with open import/export
and bring-your-own-model support. Potential paid surfaces include managed sync, hosted
inference, backups, team collaboration, administration, and enterprise operations.

The repository currently uses the MIT license. Any future open-core, dual-license, trademark,
or contribution-rights strategy requires a separate reviewed decision; this brief does not
change the repository license.

## Open product questions

- Which engineering source family produces the highest-value pilot questions after Markdown?
- Should embeddings be optional in the first runnable release or required for quality?
- What review interaction achieves high correction rates without creating a curation burden?
- Which local model/runtime combinations meet extraction quality and latency thresholds?
- What portable representation should be guaranteed for exported derived memory?
