# ADR 0002: Git source identity and provenance

- Status: accepted
- Date: 2026-07-13

## Context

Proofline must cite repository evidence without allowing a later checkout or branch movement to
change what an existing citation means. A working-tree path or branch name alone is mutable.

## Decision

The first Git connector is local and read-only. A user explicitly registers the repository root
and a revision (default `HEAD`). Proofline resolves that revision to a full commit SHA before
reading any content, then reads tracked objects through Git rather than the working tree.

Each imported file uses the immutable locator:

```text
repository root + full commit SHA + repository-relative path + exact offsets/lines
```

Commit metadata is a separate `git_commit` source containing the full SHA, author identity,
authored time, subject, and body. Tracked Markdown and UTF-8 text files are `git_file` sources.
The canonical source URI includes the resolved commit and path, so repeating the same scan is
idempotent while a new commit creates new immutable sources. Historical sources and citations are
not overwritten.

Per-file failures are explicit and make the repository status degraded. Deleting a registered
repository runs the existing derived-data deletion contract for every owned source before removing
the registration.

## Consequences

- Branch movement cannot mutate existing evidence.
- The same file at two commits is intentionally two source identities.
- Working-tree changes that are not committed are not imported.
- Network clone, hosted authentication, submodules, binary parsing, and Git write-back remain out
  of scope.
